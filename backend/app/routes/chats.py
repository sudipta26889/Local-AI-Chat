from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from datetime import datetime
import uuid

from app.models.database import get_db
from app.models.chat import Chat
from app.models.message import Message, MessageRole
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.vector_service import VectorService
from loguru import logger


router = APIRouter()


class CreateChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    title: str
    system_prompt: Optional[str] = None
    model_preferences: Optional[dict] = {}


class UpdateChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    model_preferences: Optional[dict] = None


class ChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    id: str
    user_id: str
    title: str
    system_prompt: Optional[str]
    model_preferences: dict
    created_at: str
    updated_at: str
    message_count: Optional[int] = 0


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


@router.get("", response_model=List[ChatResponse])
async def list_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """List user's chats"""
    # Query chats with message count
    result = await db.execute(
        select(Chat)
        .where(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(Chat.messages))
    )
    chats = result.scalars().all()
    
    # Format response
    chat_responses = []
    for chat in chats:
        chat_responses.append(ChatResponse(
            id=str(chat.id),
            user_id=str(chat.user_id),
            title=chat.title,
            system_prompt=chat.system_prompt,
            model_preferences=chat.model_preferences or {},
            created_at=chat.created_at.isoformat(),
            updated_at=chat.updated_at.isoformat(),
            message_count=len(chat.messages)
        ))
    
    return chat_responses


@router.post("", response_model=ChatResponse)
async def create_chat(
    request: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new chat"""
    # Ensure model_preferences has a default model
    model_preferences = request.model_preferences or {}
    
    # If no default model is set, use the system default
    if not model_preferences.get("default_model"):
        from app.services.llm_service import LLMService
        llm_service = LLMService()
        
        # Get default from user preferences or system default
        default_model = (
            current_user.preferences.get("default_model") 
            if current_user.preferences 
            else None
        ) or llm_service.default_model
        
        model_preferences["default_model"] = default_model
    
    chat = Chat(
        user_id=current_user.id,
        title=request.title,
        system_prompt=request.system_prompt,
        model_preferences=model_preferences
    )
    
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    
    logger.info(f"Created chat {chat.id} for user {current_user.ldap_uid}")
    
    return ChatResponse(
        id=str(chat.id),
        user_id=str(chat.user_id),
        title=chat.title,
        system_prompt=chat.system_prompt,
        model_preferences=chat.model_preferences,
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat(),
        message_count=0
    )


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get chat details"""
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
    
    return ChatResponse(
        id=str(chat.id),
        user_id=str(chat.user_id),
        title=chat.title,
        system_prompt=chat.system_prompt,
        model_preferences=chat.model_preferences or {},
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat(),
        message_count=len(chat.messages)
    )


@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
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
    )
    messages = result.scalars().all()
    
    return [
        MessageResponse(
            id=str(msg.id),
            chat_id=str(msg.chat_id),
            role=msg.role.value,
            content=msg.content,
            model_used=msg.model_used,
            tokens_used=msg.tokens_used,
            created_at=msg.created_at.isoformat(),
            attachments=[]
        )
        for msg in messages
    ]


@router.put("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: str,
    request: UpdateChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update chat details"""
    result = await db.execute(
        select(Chat)
        .where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )
    
    # Update fields
    if request.title is not None:
        chat.title = request.title
    if request.system_prompt is not None:
        chat.system_prompt = request.system_prompt
    if request.model_preferences is not None:
        chat.model_preferences = request.model_preferences
    
    chat.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(chat)
    
    return ChatResponse(
        id=str(chat.id),
        user_id=str(chat.user_id),
        title=chat.title,
        system_prompt=chat.system_prompt,
        model_preferences=chat.model_preferences or {},
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat()
    )


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a chat and all its messages"""
    # Verify chat ownership
    result = await db.execute(
        select(Chat)
        .where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )
    
    # Delete chat (cascade will delete messages)
    await db.delete(chat)
    await db.commit()
    
    # Delete embeddings from vector store
    vector_service = VectorService()
    await vector_service.delete_chat_embeddings(chat_id)
    
    logger.info(f"Deleted chat {chat_id} for user {current_user.ldap_uid}")
    
    return {"message": "Chat deleted successfully"}


@router.post("/{chat_id}/clear")
async def clear_chat_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Clear all messages in a chat"""
    # Verify chat ownership
    result = await db.execute(
        select(Chat)
        .where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )
    
    # Delete all messages
    await db.execute(
        delete(Message).where(Message.chat_id == chat_id)
    )
    
    # Update chat timestamp
    chat.updated_at = datetime.utcnow()
    
    await db.commit()
    
    # Delete embeddings from vector store
    vector_service = VectorService()
    await vector_service.delete_chat_embeddings(chat_id)
    
    return {"message": "Chat messages cleared successfully"}