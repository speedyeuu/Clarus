from fastapi import APIRouter
from db.client import get_supabase
from datetime import date, timedelta

router = APIRouter()


@router.get("/upcoming")
async def get_upcoming_events(days: int = 7, pair: str = "EURUSD"):
    """Vrátí nadcházející ekonomické události z Forex Factory pro daný pár."""
    db = get_supabase()
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=days)).isoformat()

    base = pair[:3].upper()
    quote = pair[3:].upper()

    result = (
        db.table("upcoming_events")
        .select("*")
        .gte("event_date", today)
        .lte("event_date", cutoff)
        .in_("country", [base, quote])
        .order("event_date", desc=False)
        .execute()
    )
    return result.data

