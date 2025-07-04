import json
import asyncio
from typing import Optional, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from loguru import logger

from app.models.database import get_db
from app.models.chat import Chat
from app.models.message import Message, MessageRole
from app.models.user import User
from app.auth.jwt_handler import JWTHandler
from app.services.llm_service import LLMService
from app.services.vector_service import VectorService
from app.services.context_service import ContextService
from app.services.cache_service import CacheService


router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections with heartbeat and health monitoring"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_health: Dict[str, datetime] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self.heartbeat_interval = 30  # seconds
        self.connection_timeout = 90  # seconds
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_health[client_id] = datetime.utcnow()
        
        # Start heartbeat task
        task = asyncio.create_task(self._heartbeat_task(websocket, client_id))
        self.heartbeat_tasks[client_id] = task
        
        logger.info(f"WebSocket connected: {client_id}")
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.connection_health:
            del self.connection_health[client_id]
        if client_id in self.heartbeat_tasks:
            task = self.heartbeat_tasks[client_id]
            if not task.done():
                task.cancel()
            del self.heartbeat_tasks[client_id]
        logger.info(f"WebSocket disconnected: {client_id}")
    
    async def send_json(self, websocket: WebSocket, data: dict):
        try:
            # Check if websocket is still connected before sending
            if websocket.client_state.name == 'DISCONNECTED':
                logger.warning("Attempted to send message to disconnected WebSocket")
                return False
                
            await websocket.send_json(data)
            return True
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {e}")
            return False
    
    async def send_error(self, websocket: WebSocket, error: str):
        await self.send_json(websocket, {
            "type": "error",
            "error": error
        })
    
    async def _heartbeat_task(self, websocket: WebSocket, client_id: str):
        """Send periodic heartbeat to keep connection alive"""
        try:
            while client_id in self.active_connections:
                await asyncio.sleep(self.heartbeat_interval)
                
                # Check if connection is still alive
                if client_id not in self.active_connections:
                    break
                
                # Send ping
                success = await self.send_json(websocket, {
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                if not success:
                    logger.warning(f"Heartbeat failed for {client_id}, disconnecting")
                    self.disconnect(client_id)
                    break
                    
        except asyncio.CancelledError:
            logger.debug(f"Heartbeat task cancelled for {client_id}")
        except Exception as e:
            logger.error(f"Heartbeat task error for {client_id}: {e}")
            self.disconnect(client_id)
    
    def update_health(self, client_id: str):
        """Update last seen time for a connection"""
        if client_id in self.connection_health:
            self.connection_health[client_id] = datetime.utcnow()
    
    def is_connection_healthy(self, client_id: str) -> bool:
        """Check if connection is healthy based on last activity"""
        if client_id not in self.connection_health:
            return False
        
        last_seen = self.connection_health[client_id]
        timeout_threshold = datetime.utcnow() - timedelta(seconds=self.connection_timeout)
        return last_seen > timeout_threshold


# Global connection manager
manager = ConnectionManager()


async def get_current_user_ws(
    token: str,
    db: AsyncSession
) -> Optional[User]:
    """Get current user from WebSocket token"""
    jwt_handler = JWTHandler(CacheService())
    
    payload = jwt_handler.verify_token(token)
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


@router.websocket("/chat/{chat_id}")
async def websocket_chat(
    websocket: WebSocket,
    chat_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """WebSocket endpoint for streaming chat"""
    # Authenticate user
    user = await get_current_user_ws(token, db)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    
    # Connect WebSocket
    client_id = f"{user.id}:{chat_id}"
    await manager.connect(websocket, client_id)
    
    try:
        # Verify chat ownership
        result = await db.execute(
            select(Chat)
            .where(Chat.id == chat_id, Chat.user_id == user.id)
            .options(selectinload(Chat.messages))
        )
        chat = result.scalar_one_or_none()
        
        if not chat:
            await manager.send_error(websocket, "Chat not found")
            await websocket.close(code=4004, reason="Chat not found")
            return
        
        # Send initial connection success
        await manager.send_json(websocket, {
            "type": "connected",
            "chat_id": chat_id,
            "user_id": str(user.id)
        })
        
        # Initialize services
        llm_service = LLMService()
        vector_service = VectorService()
        context_service = ContextService()
        
        # Listen for messages
        while True:
            try:
                # Receive message with timeout
                try:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=120.0)
                except asyncio.TimeoutError:
                    logger.warning(f"WebSocket receive timeout for {client_id}")
                    # Check if connection is still healthy
                    if not manager.is_connection_healthy(client_id):
                        logger.info(f"Connection unhealthy, disconnecting {client_id}")
                        break
                    continue
                
                # Update connection health on any message
                manager.update_health(client_id)
                
                if data.get("type") == "message":
                    content = data.get("content", "")
                    model = data.get("model") or chat.model_preferences.get("default_model")
                    temperature = data.get("temperature", 0.7)
                    max_tokens = data.get("max_tokens")
                    
                    # Create user message
                    user_message = Message(
                        chat_id=chat.id,
                        role=MessageRole.USER,
                        content=content,
                        metadata={"temperature": temperature}
                    )
                    db.add(user_message)
                    await db.commit()
                    await db.refresh(user_message)
                    
                    # Send user message confirmation
                    await manager.send_json(websocket, {
                        "type": "user_message",
                        "message_id": str(user_message.id),
                        "content": content,
                        "created_at": user_message.created_at.isoformat()
                    })
                    
                    # Store embedding asynchronously
                    try:
                        await vector_service.store_message_embedding(
                            message_id=str(user_message.id),
                            user_id=str(user.id),
                            chat_id=str(chat.id),
                            content=content,
                            role=MessageRole.USER
                        )
                    except Exception as e:
                        logger.error(f"Failed to store user embedding: {e}")
                    
                    # Build context
                    messages = await db.execute(
                        select(Message)
                        .where(Message.chat_id == chat_id)
                        .order_by(Message.created_at.asc())
                    )
                    all_messages = messages.scalars().all()
                    
                    context = context_service.build_messages_context(
                        messages=all_messages,
                        system_prompt=chat.system_prompt
                    )
                    
                    # Create assistant message placeholder
                    assistant_message = Message(
                        chat_id=chat.id,
                        role=MessageRole.ASSISTANT,
                        content="",
                        model_used=model,
                        metadata={"temperature": temperature}
                    )
                    db.add(assistant_message)
                    await db.commit()
                    await db.refresh(assistant_message)
                    
                    # Send streaming start
                    logger.info(f"Starting stream for message {assistant_message.id} with model {model}")
                    await manager.send_json(websocket, {
                        "type": "stream_start",
                        "message_id": str(assistant_message.id)
                    })
                    
                    # Stream response
                    full_response = ""
                    tokens_used = 0
                    
                    try:
                        # First, let's collect the ENTIRE response without streaming
                        # This ensures we get the complete response from Ollama
                        logger.info(f"Collecting complete response from LLM for message {assistant_message.id}")
                        
                        async for chunk in llm_service.stream_response(
                            messages=context,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens
                        ):
                            full_response += chunk
                            tokens_used += 1
                            
                            # Send chunk immediately for real-time feedback
                            await manager.send_json(websocket, {
                                "type": "stream_chunk",
                                "message_id": str(assistant_message.id),
                                "content": chunk
                            })
                            
                            # Small delay to prevent overwhelming
                            if tokens_used % 5 == 0:
                                await asyncio.sleep(0.001)
                        
                        logger.info(f"LLM streaming completed, collected {len(full_response)} characters, {tokens_used} tokens")
                        
                        # Update assistant message
                        assistant_message.content = full_response
                        assistant_message.tokens_used = tokens_used
                        
                        # Update chat timestamp
                        chat.updated_at = datetime.utcnow()
                        
                        await db.commit()
                        
                        # Send stream end with complete response as backup
                        logger.info(f"Completed stream for message {assistant_message.id}, tokens: {tokens_used}, length: {len(full_response)}")
                        
                        # Send the complete response in the stream_end to ensure nothing is lost
                        await manager.send_json(websocket, {
                            "type": "stream_end",
                            "message_id": str(assistant_message.id),
                            "content": full_response,  # Include complete response as backup
                            "tokens_used": tokens_used,
                            "complete": True  # Flag to indicate this is the final complete response
                        })
                        
                        # Also send a final completion chunk with full response as absolute fallback
                        await manager.send_json(websocket, {
                            "type": "stream_complete",
                            "message_id": str(assistant_message.id),
                            "full_content": full_response,
                            "final": True
                        })
                        
                        # Store assistant embedding asynchronously
                        try:
                            await vector_service.store_message_embedding(
                                message_id=str(assistant_message.id),
                                user_id=str(user.id),
                                chat_id=str(chat.id),
                                content=full_response,
                                role=MessageRole.ASSISTANT
                            )
                        except Exception as e:
                            logger.error(f"Failed to store assistant embedding: {e}")
                        
                    except Exception as e:
                        logger.error(f"Streaming error: {e}")
                        await manager.send_json(websocket, {
                            "type": "stream_error",
                            "message_id": str(assistant_message.id),
                            "error": str(e)
                        })
                        
                        # Delete failed message
                        await db.delete(assistant_message)
                        await db.commit()
                
                elif data.get("type") == "ping":
                    # Handle ping from client - respond with pong
                    await manager.send_json(websocket, {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                elif data.get("type") == "pong":
                    # Handle pong from client (response to our ping)
                    logger.debug(f"Received pong from {client_id}")
                    manager.update_health(client_id)
                
                else:
                    logger.warning(f"Unknown message type: {data.get('type')} from {client_id}")
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected normally: {client_id}")
                break
            except asyncio.CancelledError:
                logger.info(f"WebSocket task cancelled: {client_id}")
                break
            except Exception as e:
                logger.error(f"WebSocket message handling error: {e}")
                # Try to send error, but don't fail if connection is broken
                try:
                    await manager.send_error(websocket, f"Message handling error: {str(e)}")
                except:
                    logger.debug(f"Could not send error to {client_id}, connection likely broken")
                    break
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        logger.info(f"Cleaning up WebSocket connection: {client_id}")
        manager.disconnect(client_id)
        try:
            # Check if WebSocket is still connected before trying to close
            if hasattr(websocket, 'client_state') and websocket.client_state.name != 'DISCONNECTED':
                await websocket.close(code=1000, reason="Connection closed")
        except Exception as e:
            logger.debug(f"Error closing WebSocket: {e}")