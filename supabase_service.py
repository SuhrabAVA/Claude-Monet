import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

# Load .env if present (safe in prod)
load_dotenv()


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def supabase_enabled() -> bool:
    return bool(_env("SUPABASE_URL") and _env("SUPABASE_ANON_KEY"))


_client: Optional[Client] = None


def get_client() -> Client:
    """Create a singleton Supabase client."""
    global _client
    if _client is not None:
        return _client

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY in environment or .env"
        )

    _client = create_client(url, key)
    return _client


# ---------------------------
#   CATEGORIES + MENU ITEMS
# ---------------------------

def list_categories() -> List[Dict[str, Any]]:
    sb = get_client()
    res = sb.table("categories").select("*").order("id").execute()
    return res.data or []


def list_menu_items() -> List[Dict[str, Any]]:
    sb = get_client()
    res = sb.table("menu_items").select("*").order("id").execute()
    return res.data or []


def upsert_category(slug: str, label: str) -> Dict[str, Any]:
    sb = get_client()
    payload = {"slug": slug, "label": label}
    res = sb.table("categories").upsert(payload, on_conflict="slug").execute()
    return (res.data or [{}])[0]


def insert_menu_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    sb = get_client()
    res = sb.table("menu_items").insert(payload).execute()
    return (res.data or [{}])[0]


def get_menu_item(item_id: int) -> Optional[Dict[str, Any]]:
    sb = get_client()
    res = sb.table("menu_items").select("*").eq("id", item_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


# ---------------------------
#           BOOKINGS
# ---------------------------

def insert_booking(payload: Dict[str, Any]) -> Dict[str, Any]:
    sb = get_client()
    res = sb.table("bookings").insert(payload).execute()
    return (res.data or [{}])[0]


def insert_booking_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
    sb = get_client()
    res = sb.table("booking_items").insert(items).execute()
    return res.data or []


def list_bookings() -> List[Dict[str, Any]]:
    sb = get_client()
    res = sb.table("bookings").select("*").order("id", desc=True).execute()
    return res.data or []


def get_booking(booking_id: int) -> Optional[Dict[str, Any]]:
    sb = get_client()
    res = sb.table("bookings").select("*").eq("id", booking_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


def list_booking_items(booking_id: int) -> List[Dict[str, Any]]:
    sb = get_client()
    res = sb.table("booking_items").select("*").eq("booking_id", booking_id).order("id").execute()
    return res.data or []
