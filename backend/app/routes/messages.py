from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime
import uuid

from app.models.database import get_db
from app.models.chat import Chat
from app.models.message import Message, MessageRole, Attachment
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.llm_service import LLMService
from app.services.vector_service import VectorService
from app.services.storage_service import StorageService
from app.services.context_service import ContextService
from loguru import logger


router = APIRouter()


class SendMessageRequest(BaseModel):
    content: str
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


class MessageResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    id: str
    chat_id: str
    role: str
    content: str
    model_used: Optional[str]
    tokens_used: Optional[int]
    created_at: str
    attachments: Optional[List[dict]] = []


class SearchRequest(BaseModel):
    query: str
    chat_id: Optional[str] = None
    limit: int = 10


@router.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0
):
    """Get messages for a chat"""
    # Verify chat ownership
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )
    
    # Get messages
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(Message.attachments))
    )
    messages = result.scalars().all()
    
    # Format response
    return [
        MessageResponse(
            id=str(msg.id),
            chat_id=str(msg.chat_id),
            role=msg.role.value,
            content=msg.content,
            model_used=msg.model_used,
            tokens_used=msg.tokens_used,
            created_at=msg.created_at.isoformat(),
            attachments=[att.to_dict() for att in msg.attachments]
        )
        for msg in messages
    ]


@router.post("/chats/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    chat_id: str,
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a message and get AI response (non-streaming)"""
    # Verify chat ownership
    result = await db.execute(
        select(Chat)
        .where(Chat.id == chat_id, Chat.user_id == current_user.id)
        .options(selectinload(Chat.messages))
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )
    
    # Create user message
    user_message = Message(
        chat_id=chat.id,
        role=MessageRole.USER,
        content=request.content,
        metadata={"temperature": request.temperature}
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    
    # Store embedding for user message
    vector_service = VectorService()
    try:
        await vector_service.store_message_embedding(
            message_id=str(user_message.id),
            user_id=str(current_user.id),
            chat_id=str(chat.id),
            content=user_message.content,
            role=user_message.role.value
        )
    except Exception as e:
        logger.error(f"Failed to store embedding: {e}")
    
    # Build context
    context_service = ContextService()
    messages = chat.messages + [user_message]
    context = context_service.build_messages_context(
        messages=messages,
        system_prompt=chat.system_prompt
    )
    
    # Get AI response
    llm_service = LLMService()
    model = request.model or chat.model_preferences.get("default_model") or settings.default_model
    
    try:
        response = await llm_service.generate_response(
            messages=context,
            model=model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        # Create assistant message
        assistant_message = Message(
            chat_id=chat.id,
            role=MessageRole.ASSISTANT,
            content=response.get("message", {}).get("content", ""),
            model_used=model,
            tokens_used=response.get("eval_count", 0) + response.get("prompt_eval_count", 0),
            metadata={
                "temperature": request.temperature,
                "eval_count": response.get("eval_count", 0),
                "prompt_eval_count": response.get("prompt_eval_count", 0)
            }
        )
        db.add(assistant_message)
        
        # Update chat timestamp
        chat.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(assistant_message)
        
        # Store embedding for assistant message
        try:
            await vector_service.store_message_embedding(
                message_id=str(assistant_message.id),
                user_id=str(current_user.id),
                chat_id=str(chat.id),
                content=assistant_message.content,
                role=assistant_message.role.value
            )
        except Exception as e:
            logger.error(f"Failed to store assistant embedding: {e}")
        
        return MessageResponse(
            id=str(assistant_message.id),
            chat_id=str(assistant_message.chat_id),
            role=assistant_message.role.value,
            content=assistant_message.content,
            model_used=assistant_message.model_used,
            tokens_used=assistant_message.tokens_used,
            created_at=assistant_message.created_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to generate AI response: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI response: {str(e)}"
        )


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a message"""
    # Get message with chat info
    result = await db.execute(
        select(Message)
        .join(Chat)
        .where(Message.id == message_id, Chat.user_id == current_user.id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    await db.delete(message)
    await db.commit()
    
    return {"message": "Message deleted successfully"}


@router.post("/search", response_model=List[dict])
async def search_messages(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search messages using semantic search"""
    vector_service = VectorService()
    
    # Search similar messages
    results = await vector_service.search_similar_messages(
        query=request.query,
        user_id=str(current_user.id),
        chat_id=request.chat_id,
        limit=request.limit
    )
    
    return results


@router.post("/{message_id}/attachments")
async def upload_attachment(
    message_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload attachment for a message"""
    # Verify message ownership
    result = await db.execute(
        select(Message)
        .join(Chat)
        .where(Message.id == message_id, Chat.user_id == current_user.id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Upload file to MinIO
    storage_service = StorageService()
    object_name = f"users/{current_user.id}/chats/{message.chat_id}/{message_id}/{file.filename}"
    
    try:
        # Read file content
        content = await file.read()
        
        # Upload to MinIO
        stored_name = storage_service.upload_file(
            file_data=io.BytesIO(content),
            object_name=object_name,
            content_type=file.content_type
        )
        
        # Create attachment record
        attachment = Attachment(
            message_id=message.id,
            file_name=file.filename,
            file_type=file.content_type,
            file_size=len(content),
            minio_object_name=stored_name
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)
        
        return {
            "id": str(attachment.id),
            "file_name": attachment.file_name,
            "file_type": attachment.file_type,
            "file_size": attachment.file_size,
            "created_at": attachment.created_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to upload attachment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload attachment"
        )


# Import at the end to avoid circular imports
import io
from app.config import settings