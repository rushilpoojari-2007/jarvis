from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bookmark

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


@router.get("/")
async def list_bookmarks(db: Session = Depends(get_db)):
    items = db.query(Bookmark).order_by(Bookmark.created_at.desc()).all()
    return {"bookmarks": items}


@router.post("/")
async def create_bookmark(title: str | None = None, url: str | None = None, category: str = "general", db: Session = Depends(get_db)):
    if not title or not url:
        raise HTTPException(status_code=400, detail="Title and URL are required")
    item = Bookmark(title=title, url=url, category=category)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"bookmark": item}
