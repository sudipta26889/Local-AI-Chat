from typing import Dict, List, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.llm_service import LLMService
from app.services.cache_service import CacheService


router = APIRouter()


class ModelInfo(BaseModel):
    name: str
    service: str
    service_type: str
    endpoint: str
    available: bool
    is_default: bool


class ServiceInfo(BaseModel):
    name: str
    type: str
    url: str
    default_model: str
    models: List[str]
    is_healthy: bool
    is_default_service: bool


class ModelsResponse(BaseModel):
    services: List[ServiceInfo]
    models: List[ModelInfo]
    default_service: str
    default_model: str


class HealthResponse(BaseModel):
    healthy_services: int
    total_services: int
    default_service: str
    default_model: str
    services: List[dict]


@router.get("", response_model=ModelsResponse)
async def list_models(
    current_user: User = Depends(get_current_user)
):
    """List all available models from all services"""
    llm_service = LLMService()
    
    # Get models from all services
    all_services = await llm_service.list_models()
    
    # Get health status for service availability
    health_status = await llm_service.health_check()
    health_by_name = {s["name"]: s["is_healthy"] for s in health_status["services"]}
    
    # Format response
    services = []
    models = []
    
    for service_name, service_info in all_services.items():
        is_default_service = service_name == llm_service.default_service_name
        
        # Add service info
        services.append(ServiceInfo(
            name=service_name,
            type=service_info["type"],
            url=service_info["url"],
            default_model=service_info["default_model"],
            models=service_info["models"],
            is_healthy=health_by_name.get(service_name, False),
            is_default_service=is_default_service
        ))
        
        # Add individual models
        for model_name in service_info["models"]:
            is_default = (is_default_service and model_name == llm_service.default_model)
            models.append(ModelInfo(
                name=model_name,
                service=service_name,
                service_type=service_info["type"],
                endpoint=service_info["url"],
                available=health_by_name.get(service_name, False),
                is_default=is_default
            ))
    
    # Sort models by service and name
    models.sort(key=lambda x: (x.service, x.name))
    
    # Get default model from user preferences or system default
    user_default_model = (
        current_user.preferences.get("default_model") 
        if current_user.preferences 
        else None
    )
    
    return ModelsResponse(
        services=services,
        models=models,
        default_service=llm_service.default_service_name or "",
        default_model=user_default_model or llm_service.default_model or ""
    )


@router.get("/status", response_model=HealthResponse)
async def check_models_status(
    current_user: User = Depends(get_current_user)
):
    """Check health status of all LLM endpoints"""
    llm_service = LLMService()
    
    # Get health status
    health_status = await llm_service.health_check()
    
    return HealthResponse(**health_status)


@router.post("/check/{model_name}")
async def check_model_availability(
    model_name: str,
    current_user: User = Depends(get_current_user)
):
    """Check if a specific model is available"""
    llm_service = LLMService()
    
    # Check model availability
    available = await llm_service.check_model_availability(model_name)
    
    return {
        "model": model_name,
        "available": available
    }


@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_user)
):
    """Get cache statistics for LLM responses"""
    cache_service = CacheService()
    await cache_service.initialize()
    
    # Get cache keys pattern for LLM responses
    llm_keys = await cache_service.get_keys("llm:response:*")
    
    return {
        "cached_responses": len(llm_keys),
        "cache_enabled": True
    }