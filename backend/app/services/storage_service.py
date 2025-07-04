import io
from typing import Optional, BinaryIO, Dict, Any
from datetime import datetime, timedelta
import mimetypes
from minio import Minio
from minio.error import S3Error
from loguru import logger

from app.config import settings


class StorageService:
    """Service for MinIO object storage operations"""
    
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        self.bucket_name = settings.minio_bucket_name
    
    async def initialize(self):
        """Initialize storage service and ensure bucket exists"""
        try:
            # Check if bucket exists
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created MinIO bucket: {self.bucket_name}")
            else:
                logger.info(f"MinIO bucket exists: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO: {e}")
            raise
    
    def upload_file(
        self,
        file_data: BinaryIO,
        object_name: str,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """Upload file to MinIO"""
        try:
            # Guess content type if not provided
            if not content_type:
                content_type, _ = mimetypes.guess_type(object_name)
                if not content_type:
                    content_type = "application/octet-stream"
            
            # Get file size
            file_data.seek(0, 2)  # Seek to end
            file_size = file_data.tell()
            file_data.seek(0)  # Reset to beginning
            
            # Upload file
            self.client.put_object(
                self.bucket_name,
                object_name,
                file_data,
                file_size,
                content_type=content_type,
                metadata=metadata
            )
            
            logger.info(f"Uploaded file: {object_name}")
            return object_name
            
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise
    
    def download_file(self, object_name: str) -> bytes:
        """Download file from MinIO"""
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            
            return data
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"File not found: {object_name}")
                raise FileNotFoundError(f"File not found: {object_name}")
            logger.error(f"Failed to download file: {e}")
            raise
    
    def get_download_url(self, object_name: str, expiry: int = 3600) -> str:
        """Get presigned download URL"""
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=timedelta(seconds=expiry)
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate download URL: {e}")
            raise
    
    def get_upload_url(
        self,
        object_name: str,
        expiry: int = 3600,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get presigned upload URL"""
        try:
            # Prepare post policy
            post_policy = self.client.presigned_post_policy(
                self.bucket_name,
                object_name,
                expires=timedelta(seconds=expiry)
            )
            
            return {
                "url": post_policy[0],
                "fields": post_policy[1]
            }
        except Exception as e:
            logger.error(f"Failed to generate upload URL: {e}")
            raise
    
    def delete_file(self, object_name: str) -> bool:
        """Delete file from MinIO"""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info(f"Deleted file: {object_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return False
    
    def list_files(self, prefix: str = "", limit: int = 100) -> list:
        """List files in bucket with optional prefix"""
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            
            files = []
            for obj in objects:
                if len(files) >= limit:
                    break
                
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat(),
                    "etag": obj.etag
                })
            
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []
    
    def get_file_info(self, object_name: str) -> Optional[Dict[str, Any]]:
        """Get file metadata"""
        try:
            stat = self.client.stat_object(self.bucket_name, object_name)
            
            return {
                "name": stat.object_name,
                "size": stat.size,
                "last_modified": stat.last_modified.isoformat(),
                "etag": stat.etag,
                "content_type": stat.content_type,
                "metadata": stat.metadata
            }
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            logger.error(f"Failed to get file info: {e}")
            raise
    
    def create_user_folder(self, user_id: str) -> str:
        """Create a folder structure for user"""
        # MinIO doesn't have real folders, but we can use prefixes
        folder_prefix = f"users/{user_id}/"
        
        # Create a placeholder object to ensure the "folder" exists
        placeholder = f"{folder_prefix}.keep"
        self.client.put_object(
            self.bucket_name,
            placeholder,
            io.BytesIO(b""),
            0
        )
        
        return folder_prefix