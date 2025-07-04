from typing import Dict, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.llm_service import LLMService
from app.services.cache_service import CacheService


router = APIRouter()


class ModelInfo(BaseModel):
    name: str
    endpoint: str
    available: bool


class ModelsResponse(BaseModel):
    models: List[ModelInfo]
    default_model: str


class HealthResponse(BaseModel):
    healthy_endpoints: int
    total_endpoints: int
    endpoints: List[dict]


@router.get("", response_model=ModelsResponse)
async def list_models(
    current_user: User = Depends(get_current_user)
):
    """List all available models from all endpoints"""
    llm_service = LLMService()
    
    # Get models from all endpoints
    all_models = await llm_service.list_models()
    
    # Format response
    models = []
    for endpoint, model_list in all_models.items():
        for model_name in model_list:
            models.append(ModelInfo(
                name=model_name,
                endpoint=endpoint,
                available=True
            ))
    
    # Sort models by name
    models.sort(key=lambda x: x.name)
    
    # Get default model from user preferences or system default
    default_model = (
        current_user.preferences.get("default_model") 
        if current_user.preferences 
        else None
    ) or llm_service.default_model
    
    return ModelsResponse(
        models=models,
        default_model=default_model
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