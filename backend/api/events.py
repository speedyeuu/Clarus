from fastapi import APIRouter
from db.client import get_supabase
from datetime import date, timedelta

router = APIRouter()


@router.get("/upcoming")
async def get_upcoming_events(days: int = 7):
    """Vrátí nadcházející ekonomické události z Forex Factory."""
    db = get_supabase()
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    result = (
        db.table("upcoming_events")
        .select("*")
        .gte("event_date", today)
        .lte("event_date", cutoff)
        .order("event_date", desc=False)
        .execute()
    )
    return result.data
