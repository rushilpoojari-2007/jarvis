from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatMessage, Conversation
from app.schemas import ChatMessageCreate
from app.services.agent_service import is_clear_chat_history_command, run_agent
from app.services.vision_service import VisionInputError, VisionProviderError, analyze_image

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _conversation_data(conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


@router.get("/conversations")
async def list_conversations(db: Session = Depends(get_db)):
    conversations = (
        db.query(Conversation)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .all()
    )
    return {"conversations": [_conversation_data(item) for item in conversations]}


@router.post("/conversations")
async def create_conversation(db: Session = Depends(get_db)):
    conversation = Conversation(title="New chat")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {"conversation": _conversation_data(conversation)}


@router.post("/")
async def chat_with_jarvis(
    payload: ChatMessageCreate | None = None,
    message: str | None = None,
    conversation_id: int | None = None,
    db: Session = Depends(get_db),
):
    image_data = None
    if payload is not None:
        message = payload.message
        image_data = payload.image
    message = (message or "").strip()
    if not message and not image_data:
        raise HTTPException(status_code=400, detail="Enter a message or attach an image")
    if image_data and len(image_data) > 7_000_000:
        raise HTTPException(status_code=413, detail="Image is too large. Choose an image smaller than 5 MB.")
    if image_data and not message:
        message = "Describe and review this image. Identify visible content and notable details; if it contains a test or document, read and review the visible text. Do not guess unreadable text."

    conversation = db.get(Conversation, conversation_id) if conversation_id is not None else None
    if conversation_id is not None and conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation is None:
        conversation = (
            db.query(Conversation)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .first()
        )
        if conversation is None:
            conversation = Conversation(title="New chat")
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

    image_url = None
    if image_data:
        try:
            answer, image_url = await analyze_image(image_data, message)
        except VisionInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except VisionProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        answer = await run_agent(message, db, conversation_id=conversation.id)
    if is_clear_chat_history_command(message) and answer == "Chat history cleared.":
        fresh_conversation = Conversation(title="New chat")
        db.add(fresh_conversation)
        db.commit()
        db.refresh(fresh_conversation)
        return {
            "reply": answer,
            "message_id": None,
            "history_cleared": True,
            "conversation": _conversation_data(fresh_conversation),
        }

    if conversation.title == "New chat":
        title = " ".join(message.split())
        conversation.title = title if len(title) <= 48 else f"{title[:45].rstrip()}..."
    conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
    saved_message = f"{message}\n[[JARVIS_UPLOAD:{image_url}]]" if image_url else message
    entry = ChatMessage(message=saved_message, response=answer, conversation_id=conversation.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.refresh(conversation)
    return {
        "reply": answer,
        "message_id": entry.id,
        "history_cleared": False,
        "conversation": _conversation_data(conversation),
        "image_url": image_url,
    }


@router.get("/history")
async def chat_history(conversation_id: int | None = None, db: Session = Depends(get_db)):
    if conversation_id is None:
        conversation = (
            db.query(Conversation)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .first()
        )
        if conversation is None:
            return {"messages": []}
        conversation_id = conversation.id
    elif db.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    entries = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(100)
        .all()
    )
    entries.reverse()
    return {"messages": entries}
