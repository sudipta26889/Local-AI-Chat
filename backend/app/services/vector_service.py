from typing import List, Dict, Any, Optional, Tuple
from uuid import uuid4
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    SearchRequest, ScoredPoint
)
from loguru import logger

from app.config import settings
from app.services.llm_service import LLMService


class VectorService:
    """Service for Qdrant vector database operations"""
    
    def __init__(self, llm_service: Optional[LLMService] = None):
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None
        )
        self.collection_name = settings.qdrant_collection_name
        self.vector_size = settings.embedding_dimension
        self.llm_service = llm_service
    
    async def initialize(self):
        """Initialize vector service and ensure collection exists"""
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if self.collection_name not in collection_names:
                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"Qdrant collection exists: {self.collection_name}")
                
        except Exception as e:
            logger.warning(f"Qdrant initialization failed (continuing without vector search): {e}")
            self.client = None
    
    async def create_embedding(self, text: str) -> List[float]:
        """Create embedding for text using LLM service"""
        if not self.llm_service:
            raise Exception("LLM service not available for embeddings")
        
        try:
            embedding = await self.llm_service.create_embeddings(text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")
            raise
    
    async def store_message_embedding(
        self,
        message_id: str,
        user_id: str,
        chat_id: str,
        content: str,
        role: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store message embedding in Qdrant"""
        if not self.client:
            logger.warning("Qdrant client not available, skipping embedding storage")
            return str(uuid4())  # Return dummy ID
            
        try:
            # Create embedding
            embedding = await self.create_embedding(content)
            
            # Generate unique vector ID
            vector_id = str(uuid4())
            
            # Prepare payload
            payload = {
                "message_id": message_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "content": content[:1000],  # Store first 1000 chars
                "role": role,
                "timestamp": datetime.utcnow().isoformat(),
                **(metadata or {})
            }
            
            # Create point
            point = PointStruct(
                id=vector_id,
                vector=embedding,
                payload=payload
            )
            
            # Upsert to collection
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.info(f"Stored embedding for message {message_id}")
            return vector_id
            
        except Exception as e:
            logger.error(f"Failed to store message embedding: {e}")
            return str(uuid4())  # Return dummy ID instead of raising
    
    async def search_similar_messages(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
        chat_id: Optional[str] = None,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar messages"""
        if not self.client:
            logger.warning("Qdrant client not available, returning empty search results")
            return []
            
        try:
            # Create query embedding
            query_embedding = await self.create_embedding(query)
            
            # Build filter
            must_conditions = [
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            ]
            
            if chat_id:
                must_conditions.append(
                    FieldCondition(
                        key="chat_id",
                        match=MatchValue(value=chat_id)
                    )
                )
            
            # Search
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=Filter(must=must_conditions),
                limit=limit,
                score_threshold=threshold
            )
            
            # Format results
            similar_messages = []
            for result in results:
                similar_messages.append({
                    "message_id": result.payload.get("message_id"),
                    "chat_id": result.payload.get("chat_id"),
                    "content": result.payload.get("content"),
                    "role": result.payload.get("role"),
                    "timestamp": result.payload.get("timestamp"),
                    "score": result.score
                })
            
            return similar_messages
            
        except Exception as e:
            logger.error(f"Failed to search similar messages: {e}")
            return []
    
    async def get_relevant_context(
        self,
        query: str,
        user_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get relevant context from all user's conversations"""
        try:
            # Search across all user's chats
            results = await self.search_similar_messages(
                query=query,
                user_id=user_id,
                limit=limit,
                threshold=0.6  # Lower threshold for context
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get relevant context: {e}")
            return []
    
    async def delete_chat_embeddings(self, chat_id: str) -> bool:
        """Delete all embeddings for a chat"""
        try:
            # Delete points by filter
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="chat_id",
                            match=MatchValue(value=chat_id)
                        )
                    ]
                )
            )
            
            logger.info(f"Deleted embeddings for chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete chat embeddings: {e}")
            return False
    
    async def delete_user_embeddings(self, user_id: str) -> bool:
        """Delete all embeddings for a user"""
        try:
            # Delete points by filter
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="user_id",
                            match=MatchValue(value=user_id)
                        )
                    ]
                )
            )
            
            logger.info(f"Deleted embeddings for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete user embeddings: {e}")
            return False
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the vector collection"""
        try:
            info = self.client.get_collection(self.collection_name)
            
            return {
                "name": info.name,
                "vector_size": info.config.params.vectors.size,
                "distance": info.config.params.vectors.distance,
                "points_count": info.points_count,
                "status": info.status
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}