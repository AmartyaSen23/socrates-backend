import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Optional
from bs4 import BeautifulSoup
from sec_edgar_downloader import Downloader
from app.database import supabase_client
from app.status_store import log_update, try_acquire_vectorization, release_vectorization


class SECService:
    @staticmethod
    def extract_debt_from_text(text: str) -> Optional[int]:
        """
        Attempts to extract Total Debt from SEC prose using strict contextual Regex.
        Avoids false positives on years (e.g., '2026') or footnote numbers.
        """
        pattern = (
            r"total\s+debt\b[^.\n$]{0,50}?"
            r"(?:\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|trillion)?|"
            r"([\d,]+(?:\.\d+)?)\s+(million|billion|trillion))"
        )
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                val_str = (match.group(1) or match.group(3) or "").replace(",", "").strip()
                mult_str = (match.group(2) or match.group(4) or "").lower().strip()
                if not val_str:
                    continue

                val = float(val_str)
                # Guard against matching calendar years like 2024, 2025, 2026 when no unit multiplier exists
                if not mult_str and 1990 <= val <= 2100:
                    continue

                if mult_str == "million":
                    val *= 1_000_000
                elif mult_str == "billion":
                    val *= 1_000_000_000
                elif mult_str == "trillion":
                    val *= 1_000_000_000_000
                elif val < 100_000:
                    # Ignore small bare numbers (e.g., table note references)
                    continue

                if val > 0:
                    return int(round(val))
            except ValueError:
                continue
        return None

    @staticmethod
    def fetch_and_store_10k(ticker: str, preferred_form: Optional[str] = None):
        ticker = re.sub(r"[^A-Z0-9.\-]", "", ticker.strip().upper())
        if not ticker:
            raise ValueError("Invalid ticker symbol provided for SEC download.")

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Support US (10-K), Global Foreign (20-F), Canadian (40-F), and quarterly (10-Q) if requested
        default_forms = ["10-K", "20-F", "40-F"]
        if preferred_form and preferred_form in ["10-K", "20-F", "40-F", "10-Q"]:
            form_types = [preferred_form] + [f for f in default_forms if f != preferred_form]
        else:
            form_types = default_forms

        for form in form_types:
            download_dir = tempfile.mkdtemp(prefix=f"sec_{ticker}_")
            try:
                dl = Downloader("SocratesResearchEngine", "amartya@socrates-ai.com", download_dir)
                log_update(ticker, f"Attempting to download {form} for {ticker}...")
                dl.get(form, ticker, limit=1)

                target_path = os.path.join(download_dir, "sec-edgar-filings", ticker, form)

                if os.path.exists(target_path) and os.listdir(target_path):
                    accession_number = os.listdir(target_path)[0]
                    file_path = os.path.join(target_path, accession_number, "full-submission.txt")

                    if not os.path.exists(file_path):
                        raise FileNotFoundError("Download completed but full-submission.txt is missing.")

                    # --- THE LOCAL SCRUBBER (Fixes Payload Too Large & Prevents 512MB RAM OOM) ---
                    log_update(ticker, f"Scrubbing {form} locally to bypass storage limits...")
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_text = f.read()

                    # Extract only the actual report prose, ignoring embedded base64 PDFs/Images/XBRL exhibits
                    doc_match = re.search(
                        r"<DOCUMENT>\s*<TYPE>(?:10-K|20-F|40-F|10-Q).*?<TEXT>(.*?)</TEXT>\s*</DOCUMENT>",
                        raw_text,
                        re.IGNORECASE | re.DOTALL,
                    )
                    if not doc_match:
                        doc_match = re.search(
                            r"<TYPE>(?:10-K|20-F|40-F|10-Q).*?<TEXT>(.*?)</TEXT>",
                            raw_text,
                            re.IGNORECASE | re.DOTALL,
                        )
                    target_html = doc_match.group(1) if doc_match else raw_text
                    del raw_text  # Free raw file buffer immediately

                    # Pre-strip heavy iXBRL hidden headers, scripts, styles, and SVGs before parsing
                    target_html = re.sub(
                        r"<(?:script|style|svg|ix:header|ix:hidden)\b[^>]*>.*?</(?:script|style|svg|ix:header|ix:hidden)>",
                        " ",
                        target_html,
                        flags=re.IGNORECASE | re.DOTALL,
                    )

                    if len(target_html) > 3_000_000:
                        # Fast low-memory HTML stripper for huge iXBRL filings (avoids BeautifulSoup DOM OOM on 512MB cloud instances)
                        import html as html_lib
                        text_with_breaks = re.sub(r"</?(?:p|div|tr|br|li|h[1-6])\b[^>]*>", "\n", target_html, flags=re.IGNORECASE)
                        clean_text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text_with_breaks))
                    else:
                        soup = BeautifulSoup(target_html, "html.parser")
                        clean_text = soup.get_text(separator="\n")
                    del target_html

                    clean_text = re.sub(r"[ \t]+", " ", clean_text)
                    clean_text = re.sub(r"\n\s*\n+", "\n\n", clean_text).strip()

                    if len(clean_text) < 500:
                        raise ValueError(f"Extracted {form} text for {ticker} was empty or corrupted.")

                    # --- ATTEMPT TO BACKFILL DEBT IF MISSING IN FUNDAMENTALS ---
                    extracted_debt = SECService.extract_debt_from_text(clean_text)
                    if extracted_debt is not None:
                        log_update(ticker, f"Extracted Total Debt from {form}: ${extracted_debt:,.0f}")
                        try:
                            supabase_client.table("soc_company_fundamentals").update(
                                {"total_debt": extracted_debt}
                            ).eq("ticker", ticker).eq("fiscal_date", today_str).is_("total_debt", "null").execute()
                        except Exception as e:
                            log_update(ticker, f"Warning: Failed to update debt in DB: {e}")
                    else:
                        log_update(ticker, f"Could not reliably extract Total Debt from {form} prose.")

                    # Convert string back to bytes for Supabase upload
                    file_data = clean_text.encode("utf-8")
                    storage_path = f"{ticker}/{form}/{accession_number}.txt"
                    log_update(ticker, f"Uploading clean, compressed {form} text to Supabase...")

                    supabase_client.storage.from_("sec-filings-raw").upload(
                        path=storage_path,
                        file=file_data,
                        file_options={"content-type": "text/plain", "upsert": "true"},
                    )

                    # Reuse existing filing row if present for this ticker to avoid orphan duplicates
                    existing = (
                        supabase_client.table("soc_sec_filings")
                        .select("id")
                        .eq("ticker", ticker)
                        .order("filed_at", desc=True)
                        .limit(1)
                        .execute()
                    )

                    filing_payload = {
                        "ticker": ticker,
                        "form_type": form,
                        "filed_at": today_str,
                        "storage_bucket_url": storage_path,
                        "is_ready": False,
                    }

                    if existing.data:
                        existing_id = existing.data[0]["id"]
                        db_res = (
                            supabase_client.table("soc_sec_filings")
                            .update(filing_payload)
                            .eq("id", existing_id)
                            .execute()
                        )
                    else:
                        db_res = supabase_client.table("soc_sec_filings").insert(filing_payload).execute()

                    return {"status": "success", "form": form, "db_record": db_res.data}

            except Exception as e:
                print(f"Failed {form} for {ticker}: {str(e)}")
                continue

            finally:
                if os.path.exists(download_dir):
                    shutil.rmtree(download_dir, ignore_errors=True)

        raise Exception("Filing not found or company is not listed on US Exchanges.")

    @staticmethod
    def download_and_vectorize_filing(ticker: str, preferred_form: Optional[str] = None):
        """
        End-to-end helper used by both background tasks and the live SEC RSS listener.
        Coordinates via atomic lock so duplicate vectorization jobs never run concurrently.
        """
        from app.services.vector_service import VectorService

        ticker_upper = ticker.strip().upper()
        if not try_acquire_vectorization(ticker_upper):
            log_update(ticker_upper, "Vectorization already in progress by another worker. Skipping duplicate task.")
            return {"status": "already_running"}

        try:
            sec_data = SECService.fetch_and_store_10k(ticker_upper, preferred_form=preferred_form)
            records = sec_data.get("db_record") or sec_data.get("data") or []
            if isinstance(records, list) and len(records) > 0:
                filing_id = records[0].get("id")
                storage_url = records[0].get("storage_bucket_url")
            else:
                filing_id = sec_data.get("id") or sec_data.get("filing_id")
                storage_url = sec_data.get("storage_bucket_url")

            if not filing_id or not storage_url:
                raise ValueError("Missing filing ID or storage URL in SEC response payload.")

            return VectorService.chunk_and_embed_filing(
                filing_id=filing_id,
                storage_bucket_url=storage_url,
                ticker=ticker_upper,
            )
        finally:
            release_vectorization(ticker_upper)