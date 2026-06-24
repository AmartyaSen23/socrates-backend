from supabase import create_client, Client
from app.config import settings

supabase_client: Client = create_client(settings.supabase_url, settings.supabase_key)