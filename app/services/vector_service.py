import requests
import time
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings
from app.database import supabase_client
from app.status_store import log_update

class VectorService:
    @staticmethod
    def chunk_and_embed_filing(filing_id: str, storage_bucket_url: str, ticker: str):
        # 1. Pull down the raw SEC file (which is ALREADY clean prose now!)
        log_update(ticker, "Downloading clean prose filing from storage...")
        file_bytes = supabase_client.storage.from_("sec-filings-raw").download(storage_bucket_url)
        clean_text = file_bytes.decode("utf-8", errors="ignore")

        # 2. Create semantic text windows
        log_update(ticker, "Slicing text into semantic chunks...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=200,
            length_function=len
        )
        chunks = text_splitter.split_text(clean_text)
        
        # 3. Cohere Cloud Embedding Pipeline
        batch_size = 90
        url = "https://api.cohere.ai/v1/embed"
        headers = {
            "Authorization": f"Bearer {settings.cohere_api_key}",
            "Content-Type": "application/json"
        }

        log_update(ticker, f"Total chunks to process: {len(chunks)}. Starting embedding...")

        for idx in range(0, len(chunks), batch_size):
            batch_chunks = chunks[idx : idx + batch_size]
            
            payload = {
                "texts": batch_chunks,
                "model": "embed-english-v3.0",
                "input_type": "search_document"
            }

            response = requests.post(url, json=payload, headers=headers)
            
            # Handle the 100k token/minute rate limit gracefully
            if response.status_code == 429 or "rate limit" in response.text.lower():
                log_update(ticker, f"Token limit reached. Sleeping 60s...")
                time.sleep(60)
                log_update(ticker, "Resuming embedding process...")
                response = requests.post(url, json=payload, headers=headers)

            if response.status_code != 200:
                raise Exception(f"Cohere Cloud API Error: {response.text}")

            embeddings = response.json().get("embeddings", [])
            
            # Map text chunks and corresponding vectors to the Postgres Schema
            db_payloads = []
            for i, chunk_text in enumerate(batch_chunks):
                db_payloads.append({
                    "filing_id": filing_id,
                    "ticker": ticker.upper(),
                    "chunk_content": chunk_text,
                    "embedding": embeddings[i],
                    "page_number": idx + i + 1
                })

            # Fire the batch directly into pgvector
            supabase_client.table("soc_filing_chunks").insert(db_payloads).execute()
            log_update(ticker, f"Successfully inserted chunks {idx} to {idx + len(batch_chunks)}")

        # Signal that the filing is fully vectorized
        supabase_client.table("soc_sec_filings").update({"is_ready": True}).eq("id", filing_id).execute()
        log_update(ticker, "Deep Research is Ready to be Initiated!")
        return {"status": "success", "total_chunks_embedded": len(chunks)}