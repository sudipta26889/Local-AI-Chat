from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.models.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ldap_uid = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255))
    display_name = Column(String(255))
    preferences = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.display_name or self.ldap_uid}>"
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "ldap_uid": self.ldap_uid,
            "email": self.email,
            "display_name": self.display_name,
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }