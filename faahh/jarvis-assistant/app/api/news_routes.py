import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bookmark
from app.services.news_service import fetch_news

router = APIRouter(prefix="/api/news", tags=["news"])
logger = logging.getLogger("jarvis.news")


@router.get("/")
async def get_news(
    category: str = Query(default="general"),
    query: str | None = None,
    country: Literal["in", "us", "gb"] = Query(default="in"),
    db: Session = Depends(get_db),
):
    try:
        results = await fetch_news(category=category, query=query, country=country)
        return {"articles": results, "count": len(results), "source": "live" if results else "none"}
    except Exception as exc:
        logger.warning("News lookup failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="News providers could not complete the request.") from None


@router.post("/bookmark")
async def bookmark_article(title: str, url: str, category: str = "general", db: Session = Depends(get_db)):
    if not title or not url:
        raise HTTPException(status_code=400, detail="Title and URL are required")
    item = Bookmark(title=title, url=url, category=category)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "message": "Bookmark saved"}
