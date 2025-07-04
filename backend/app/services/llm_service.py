import asyncio
import json
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime
import httpx
from loguru import logger

from app.config import settings
from app.services.cache_service import CacheService


class LLMEndpoint:
    """Represents a single LLM endpoint"""
    
    def __init__(self, url: str):
        self.url = url.rstrip('/')
        self.is_healthy = True
        self.last_check = datetime.utcnow()
        self.response_times: List[float] = []
        self.error_count = 0
    
    @property
    def average_response_time(self) -> float:
        if not self.response_times:
            return 0
        return sum(self.response_times[-10:]) / len(self.response_times[-10:])
    
    def record_response_time(self, time: float):
        self.response_times.append(time)
        if len(self.response_times) > 100:
            self.response_times.pop(0)
    
    def record_error(self):
        self.error_count += 1
        if self.error_count >= 3:
            self.is_healthy = False
    
    def reset_health(self):
        self.is_healthy = True
        self.error_count = 0


class LLMService:
    """Service for managing LLM endpoints and streaming responses"""
    
    def __init__(self, cache_service: Optional[CacheService] = None):
        self.endpoints = [LLMEndpoint(url) for url in settings.llm_endpoints_list]
        self.cache_service = cache_service
        self.default_model = settings.default_model
        self.timeout = settings.model_timeout
        self.streaming_timeout = settings.streaming_timeout
    
    async def list_models(self) -> Dict[str, List[str]]:
        """List available models from all endpoints"""
        all_models = {}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for endpoint in self.endpoints:
                if not endpoint.is_healthy:
                    continue
                
                try:
                    response = await client.get(f"{endpoint.url}/api/tags")
                    if response.status_code == 200:
                        data = response.json()
                        models = [model["name"] for model in data.get("models", [])]
                        all_models[endpoint.url] = models
                except Exception as e:
                    logger.error(f"Failed to fetch models from {endpoint.url}: {e}")
                    endpoint.record_error()
        
        return all_models
    
    def _select_endpoint(self, preferred_endpoint: Optional[str] = None) -> Optional[LLMEndpoint]:
        """Select best available endpoint"""
        if preferred_endpoint:
            for endpoint in self.endpoints:
                if endpoint.url == preferred_endpoint and endpoint.is_healthy:
                    return endpoint
        
        # Select endpoint with lowest average response time
        healthy_endpoints = [ep for ep in self.endpoints if ep.is_healthy]
        if not healthy_endpoints:
            # Try to reset all endpoints if none are healthy
            for ep in self.endpoints:
                ep.reset_health()
            healthy_endpoints = self.endpoints
        
        if healthy_endpoints:
            return min(healthy_endpoints, key=lambda ep: ep.average_response_time)
        
        return None
    
    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert chat messages to a single prompt for /api/generate"""
        prompt_parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"Human: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        
        # Add Assistant: prefix for the model to continue
        prompt_parts.append("Assistant:")
        
        return "\n\n".join(prompt_parts)
    
    async def check_model_availability(self, model: str, endpoint_url: Optional[str] = None) -> bool:
        """Check if a model is available on any endpoint"""
        models = await self.list_models()
        
        if endpoint_url:
            endpoint_models = models.get(endpoint_url, [])
            return model in endpoint_models
        
        for endpoint_models in models.values():
            if model in endpoint_models:
                return True
        
        return False
    
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a non-streaming response"""
        model = model or self.default_model
        endpoint = self._select_endpoint(preferred_endpoint)
        
        if not endpoint:
            raise Exception("No healthy LLM endpoints available")
        
        # Check cache first
        cache_key = None
        if self.cache_service and temperature == 0:
            # Only cache deterministic responses
            messages_hash = hash(json.dumps(messages, sort_keys=True))
            cache_key = f"llm:response:{model}:{messages_hash}"
            cached = await self.cache_service.get(cache_key)
            if cached:
                logger.info("Returning cached LLM response")
                return cached
        
        start_time = datetime.utcnow()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False
                }
                
                if max_tokens:
                    payload["options"] = {"num_predict": max_tokens}
                
                response = await client.post(
                    f"{endpoint.url}/api/chat",
                    json=payload
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Record response time
                response_time = (datetime.utcnow() - start_time).total_seconds()
                endpoint.record_response_time(response_time)
                
                # Cache if applicable
                if cache_key and self.cache_service:
                    await self.cache_service.set(cache_key, result, expire=3600)
                
                return result
                
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            endpoint.record_error()
            raise
    
    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_endpoint: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream response from LLM"""
        model = model or self.default_model
        endpoint = self._select_endpoint(preferred_endpoint)
        
        if not endpoint:
            raise Exception("No healthy LLM endpoints available")
        
        start_time = datetime.utcnow()
        
        try:
            async with httpx.AsyncClient(timeout=self.streaming_timeout) as client:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True
                }
                
                if max_tokens:
                    payload["options"] = {"num_predict": max_tokens}
                
                async with client.stream(
                    "POST",
                    f"{endpoint.url}/api/chat",
                    json=payload,
                    timeout=self.streaming_timeout
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                # Ollama returns JSON lines
                                data = json.loads(line)
                                
                                # Handle message content
                                if "message" in data and "content" in data["message"]:
                                    content = data["message"]["content"]
                                    if content:  # Only yield non-empty content
                                        yield content
                                
                                # Check for completion
                                if data.get("done", False):
                                    logger.info(f"Stream completed for model {endpoint.url}")
                                    # Record response time on completion
                                    response_time = (datetime.utcnow() - start_time).total_seconds()
                                    endpoint.record_response_time(response_time)
                                    break
                                    
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse streaming response: {line}, error: {e}")
                                continue
                    
        except Exception as e:
            logger.error(f"LLM streaming error: {e}")
            endpoint.record_error()
            raise
    
    async def create_embeddings(
        self,
        text: str,
        model: Optional[str] = None
    ) -> List[float]:
        """Create embeddings for text"""
        model = model or settings.embedding_model
        endpoint = self._select_endpoint()
        
        if not endpoint:
            raise Exception("No healthy LLM endpoints available")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "model": model,
                    "prompt": text
                }
                
                response = await client.post(
                    f"{endpoint.url}/api/embeddings",
                    json=payload
                )
                
                response.raise_for_status()
                result = response.json()
                
                return result.get("embedding", [])
                
        except Exception as e:
            logger.error(f"Embedding creation error: {e}")
            endpoint.record_error()
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of all endpoints"""
        health_status = {
            "healthy_endpoints": 0,
            "total_endpoints": len(self.endpoints),
            "endpoints": []
        }
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for endpoint in self.endpoints:
                try:
                    response = await client.get(f"{endpoint.url}/api/tags")
                    is_healthy = response.status_code == 200
                    
                    if is_healthy:
                        endpoint.reset_health()
                        health_status["healthy_endpoints"] += 1
                    
                    health_status["endpoints"].append({
                        "url": endpoint.url,
                        "is_healthy": is_healthy,
                        "average_response_time": endpoint.average_response_time,
                        "error_count": endpoint.error_count
                    })
                except:
                    health_status["endpoints"].append({
                        "url": endpoint.url,
                        "is_healthy": False,
                        "average_response_time": endpoint.average_response_time,
                        "error_count": endpoint.error_count
                    })
        
        return health_status