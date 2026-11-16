"""Object storage client supporting Azure Blob Storage and local filesystem dev fallback."""
import os
import logging
from pathlib import Path
from typing import Optional
from src.config import settings

logger = logging.getLogger(__name__)

class StorageClient:
    def __init__(self):
        self.connection_string = settings.AZURE_STORAGE_CONNECTION_STRING
        self.container_name = settings.AZURE_CONTAINER_NAME
        self.local_storage_dir = Path(settings.DEV_STORAGE_LOCAL_PATH)
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)
        self.use_azure = bool(self.connection_string and "DefaultEndpointsProtocol" in self.connection_string)

        if self.use_azure:
            logger.info("Storage configured with Azure Blob Storage.")
        else:
            logger.info(f"Storage using local filesystem dev fallback at {self.local_storage_dir.resolve()}.")

    async def upload(self, filename: str, data: bytes, mime_type: str = "application/octet-stream") -> str:
        """Upload raw binary or extracted text and return the storage URL/path."""
        if self.use_azure:
            try:
                # Lazy import azure-storage-blob if configured
                from azure.storage.blob.aio import BlobServiceClient
                async with BlobServiceClient.from_connection_string(self.connection_string) as client:
                    container = client.get_container_client(self.container_name)
                    blob = container.get_blob_client(filename)
                    await blob.upload_blob(data, overwrite=True)
                    return f"https://{client.account_name}.blob.core.windows.net/{self.container_name}/{filename}"
            except Exception as e:
                logger.error(f"Azure upload failed, falling back to disk: {e}")

        # Local filesystem fallback
        dest_path = self.local_storage_dir / filename
        dest_path.write_bytes(data)
        logger.info(f"Stored file locally at {dest_path}")
        return f"/storage/blobs/{filename}"

    async def download(self, filename: str) -> Optional[bytes]:
        """Download raw binary content by filename."""
        if self.use_azure:
            try:
                from azure.storage.blob.aio import BlobServiceClient
                async with BlobServiceClient.from_connection_string(self.connection_string) as client:
                    blob = client.get_blob_client(container=self.container_name, blob=filename)
                    stream = await blob.download_blob()
                    return await stream.readall()
            except Exception as e:
                logger.error(f"Azure download failed: {e}")

        dest_path = self.local_storage_dir / filename
        if dest_path.exists():
            return dest_path.read_bytes()
        return None

    async def delete(self, filename: str) -> bool:
        """Delete stored blob."""
        if self.use_azure:
            try:
                from azure.storage.blob.aio import BlobServiceClient
                async with BlobServiceClient.from_connection_string(self.connection_string) as client:
                    blob = client.get_blob_client(container=self.container_name, blob=filename)
                    await blob.delete_blob()
                    return True
            except Exception as e:
                logger.warning(f"Azure blob delete error: {e}")

        dest_path = self.local_storage_dir / filename
        if dest_path.exists():
            dest_path.unlink()
            return True
        return False

storage_client = StorageClient()
