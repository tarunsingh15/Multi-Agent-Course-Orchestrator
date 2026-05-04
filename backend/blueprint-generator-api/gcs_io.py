"""
This module provides helper functions to work with Google Cloud Storage (GCS).
It includes functions to:
1. Read and write files stored in GCS
2. Upload JSON data
3. Download JSON or text files

These helper functions are used throughout the app to store and retrieve files
"""
# utils/gcs_io.py
from __future__ import annotations

import json
import uuid
import logging
from typing import Any, Optional, Tuple
from google.cloud import storage
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

def split_gcs_uri(gcs_uri: str) -> Tuple[str, str]:
    """
    Parses a GCS URI to extract the bucket name and the object/blob name.
    """
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
        # The first part of the path is the bucket name, the rest is the blob
        return path_parts[0], path_parts[1]
    else:
        raise ValueError(f"Not a valid GCS or HTTPS GCS URI: {gcs_uri}")


def upload_json_to_gcs(
    data: Any,
    bucket_name: str,
    *, 
    object_name: Optional[str] = None,
    prefix: Optional[str] = None,
    content_type: str = "application/json",
) -> str:
    """Serializes a Python object to JSON and uploads it to a GCS bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    if object_name is None:
        object_name = f"{uuid.uuid4()}.json"
    if prefix:
        object_name = f"{prefix.rstrip('/')}/{object_name}"

    blob = bucket.blob(object_name)
    # Convert the data to a formatted JSON string.
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    # Upload the JSON string to the specified blob.
    blob.upload_from_string(payload, content_type=content_type)
    # Return the public URL for easy access.
    return blob.public_url


def download_json_from_uri(uri: str):
    """Downloads a JSON file from a GCS URI and deserializes it into a Python object."""
    logger.info(f"Downloading JSON from: {uri}")
    storage_client = storage.Client()
    try:
        # Extract bucket and blob names from the URI.
        bucket_name, blob_name = split_gcs_uri(uri)
        # Decode URL-encoded characters in the blob name.
        blob_name = unquote(blob_name)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {uri}")
        # Download the blob content as text and parse it as JSON.
        return json.loads(blob.download_as_text())
    except Exception as e:
        logger.exception(f"Failed to download or parse JSON from {uri}")
        raise

def download_text_from_uri(uri: str) -> str:
    """Downloads a text-based file from a GCS URI as a string."""
    logger.info(f"Downloading text from: {uri}")
    storage_client = storage.Client()
    try:
        # Extract bucket and blob names from the URI.
        bucket_name, blob_name = split_gcs_uri(uri)
        blob_name = unquote(blob_name)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: {uri}")
        # Download the blob content as a raw text string.
        return blob.download_as_text()
    except Exception as e:
        logger.exception(f"Failed to download text from {uri}")
        raise