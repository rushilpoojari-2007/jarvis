from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Briefing
from app.services.briefing_service import generate_daily_briefing

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


@router.get("/")
async def get_briefing(db: Session = Depends(get_db)):
    summary = await generate_daily_briefing()
    item = Briefing(title="Daily Briefing", summary=summary)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "title": item.title, "summary": item.summary}


@router.get("/history")
async def get_briefing_history(db: Session = Depends(get_db)):
    items = db.query(Briefing).order_by(Briefing.created_at.desc()).all()
    return {"briefings": items}
