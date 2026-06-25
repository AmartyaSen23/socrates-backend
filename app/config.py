from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    cohere_api_key: str
    fred_api_key: str
    groq_api_key: str
    alpaca_api_key: str
    alpaca_secret: str

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()