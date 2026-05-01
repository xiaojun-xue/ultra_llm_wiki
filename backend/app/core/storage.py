import uuid
from io import BytesIO

import aioboto3
from botocore.config import Config

from app.config import settings


class StorageService:
    """MinIO/S3 file storage service."""

    def __init__(self):
        self._session = aioboto3.Session()

    def _client_kwargs(self):
        return {
            "service_name": "s3",
            "endpoint_url": f"{'https' if settings.minio_use_ssl else 'http'}://{settings.minio_endpoint}",
            "aws_access_key_id": settings.minio_access_key,
            "aws_secret_access_key": settings.minio_secret_key,
            "config": Config(signature_version="s3v4"),
        }

    async def ensure_bucket(self):
        """Create the bucket if it doesn't exist."""
        async with self._session.client(**self._client_kwargs()) as s3:
            try:
                await s3.head_bucket(Bucket=settings.minio_bucket)
            except Exception:
                await s3.create_bucket(Bucket=settings.minio_bucket)

    async def upload_file(self, data: bytes, filename: str, content_type: str) -> str:
        """Upload a file and return its storage path."""
        # Organize by type prefix to avoid flat namespace
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        storage_path = f"{ext}/{uuid.uuid4().hex[:8]}_{filename}"

        async with self._session.client(**self._client_kwargs()) as s3:
            await s3.upload_fileobj(
                BytesIO(data),
                settings.minio_bucket,
                storage_path,
                ExtraArgs={"ContentType": content_type},
            )
        return storage_path

    async def download_file(self, storage_path: str) -> bytes:
        """Download a file by its storage path."""
        async with self._session.client(**self._client_kwargs()) as s3:
            response = await s3.get_object(Bucket=settings.minio_bucket, Key=storage_path)
            return await response["Body"].read()

    async def delete_file(self, storage_path: str):
        """Delete a file from storage."""
        async with self._session.client(**self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=settings.minio_bucket, Key=storage_path)

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary access."""
        async with self._session.client(**self._client_kwargs()) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.minio_bucket, "Key": storage_path},
                ExpiresIn=expires_in,
            )


storage_service = StorageService()
