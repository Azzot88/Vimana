import logging
from functools import lru_cache

import boto3

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_s3_client():
    """One client for the process (T_PERF.1).

    Building a boto3 client is not a cheap constructor: botocore loads and parses
    the S3 service model — a few hundred kilobytes of JSON — and assembles the
    signing machinery. This function used to run on **every** call, and
    `get_presigned_url` is called once per attachment, so opening a vault page
    with a dozen photos built a dozen clients to sign a dozen URLs.

    Sharing one is the documented pattern: boto3 clients are safe to use from
    several threads, which matters because the upload paths now run inside the
    threadpool.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def reset_client_cache() -> None:
    """For tests that swap R2 settings mid-run (cf. `keypair.reset_key_cache`)."""
    get_s3_client.cache_clear()


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


# A presigned URL is a bearer token for one object: whoever holds the link can
# fetch the file for its whole lifetime, with no session and no authorization
# check. It leaks the ordinary ways links leak — browser history, a referrer, a
# shared screenshot, a chat log.
#
# So the lifetime should match what the object is worth. An avatar living an
# hour costs nothing. A passport scan living an hour is a different bet: the
# window only has to be long enough to open the file once.
PRESIGN_TTL_DEFAULT = 3600
PRESIGN_TTL_SENSITIVE = 300


def get_presigned_url(key: str, expires: int = PRESIGN_TTL_DEFAULT) -> str | None:
    if not settings.R2_ENDPOINT:
        return None
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def presign_ttl_for_kind(kind: str | None) -> int:
    """Short-lived link for identity documents, normal for everything else.

    Keyed on `AttachmentKind`. `identity_doc` is the copy of a passport or ID
    that T3.9 places inside a deal — the most sensitive bytes the platform
    stores, and the ones a stale link hurts most.
    """
    return PRESIGN_TTL_SENSITIVE if kind == "identity_doc" else PRESIGN_TTL_DEFAULT


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
