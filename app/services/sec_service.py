import os
import shutil
import re
from bs4 import BeautifulSoup
from sec_edgar_downloader import Downloader
from app.database import supabase_client
from datetime import datetime
from app.status_store import log_update, get_logs, clear_logs

class SECService:
    @staticmethod
    def fetch_and_store_10k(ticker: str):
        ticker = ticker.upper()
        download_dir = f"./temp_sec_{ticker}"
        dl = Downloader("SocratesResearchEngine", "amar@example.com", download_dir)
        
        # We now support US (10-K), Global Foreign (20-F), and Canadian (40-F)
        form_types = ["10-K", "20-F", "40-F"]
        
        for form in form_types:
            try:
                log_update(ticker, f"Attempting to download {form} for {ticker}...")
                dl.get(form, ticker, limit=1)
                
                target_path = os.path.join(download_dir, "sec-edgar-filings", ticker, form)
                
                if os.path.exists(target_path) and os.listdir(target_path):
                    accession_number = os.listdir(target_path)[0]
                    file_path = os.path.join(target_path, accession_number, "full-submission.txt")
                    
                    if not os.path.exists(file_path):
                        raise FileNotFoundError(f"Download completed but file missing.")
                    
                    # --- THE LOCAL SCRUBBER (Fixes Payload Too Large) ---
                    log_update(ticker, f"Scrubbing {form} locally to bypass storage limits...")
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_text = f.read()
                        
                    # Extract only the actual report, ignoring embedded PDFs/Images
                    doc_match = re.search(r'<TYPE>(10-K|20-F|40-F).*?<TEXT>(.*?)</TEXT>', raw_text, re.IGNORECASE | re.DOTALL)
                    target_html = doc_match.group(2) if doc_match else raw_text
                    
                    # Strip HTML
                    soup = BeautifulSoup(target_html, "html.parser")
                    for script_or_style in soup(["script", "style"]):
                        script_or_style.extract()
                        
                    clean_text = soup.get_text(separator="\n")
                    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text) # Remove massive whitespace
                    
                    # Convert string back to bytes for Supabase upload
                    file_data = clean_text.encode('utf-8')
                    
                    storage_path = f"{ticker}/{form}/{accession_number}.txt"
                    log_update(ticker, f"Uploading clean, compressed {form} text to Supabase...")
                    
                    supabase_client.storage.from_("sec-filings-raw").upload(
                        path=storage_path,
                        file=file_data,
                        file_options={"content-type": "text/plain", "upsert": "true"}
                    )
                    
                    db_res = supabase_client.table("soc_sec_filings").insert({
                        "ticker": ticker,
                        "form_type": form,
                        "filed_at": datetime.today().strftime('%Y-%m-%d'),
                        "storage_bucket_url": storage_path
                    }).execute()
                    
                    return {"status": "success", "form": form, "db_record": db_res.data}
                    
            except Exception as e:
                # If it's just not found, we silently continue to try the next form type
                print(f"Failed {form} for {ticker}: {str(e)}")
                continue
                
            finally:
                if os.path.exists(download_dir):
                    shutil.rmtree(download_dir)
                    
        # If we loop through 10-K, 20-F, and 40-F and STILL find nothing:
        raise Exception("Filing not found or company is not listed on US Exchanges.")