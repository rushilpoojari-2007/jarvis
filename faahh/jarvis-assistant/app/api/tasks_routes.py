from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task
from app.schemas import TaskCreate, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/")
async def list_tasks(db: Session = Depends(get_db)):
    items = db.query(Task).order_by(Task.created_at.desc()).all()
    return {"tasks": items}


@router.post("/")
async def create_task(payload: TaskCreate | dict | None = None, db: Session = Depends(get_db)):
    if payload is None:
        raise HTTPException(status_code=400, detail="Task payload is required")
    if isinstance(payload, dict):
        payload = TaskCreate(**payload)
    item = Task(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"task": item}


@router.put("/{task_id}")
async def update_task(task_id: int, payload: TaskUpdate | dict | None = None, db: Session = Depends(get_db)):
    item = db.query(Task).filter(Task.id == task_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload is None:
        raise HTTPException(status_code=400, detail="Task payload is required")
    if isinstance(payload, dict):
        payload = TaskUpdate(**payload)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return {"task": item}


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    item = db.query(Task).filter(Task.id == task_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(item)
    db.commit()
    return {"message": "Task deleted"}
