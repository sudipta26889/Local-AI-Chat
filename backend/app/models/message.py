from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, String, DateTime, JSON, Text, ForeignKey, Integer
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.models.database import Base


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role = Column(
        SQLEnum(MessageRole, values_callable=lambda x: [e.value for e in x], native_enum=True),
        nullable=False
    )
    content = Column(Text, nullable=False)
    model_used = Column(String(100))
    tokens_used = Column(Integer)
    msg_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    chat = relationship("Chat", back_populates="messages")
    embeddings = relationship("Embedding", back_populates="message", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Message {self.role.value}: {self.content[:50]}...>"
    
    def to_dict(self, include_attachments=False):
        data = {
            "id": str(self.id),
            "chat_id": str(self.chat_id),
            "role": self.role.value,
            "content": self.content,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "metadata": self.msg_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_attachments and self.attachments:
            data["attachments"] = [att.to_dict() for att in self.attachments]
        
        return data


class Embedding(Base):
    __tablename__ = "embeddings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    vector_id = Column(String(255), nullable=False)
    collection_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    message = relationship("Message", back_populates="embeddings")
    
    def __repr__(self):
        return f"<Embedding {self.vector_id}>"


class Attachment(Base):
    __tablename__ = "attachments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(100))
    file_size = Column(Integer)
    minio_object_name = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    message = relationship("Message", back_populates="attachments")
    
    def __repr__(self):
        return f"<Attachment {self.file_name}>"
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "message_id": str(self.message_id),
            "file_name": self.file_name,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }