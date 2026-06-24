import requests
from app.config import settings
from app.database import supabase_client
from datetime import datetime

class FredService:
    @staticmethod
    def fetch_and_store_macro_data():
        print("Waking up FRED Macro Collector...")
        
        # The specific data series we care about for algorithmic trading
        series_map = {
            "CPIAUCSL": "Inflation (CPI)",
            "GDP": "Gross Domestic Product",
            "UNRATE": "Unemployment Rate",
            "FEDFUNDS": "Fed Funds Interest Rate"
        }
        
        payloads = []
        
        for series_id, indicator_name in series_map.items():
            print(f"Pulling latest data for {indicator_name}...")
            
            # FRED API Endpoint for fetching the latest observations
            url = f"https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": settings.fred_api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1  # We only need the most recent release
            }
            
            try:
                response = requests.get(url, params=params)
                if response.status_code != 200:
                    print(f"Failed to fetch {indicator_name} from FRED.")
                    continue
                    
                data = response.json()
                observations = data.get("observations", [])
                
                if not observations:
                    continue
                    
                latest_obs = observations[0]
                
                payloads.append({
                    "event_name": indicator_name,
                    "released_at": latest_obs.get("date"), # Fixed column name
                    "actual_value": float(latest_obs.get("value", 0.0))
                })
                
            except Exception as e:
                print(f"FRED API Error for {series_id}: {e}")

        if payloads:
            print(f"Pushing {len(payloads)} macroeconomic indicators to Supabase...")
            try:
                response = supabase_client.table("soc_economic_events").upsert(
                    payloads, on_conflict="event_name,released_at" # Fixed variable name
                ).execute()
                
                return {"status": "success", "data_inserted": len(payloads)}
            except Exception as e:
                raise Exception(f"Supabase Database Error: {str(e)}")
        
        return {"status": "no new data"}