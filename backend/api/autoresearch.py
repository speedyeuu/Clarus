from fastapi import APIRouter, HTTPException
from db.client import get_supabase
from pydantic import BaseModel

router = APIRouter()


class ApprovalRequest(BaseModel):
    log_id: str
    approved: bool


@router.get("/log")
async def get_autoresearch_log(limit: int = 10):
    """Vrátí historii autoresearch návrhů (schválené i čekající)."""
    db = get_supabase()
    result = (
        db.table("autoresearch_log")
        .select("*")
        .order("run_date", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


@router.get("/pending")
async def get_pending_proposals():
    """Vrátí neschválené návrhy čekající na admin schválení."""
    db = get_supabase()
    result = (
        db.table("autoresearch_log")
        .select("*")
        .eq("applied", False)
        .order("run_date", desc=True)
        .execute()
    )
    return result.data


@router.post("/approve")
async def approve_or_reject(request: ApprovalRequest):
    """Schválit nebo zamítnout návrh nových vah."""
    db = get_supabase()

    if request.approved:
        # Načíst nové váhy z logu
        log = db.table("autoresearch_log").select("new_weights").eq("id", request.log_id).single().execute()
        if not log.data:
            raise HTTPException(status_code=404, detail="Návrh nenalezen.")

        new_weights = log.data["new_weights"]

        # Uložit jako aktuální váhy (upsert do tabulky settings)
        db.table("weight_settings").upsert({
            "id": "current",
            "weights": new_weights,
            "updated_at": "now()"
        }).execute()

        # Označit jako aplikované
        db.table("autoresearch_log").update({"applied": True}).eq("id", request.log_id).execute()

        return {"status": "approved", "new_weights": new_weights}
    else:
        # Zamítnout – pouze označit jako reviewed (applied zůstane False, přidáme rejected flag)
        db.table("autoresearch_log").update({"rejected": True}).eq("id", request.log_id).execute()
        return {"status": "rejected"}
