import requests
from app.config import settings
from app.database import supabase_client


class FredService:
    @staticmethod
    def fetch_and_store_macro_data():
        print("Waking up FRED Macro Collector...")

        # Core macroeconomic series tracked for institutional context
        series_map = {
            "CPIAUCSL": "Inflation (CPI)",
            "GDP": "Gross Domestic Product",
            "UNRATE": "Unemployment Rate",
            "FEDFUNDS": "Fed Funds Interest Rate",
        }

        payloads = []
        url = "https://api.stlouisfed.org/fred/series/observations"

        for series_id, indicator_name in series_map.items():
            print(f"Pulling latest data for {indicator_name}...")

            params = {
                "series_id": series_id,
                "api_key": settings.fred_api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 5,  # Fetch top 5 in case the latest unreleased row has value="."
            }

            try:
                response = requests.get(url, params=params, timeout=10)
                if response.status_code != 200:
                    print(f"Failed to fetch {indicator_name} from FRED (HTTP {response.status_code}).")
                    continue

                data = response.json()
                observations = data.get("observations", [])

                valid_obs = None
                for obs in observations:
                    raw_val = obs.get("value")
                    if raw_val is not None and str(raw_val).strip() not in ("", "."):
                        try:
                            float(raw_val)
                            valid_obs = obs
                            break
                        except ValueError:
                            continue

                if not valid_obs:
                    continue

                payloads.append({
                    "event_name": indicator_name,
                    "released_at": valid_obs.get("date"),
                    "actual_value": float(valid_obs["value"]),
                })

            except Exception as e:
                print(f"FRED API Error for {series_id}: {e}")

        if payloads:
            print(f"Pushing {len(payloads)} macroeconomic indicators to Supabase...")
            try:
                supabase_client.table("soc_economic_events").upsert(
                    payloads, on_conflict="event_name,released_at"
                ).execute()
                return {"status": "success", "data_inserted": len(payloads)}
            except Exception as e:
                raise Exception(f"Supabase Database Error: {str(e)}")

        return {"status": "no new data"}