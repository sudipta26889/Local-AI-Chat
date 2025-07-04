from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from loguru import logger

from app.models.message import Message, MessageRole
from app.services.llm_service import LLMService


class ContextService:
    """Service for managing conversation context"""
    
    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service
        self.max_tokens = 4000  # Default context window
        self.summary_threshold = 3000  # When to start summarizing
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)"""
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4
    
    def build_messages_context(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Build context from messages list"""
        max_tokens = max_tokens or self.max_tokens
        context_messages = []
        
        # Add system prompt if provided
        if system_prompt:
            context_messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        # Convert messages to format expected by LLM
        for message in messages:
            context_messages.append({
                "role": message.role.value,
                "content": message.content
            })
        
        # Check if we need to compress context
        total_tokens = sum(self.estimate_tokens(msg["content"]) for msg in context_messages)
        
        if total_tokens > max_tokens:
            return self._compress_context(context_messages, max_tokens)
        
        return context_messages
    
    def _compress_context(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int
    ) -> List[Dict[str, str]]:
        """Compress context using sliding window and summarization"""
        # Keep system message if present
        compressed = []
        system_message = None
        
        if messages and messages[0]["role"] == "system":
            system_message = messages[0]
            messages = messages[1:]
            compressed.append(system_message)
        
        # Keep most recent messages that fit in context
        recent_messages = []
        tokens_used = self.estimate_tokens(system_message["content"]) if system_message else 0
        
        # Iterate from most recent to oldest
        for message in reversed(messages):
            message_tokens = self.estimate_tokens(message["content"])
            if tokens_used + message_tokens <= max_tokens:
                recent_messages.insert(0, message)
                tokens_used += message_tokens
            else:
                break
        
        # If we have older messages, consider summarizing them
        if len(recent_messages) < len(messages):
            older_messages = messages[:len(messages) - len(recent_messages)]
            
            # Group older messages into conversation chunks
            if self.llm_service and len(older_messages) > 4:
                summary = self._create_summary(older_messages)
                if summary:
                    compressed.append({
                        "role": "system",
                        "content": f"Previous conversation summary: {summary}"
                    })
        
        compressed.extend(recent_messages)
        return compressed
    
    def _create_summary(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Create summary of messages (synchronous for now)"""
        # TODO: Make this async in production
        try:
            summary_prompt = [
                {
                    "role": "system",
                    "content": "Summarize the following conversation concisely, preserving key information and context:"
                }
            ]
            summary_prompt.extend(messages)
            summary_prompt.append({
                "role": "user",
                "content": "Please provide a concise summary of the above conversation."
            })
            
            # This is a simplified version - in production, this should be async
            logger.info(f"Creating summary for {len(messages)} messages")
            return "Conversation summary placeholder"  # Implement actual summarization
            
        except Exception as e:
            logger.error(f"Failed to create summary: {e}")
            return None
    
    def extract_context_window(
        self,
        messages: List[Message],
        target_message_id: str,
        window_size: int = 10
    ) -> List[Message]:
        """Extract a window of messages around a target message"""
        target_index = None
        
        for i, msg in enumerate(messages):
            if str(msg.id) == target_message_id:
                target_index = i
                break
        
        if target_index is None:
            return []
        
        start_index = max(0, target_index - window_size // 2)
        end_index = min(len(messages), target_index + window_size // 2 + 1)
        
        return messages[start_index:end_index]
    
    def merge_contexts(
        self,
        primary_context: List[Dict[str, str]],
        additional_context: List[Dict[str, str]],
        max_tokens: int
    ) -> List[Dict[str, str]]:
        """Merge two contexts while respecting token limit"""
        merged = primary_context.copy()
        tokens_used = sum(self.estimate_tokens(msg["content"]) for msg in merged)
        
        for msg in additional_context:
            msg_tokens = self.estimate_tokens(msg["content"])
            if tokens_used + msg_tokens <= max_tokens:
                # Check if message already exists to avoid duplicates
                if not any(m["content"] == msg["content"] for m in merged):
                    merged.append(msg)
                    tokens_used += msg_tokens
            else:
                break
        
        return merged
    
    def format_for_export(self, messages: List[Message]) -> str:
        """Format messages for export"""
        formatted = []
        
        for msg in messages:
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            role = msg.role.value.capitalize()
            formatted.append(f"[{timestamp}] {role}: {msg.content}")
            
            if msg.model_used:
                formatted.append(f"  (Model: {msg.model_used})")
            
            formatted.append("")  # Empty line between messages
        
        return "\n".join(formatted)