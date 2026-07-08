import logging

import boto3

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def upload_file(file_bytes: bytes, key: str, content_type: str) -> str:
    if not settings.R2_ENDPOINT:
        return key
    client = get_s3_client()
    client.put_object(
        Bucket=settings.R2_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return key


def get_presigned_url(key: str, expires: int = 3600) -> str | None:
    if not settings.R2_ENDPOINT:
        return None
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def check_storage() -> dict:
    """Health probe for R2/S3. Returns dict describing configuration and reachability."""
    if not settings.R2_ENDPOINT or not settings.R2_BUCKET:
        return {
            "configured": False,
            "reachable": False,
            "bucket": None,
            "detail": "R2_ENDPOINT or R2_BUCKET not set",
        }
    try:
        client = get_s3_client()
        client.head_bucket(Bucket=settings.R2_BUCKET)
        return {
            "configured": True,
            "reachable": True,
            "bucket": settings.R2_BUCKET,
        }
    except Exception as exc:
        logger.warning("Storage health check failed: %s", exc)
        return {
            "configured": True,
            "reachable": False,
            "bucket": settings.R2_BUCKET,
            "detail": f"{type(exc).__name__}: {exc}",
        }
