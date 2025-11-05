"""
Vultr Object Storage utilities for pedestrian prediction API.
Provides S3-compatible storage interface for models and data.
"""

import os
import logging
from typing import Optional, BinaryIO
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logging.warning("boto3 not installed. Vultr storage will not be available.")

logger = logging.getLogger(__name__)


class VultrStorage:
    """S3-compatible client for Vultr Object Storage."""

    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        bucket_name: Optional[str] = None,
        region: str = "us-east-1"
    ):
        """
        Initialize Vultr storage client.

        Args:
            access_key: Vultr access key (defaults to VULTR_ACCESS_KEY env var)
            secret_key: Vultr secret key (defaults to VULTR_SECRET_KEY env var)
            endpoint_url: S3 endpoint URL (defaults to VULTR_ENDPOINT env var)
            bucket_name: Bucket name (defaults to VULTR_BUCKET env var)
            region: AWS region name for S3 client (default: us-east-1)
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for Vultr storage. Install with: pip install boto3")

        self.access_key = access_key or os.getenv("S3_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("S3_SECRET_KEY")
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT")
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET")
        self.region = region or os.getenv("S3_REGION", "us-east-1")

        if not all([self.access_key, self.secret_key, self.endpoint_url, self.bucket_name]):
            raise ValueError(
                "Missing S3 credentials. Set environment variables: "
                "S3_ACCESS_KEY, S3_SECRET_KEY, S3_ENDPOINT, S3_BUCKET"
            )

        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            endpoint_url=self.endpoint_url,
            region_name=self.region
        )

        logger.info(f"Initialized Vultr storage client: bucket={self.bucket_name}, endpoint={self.endpoint_url}")

    def download_file(self, object_key: str, local_path: str) -> bool:
        """
        Download file from Vultr storage to local path.

        Args:
            object_key: Object key in bucket (e.g., "models/model.cbm")
            local_path: Local file path to save to

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create parent directory if needed
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"Downloading from Vultr: s3://{self.bucket_name}/{object_key} -> {local_path}")
            self.s3_client.download_file(self.bucket_name, object_key, local_path)
            logger.info(f"Successfully downloaded: {object_key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to download {object_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading {object_key}: {e}")
            return False

    def upload_file(self, local_path: str, object_key: str) -> bool:
        """
        Upload file from local path to Vultr storage.

        Args:
            local_path: Local file path to upload
            object_key: Object key in bucket (e.g., "models/model.cbm")

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Uploading to Vultr: {local_path} -> s3://{self.bucket_name}/{object_key}")
            self.s3_client.upload_file(local_path, self.bucket_name, object_key)
            logger.info(f"Successfully uploaded: {object_key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading {local_path}: {e}")
            return False

    def file_exists(self, object_key: str) -> bool:
        """
        Check if file exists in Vultr storage.

        Args:
            object_key: Object key to check

        Returns:
            True if exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError:
            return False

    def list_files(self, prefix: str = "") -> list[str]:
        """
        List files in bucket with optional prefix filter.

        Args:
            prefix: Object key prefix (e.g., "models/")

        Returns:
            List of object keys
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                return []

            return [obj['Key'] for obj in response['Contents']]

        except ClientError as e:
            logger.error(f"Failed to list files with prefix '{prefix}': {e}")
            return []

    def generate_presigned_url(self, object_key: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generate presigned URL for temporary public access.

        Args:
            object_key: Object key to generate URL for
            expires_in: Expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL or None if error
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_key},
                ExpiresIn=expires_in
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {object_key}: {e}")
            return None

    def delete_file(self, object_key: str) -> bool:
        """
        Delete file from Vultr storage.

        Args:
            object_key: Object key to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
            logger.info(f"Deleted: {object_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete {object_key}: {e}")
            return False


def get_vultr_storage() -> Optional[VultrStorage]:
    """
    Get VultrStorage instance if configured, otherwise None.

    Returns:
        VultrStorage instance or None if not configured
    """
    if not BOTO3_AVAILABLE:
        return None

    # Check if S3 storage is enabled
    use_s3 = os.getenv("USE_S3_STORAGE", "false").lower() == "true"
    if not use_s3:
        logger.info("S3 storage disabled (USE_S3_STORAGE not set)")
        return None

    try:
        return VultrStorage()
    except (ValueError, ImportError) as e:
        logger.warning(f"S3 storage not available: {e}")
        return None


def download_model_from_vultr(model_name: str, local_dir: str = "/tmp/models") -> Optional[str]:
    """
    Download model from Vultr to local cache directory.

    Args:
        model_name: Model filename (e.g., "cb_model.cbm")
        local_dir: Local directory to cache model (default: /tmp/models)

    Returns:
        Local path to downloaded model, or None if failed
    """
    storage = get_vultr_storage()
    if not storage:
        return None

    # Create local cache directory
    os.makedirs(local_dir, exist_ok=True)

    # Define paths
    object_key = f"models/{model_name}"
    local_path = os.path.join(local_dir, model_name)

    # Check if already cached locally
    if os.path.exists(local_path):
        logger.info(f"Model already cached locally: {local_path}")
        return local_path

    # Download from Vultr
    if storage.download_file(object_key, local_path):
        return local_path
    else:
        return None


def upload_model_to_vultr(local_path: str, model_name: Optional[str] = None) -> bool:
    """
    Upload model file to Vultr storage.

    Args:
        local_path: Path to local model file
        model_name: Optional custom name in storage (defaults to filename)

    Returns:
        True if successful, False otherwise
    """
    storage = get_vultr_storage()
    if not storage:
        logger.error("Vultr storage not configured")
        return False

    if not os.path.exists(local_path):
        logger.error(f"Local file not found: {local_path}")
        return False

    # Use filename if no custom name provided
    if not model_name:
        model_name = os.path.basename(local_path)

    object_key = f"models/{model_name}"
    return storage.upload_file(local_path, object_key)
