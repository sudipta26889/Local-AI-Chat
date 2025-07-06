import asyncio
import json
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime
import httpx
from loguru import logger
from enum import Enum

from app.config import settings
from app.services.cache_service import CacheService


class ServiceType(Enum):
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"


class LLMEndpoint:
    """Represents a single LLM endpoint"""
    
    def __init__(self, service_config: Dict[str, str]):
        self.name = service_config.get("name", "")
        self.type = ServiceType(service_config.get("type", "ollama"))
        self.url = service_config.get("url", "").rstrip('/')
        self.default_model = service_config.get("default_model", "")
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
        # Initialize endpoints from services configuration
        self.endpoints = [LLMEndpoint(service) for service in settings.llm_services_list]
        self.cache_service = cache_service
        
        # Get default service and model
        default_info = settings.default_service_info
        self.default_service_name = default_info.get("service_name")
        self.default_model = default_info.get("model_name")
        
        # Legacy support
        if not self.default_model and settings.default_model:
            self.default_model = settings.default_model
        
        self.timeout = settings.model_timeout
        self.streaming_timeout = settings.streaming_timeout
    
    async def list_models(self) -> Dict[str, Dict[str, Any]]:
        """List available models from all endpoints"""
        all_models = {}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for endpoint in self.endpoints:
                if not endpoint.is_healthy:
                    continue
                
                try:
                    if endpoint.type == ServiceType.OLLAMA:
                        response = await client.get(f"{endpoint.url}/api/tags")
                        if response.status_code == 200:
                            data = response.json()
                            models = [model["name"] for model in data.get("models", [])]
                            all_models[endpoint.name] = {
                                "type": endpoint.type.value,
                                "url": endpoint.url,
                                "models": models,
                                "default_model": endpoint.default_model
                            }
                    elif endpoint.type == ServiceType.LMSTUDIO:
                        # LM Studio uses OpenAI-compatible API
                        response = await client.get(f"{endpoint.url}/v1/models")
                        if response.status_code == 200:
                            data = response.json()
                            models = [model["id"] for model in data.get("data", [])]
                            all_models[endpoint.name] = {
                                "type": endpoint.type.value,
                                "url": endpoint.url,
                                "models": models,
                                "default_model": endpoint.default_model
                            }
                except Exception as e:
                    logger.error(f"Failed to fetch models from {endpoint.name} ({endpoint.url}): {e}")
                    endpoint.record_error()
        
        return all_models
    
    def _select_endpoint(self, preferred_service: Optional[str] = None) -> Optional[LLMEndpoint]:
        """Select best available endpoint"""
        if preferred_service:
            for endpoint in self.endpoints:
                if endpoint.name == preferred_service and endpoint.is_healthy:
                    return endpoint
        
        # Try to use default service
        if self.default_service_name:
            for endpoint in self.endpoints:
                if endpoint.name == self.default_service_name and endpoint.is_healthy:
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
    
    async def check_model_availability(self, model: str, service_name: Optional[str] = None) -> bool:
        """Check if a model is available on any endpoint"""
        models = await self.list_models()
        
        if service_name:
            service_info = models.get(service_name, {})
            return model in service_info.get("models", [])
        
        for service_info in models.values():
            if model in service_info.get("models", []):
                return True
        
        return False
    
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_service: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a non-streaming response"""
        endpoint = self._select_endpoint(preferred_service)
        
        if not endpoint:
            raise Exception("No healthy LLM endpoints available")
        
        # Use endpoint's default model if not specified
        model = model or endpoint.default_model or self.default_model
        
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
                if endpoint.type == ServiceType.OLLAMA:
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
                    
                elif endpoint.type == ServiceType.LMSTUDIO:
                    # LM Studio uses OpenAI-compatible API
                    payload = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": False
                    }
                    
                    if max_tokens:
                        payload["max_tokens"] = max_tokens
                    
                    response = await client.post(
                        f"{endpoint.url}/v1/chat/completions",
                        json=payload
                    )
                
                response.raise_for_status()
                result = response.json()
                
                # Normalize response format
                if endpoint.type == ServiceType.LMSTUDIO:
                    # Convert OpenAI format to Ollama format
                    if "choices" in result and result["choices"]:
                        content = result["choices"][0]["message"]["content"]
                        result = {
                            "message": {
                                "role": "assistant",
                                "content": content
                            },
                            "done": True
                        }
                
                # Record response time
                response_time = (datetime.utcnow() - start_time).total_seconds()
                endpoint.record_response_time(response_time)
                
                # Cache if applicable
                if cache_key and self.cache_service:
                    await self.cache_service.set(cache_key, result, expire=3600)
                
                return result
                
        except Exception as e:
            logger.error(f"LLM generation error on {endpoint.name}: {e}")
            endpoint.record_error()
            raise
    
    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_service: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream response from LLM"""
        endpoint = self._select_endpoint(preferred_service)
        
        if not endpoint:
            raise Exception("No healthy LLM endpoints available")
        
        # Use endpoint's default model if not specified
        model = model or endpoint.default_model or self.default_model
        
        start_time = datetime.utcnow()
        
        try:
            async with httpx.AsyncClient(timeout=self.streaming_timeout) as client:
                if endpoint.type == ServiceType.OLLAMA:
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
                                    data = json.loads(line)
                                    
                                    if "message" in data and "content" in data["message"]:
                                        content = data["message"]["content"]
                                        if content:
                                            yield content
                                    
                                    if data.get("done", False):
                                        logger.info(f"Stream completed for {endpoint.name}")
                                        response_time = (datetime.utcnow() - start_time).total_seconds()
                                        endpoint.record_response_time(response_time)
                                        break
                                        
                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to parse streaming response: {line}, error: {e}")
                                    continue
                
                elif endpoint.type == ServiceType.LMSTUDIO:
                    # LM Studio uses OpenAI-compatible API with SSE
                    payload = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": True
                    }
                    
                    if max_tokens:
                        payload["max_tokens"] = max_tokens
                    
                    async with client.stream(
                        "POST",
                        f"{endpoint.url}/v1/chat/completions",
                        json=payload,
                        timeout=self.streaming_timeout
                    ) as response:
                        response.raise_for_status()
                        
                        async for line in response.aiter_lines():
                            if line.strip():
                                # LM Studio uses Server-Sent Events format
                                if line.startswith("data: "):
                                    data_str = line[6:]  # Remove "data: " prefix
                                    
                                    if data_str == "[DONE]":
                                        logger.info(f"Stream completed for {endpoint.name}")
                                        response_time = (datetime.utcnow() - start_time).total_seconds()
                                        endpoint.record_response_time(response_time)
                                        break
                                    
                                    try:
                                        data = json.loads(data_str)
                                        
                                        if "choices" in data and data["choices"]:
                                            delta = data["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                yield content
                                                
                                    except json.JSONDecodeError as e:
                                        logger.warning(f"Failed to parse SSE data: {data_str}, error: {e}")
                                        continue
                    
        except Exception as e:
            logger.error(f"LLM streaming error on {endpoint.name}: {e}")
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
            "healthy_services": 0,
            "total_services": len(self.endpoints),
            "default_service": self.default_service_name,
            "default_model": self.default_model,
            "services": []
        }
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for endpoint in self.endpoints:
                try:
                    if endpoint.type == ServiceType.OLLAMA:
                        response = await client.get(f"{endpoint.url}/api/tags")
                    elif endpoint.type == ServiceType.LMSTUDIO:
                        response = await client.get(f"{endpoint.url}/v1/models")
                    
                    is_healthy = response.status_code == 200
                    
                    if is_healthy:
                        endpoint.reset_health()
                        health_status["healthy_services"] += 1
                    
                    health_status["services"].append({
                        "name": endpoint.name,
                        "type": endpoint.type.value,
                        "url": endpoint.url,
                        "default_model": endpoint.default_model,
                        "is_healthy": is_healthy,
                        "average_response_time": endpoint.average_response_time,
                        "error_count": endpoint.error_count
                    })
                except:
                    health_status["services"].append({
                        "name": endpoint.name,
                        "type": endpoint.type.value,
                        "url": endpoint.url,
                        "default_model": endpoint.default_model,
                        "is_healthy": False,
                        "average_response_time": endpoint.average_response_time,
                        "error_count": endpoint.error_count
                    })
        
        return health_status