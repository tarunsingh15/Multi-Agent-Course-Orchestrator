import json
import logging
from typing import Any, Tuple
from urllib.parse import unquote, urlparse
from google.cloud import storage

logger = logging.getLogger(__name__)

# Copied from backend/evaluator-api/agents/evaluation_agent.py
def split_gcs_uri(gcs_uri: str) -> Tuple[str, str]:
    """Accepts either gs:// or https://storage.googleapis.com/..."""
    if gcs_uri.startswith("gs://"):
        parts = gcs_uri[5:].split("/", 1)
        if len(parts) < 2 or not parts[0] or not parts[1]:
             raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        return parts[0], parts[1]
    elif "storage.googleapis.com" in gcs_uri:
        parsed = urlparse(gcs_uri)
        path_parts = parsed.path.lstrip("/").split("/", 1)
        if len(path_parts) < 2:
            raise ValueError(f"Unexpected GCS URL format: {gcs_uri}")
        return path_parts[0], path_parts[1]
    else:
        raise ValueError(f"Not a valid GCS or HTTPS GCS URI: {gcs_uri}")

def upload_json_to_gcs(data: Any, bucket_name: str, object_name: str, storage_client: storage.Client) -> str:
    """
    Uploads JSON-serializable data to GCS and returns the public URL.
    """
    logger.info(f"Uploading JSON to: gs://{bucket_name}/{object_name}")
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        blob.upload_from_string(payload, content_type="application/json")
        return f"gs://{bucket_name}/{object_name}"
    except Exception as e:
        logger.exception(f"Failed to upload JSON to gs://{bucket_name}/{object_name}")
        raise

def download_json_from_uri(uri: str) -> Any:
    """Download JSON either from a gs:// URI or a public HTTPS URL."""
    logger.info(f"Downloading JSON from: {uri}")
    storage_client = storage.Client()
    try:
        bucket_name, blob_name = split_gcs_uri(uri)
        blob_name = unquote(blob_name)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {uri}")
        return json.loads(blob.download_as_text())
    except Exception as e:
        logger.exception(f"Failed to download or parse JSON from {uri}")
        raise

def download_text_from_uri(uri: str) -> str:
    """Downloads a text blob from a gs:// URI or public https:// GCS URL."""
    logger.info(f"Downloading text from: {uri}")
    storage_client = storage.Client()
    try:
        bucket_name, blob_name = split_gcs_uri(uri)
        blob_name = unquote(blob_name)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {uri}")
        return blob.download_as_text()
    except Exception as e:
        logger.exception(f"Failed to download text from {uri}")
        raise