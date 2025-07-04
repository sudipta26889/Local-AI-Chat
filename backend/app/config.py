from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field


class Settings(BaseSettings):
    # Application
    app_name: str = "DharasLocalAI"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"
    
    # API
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost"
    
    # Database
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str
    
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def sync_database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    # Redis
    redis_host: str
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    # LDAP
    ldap_enabled: bool = True
    ldap_server: str
    ldap_port: int = 389
    ldap_use_ssl: bool = False
    ldap_start_tls: bool = True
    ldap_bind_dn: str
    ldap_bind_password: str
    ldap_base_dn: str
    ldap_user_dn_template: str
    ldap_user_search_base: str
    ldap_user_filter: str = "(objectClass=inetOrgPerson)"
    ldap_user_attr_email: str = "mail"
    ldap_user_attr_name: str = "displayName"
    ldap_user_attr_uid: str = "uid"
    ldap_connection_timeout: int = 5
    ldap_auto_create_user: bool = True
    ldap_ignore_tls_errors: bool = True
    
    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 720  # 30 days
    jwt_refresh_expiration_hours: int = 2160  # 90 days
    
    # LLM
    llm_endpoints: str
    default_model: str = "qwen2.5:32b-instruct"
    model_timeout: int = 600  # Increased to 10 minutes for long responses
    streaming_timeout: int = 900  # 15 minutes for streaming responses
    
    @property
    def llm_endpoints_list(self) -> List[str]:
        if isinstance(self.llm_endpoints, str):
            return [ep.strip() for ep in self.llm_endpoints.split(",")]
        return self.llm_endpoints
    
    @property
    def cors_origins_list(self) -> List[str]:
        if isinstance(self.cors_origins, str):
            return [origin.strip() for origin in self.cors_origins.split(",")]
        return self.cors_origins
    
    # Qdrant
    qdrant_host: str
    qdrant_port: int = 6333
    qdrant_api_key: Optional[str] = None
    qdrant_collection_name: str = "dharas_chat_embeddings"
    
    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
    
    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_name: str = "dharas-chat-attachments"
    minio_secure: bool = False
    
    # Embeddings
    embedding_model: str = "nomic-embed-text"
    embedding_dimension: int = 768
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "protected_namespaces": ()
    }


settings = Settings()