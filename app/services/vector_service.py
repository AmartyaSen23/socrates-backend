import time
import requests
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings
from app.database import supabase_client
from app.status_store import log_update


class VectorService:
    @staticmethod
    def chunk_and_embed_filing(filing_id: str, storage_bucket_url: str, ticker: str):
        ticker_upper = ticker.strip().upper()

        # 1. Pull down the scrubbed SEC file from storage
        log_update(ticker_upper, "Downloading clean prose filing from storage...")
        file_bytes = supabase_client.storage.from_("sec-filings-raw").download(storage_bucket_url)
        clean_text = file_bytes.decode("utf-8", errors="ignore").strip()

        if not clean_text:
            raise ValueError(f"Downloaded filing text for {ticker_upper} is empty.")

        # 2. Create semantic text windows
        log_update(ticker_upper, "Slicing text into semantic chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200,
            length_function=len,
        )
        chunks = [c.strip() for c in text_splitter.split_text(clean_text) if c and c.strip()]

        if not chunks:
            raise ValueError(f"No valid text chunks produced for {ticker_upper}.")

        # Clear any stale chunks for this ticker before inserting fresh vectors
        try:
            supabase_client.table("soc_filing_chunks").delete().eq("ticker", ticker_upper).execute()
        except Exception as e:
            print(f"[{ticker_upper}] Warning clearing old chunks: {e}")

        # 3. Cohere Cloud Embedding Pipeline
        batch_size = 90
        url = "https://api.cohere.ai/v1/embed"
        headers = {
            "Authorization": f"Bearer {settings.cohere_api_key}",
            "Content-Type": "application/json",
        }

        log_update(ticker_upper, f"Total chunks to process: {len(chunks)}. Starting embedding...")

        for idx in range(0, len(chunks), batch_size):
            batch_chunks = chunks[idx : idx + batch_size]

            payload = {
                "texts": batch_chunks,
                "model": "embed-english-v3.0",
                "input_type": "search_document",
            }

            response = None
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=30)
                    if response.status_code == 429 or "rate limit" in response.text.lower():
                        wait_secs = 60
                        log_update(
                            ticker_upper,
                            f"Cohere rate limit reached (Attempt {attempt + 1}/{max_attempts}). Cooling down {wait_secs}s...",
                        )
                        time.sleep(wait_secs)
                        continue
                    break
                except requests.RequestException as req_err:
                    if attempt < max_attempts - 1:
                        time.sleep(5 * (attempt + 1))
                        continue
                    raise Exception(f"Cohere network request failed: {req_err}")

            if response is None or response.status_code != 200:
                err_body = response.text if response is not None else "No response"
                raise Exception(f"Cohere Cloud API Error: {err_body}")

            embeddings = response.json().get("embeddings", [])
            if len(embeddings) != len(batch_chunks):
                raise Exception(
                    f"Cohere returned mismatched embedding count ({len(embeddings)} vs {len(batch_chunks)})."
                )

            # Map text chunks and corresponding vectors to the Postgres Schema
            db_payloads = []
            for i, chunk_text in enumerate(batch_chunks):
                db_payloads.append({
                    "filing_id": filing_id,
                    "ticker": ticker_upper,
                    "chunk_content": chunk_text,
                    "embedding": embeddings[i],
                    "page_number": idx + i + 1,
                })

            # Fire the batch directly into pgvector
            supabase_client.table("soc_filing_chunks").insert(db_payloads).execute()
            log_update(ticker_upper, f"Successfully inserted chunks {idx} to {idx + len(batch_chunks)}")

        # Signal that the filing is fully vectorized
        supabase_client.table("soc_sec_filings").update({"is_ready": True}).eq("id", filing_id).execute()
        log_update(ticker_upper, "Deep Research is Ready to be Initiated!")
        return {"status": "success", "total_chunks_embedded": len(chunks)}