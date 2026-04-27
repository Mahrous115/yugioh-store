"""Singleton Supabase client using the service-role key.

The service key bypasses Row Level Security, so this client is only used
server-side in the FastAPI app — never exposed to the browser.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_url: str = os.environ["SUPABASE_URL"]
_key: str = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(_url, _key)
