#!/usr/bin/env python3
"""
vultr_cache.py

Vultr Object Storage caching for prediction results.
Provides fast path/slow path caching for Israeli city predictions.
"""
import os
import gzip
import json
import logging
import hashlib
from typing import Optional, Dict, Any, Tuple
import boto3
from botocore.exceptions import ClientError

# ============================================================================
# Configuration
# ============================================================================

# S3-compatible client configuration
S3_ENDPOINT = os.getenv('S3_ENDPOINT', 'https://ams1.vultrobjects.com')
S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY')
S3_SECRET_KEY = os.getenv('S3_SECRET_KEY')
S3_BUCKET = os.getenv('S3_BUCKET', 'pedestrian-data-prod')

# Cache configuration
CACHE_PREFIX = "predictions"
MODEL_VERSION = os.getenv('MODEL_VERSION', 'cb_model_israel_v1')
SUPPORTED_COUNTRY = "israel"

# Initialize S3 client
_s3_client = None

def get_s3_client():
    """Get or initialize S3 client (lazy initialization)."""
    global _s3_client
    if _s3_client is None:
        if not S3_ACCESS_KEY or not S3_SECRET_KEY:
            logging.warning("[CACHE] S3 credentials not configured, caching disabled")
            return None

        try:
            _s3_client = boto3.client(
                's3',
                aws_access_key_id=S3_ACCESS_KEY,
                aws_secret_access_key=S3_SECRET_KEY,
                endpoint_url=S3_ENDPOINT,
                region_name='us-east-1'  # Required but not used by Vultr
            )
            logging.info(f"[CACHE] Initialized S3 client for bucket: {S3_BUCKET}")
        except Exception as e:
            logging.error(f"[CACHE] Failed to initialize S3 client: {e}")
            return None

    return _s3_client


# ============================================================================
# Helper Functions
# ============================================================================

def bbox_to_token(bbox: Tuple[float, float, float, float]) -> str:
    """
    Convert bbox coordinates to a normalized token for cache keys.

    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)

    Returns:
        Normalized token like "34.77_32.05_34.81_32.09"
    """
    # Round to 2 decimal places to avoid float precision issues
    min_lon, min_lat, max_lon, max_lat = bbox
    return f"{min_lon:.2f}_{min_lat:.2f}_{max_lon:.2f}_{max_lat:.2f}"


def build_cache_key(
    country: str,
    city: str,
    season: str,
    is_weekend: bool,
    time_of_day: str,
    bbox: Tuple[float, float, float, float]
) -> str:
    """
    Build cache key for prediction results.

    Format: predictions/<model_version>/israel/<city>/<season>/weekend0_or_1/<time_of_day>/bbox_<token>.geojson.gz

    Args:
        country: Country name (must be "israel")
        city: City name (normalized to lowercase, spaces replaced with underscores)
        season: Season name (spring/summer/fall/winter)
        is_weekend: Weekend flag
        time_of_day: Time of day (morning/afternoon/evening/night)
        bbox: Bounding box coordinates

    Returns:
        S3 object key for cache storage
    """
    # Normalize city name
    city_normalized = city.lower().replace(' ', '_').replace('-', '_')

    # Weekend flag
    weekend_flag = "weekend1" if is_weekend else "weekend0"

    # Bbox token
    bbox_token = bbox_to_token(bbox)

    # Build key
    key = (
        f"{CACHE_PREFIX}/"
        f"{MODEL_VERSION}/"
        f"{country}/"
        f"{city_normalized}/"
        f"{season}/"
        f"{weekend_flag}/"
        f"{time_of_day}/"
        f"bbox_{bbox_token}.geojson.gz"
    )

    return key


def cache_exists(cache_key: str) -> bool:
    """
    Check if a cache entry exists in Vultr storage.

    Args:
        cache_key: S3 object key

    Returns:
        True if cache entry exists, False otherwise
    """
    s3_client = get_s3_client()
    if s3_client is None:
        return False

    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=cache_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            logging.warning(f"[CACHE] Error checking cache existence: {e}")
            return False
    except Exception as e:
        logging.warning(f"[CACHE] Unexpected error checking cache: {e}")
        return False


def load_cached_geojson(cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Load cached GeoJSON from Vultr storage.

    Args:
        cache_key: S3 object key

    Returns:
        GeoJSON dict if found, None otherwise
    """
    s3_client = get_s3_client()
    if s3_client is None:
        return None

    try:
        # Download gzipped GeoJSON
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=cache_key)
        compressed_data = response['Body'].read()

        # Decompress and parse
        geojson_bytes = gzip.decompress(compressed_data)
        geojson_str = geojson_bytes.decode('utf-8')
        geojson = json.loads(geojson_str)

        logging.info(f"[CACHE] Loaded cached GeoJSON from {cache_key}")
        return geojson

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            logging.debug(f"[CACHE] Cache miss: {cache_key}")
        else:
            logging.warning(f"[CACHE] Error loading cached GeoJSON: {e}")
        return None
    except Exception as e:
        logging.warning(f"[CACHE] Unexpected error loading cache: {e}")
        return None


def save_cached_geojson(cache_key: str, geojson: Dict[str, Any]) -> bool:
    """
    Save GeoJSON to Vultr storage with gzip compression.

    Args:
        cache_key: S3 object key
        geojson: GeoJSON dict to cache

    Returns:
        True if successful, False otherwise
    """
    s3_client = get_s3_client()
    if s3_client is None:
        return False

    try:
        # Serialize to JSON
        geojson_str = json.dumps(geojson, ensure_ascii=False)
        geojson_bytes = geojson_str.encode('utf-8')

        # Compress with gzip
        compressed_data = gzip.compress(geojson_bytes, compresslevel=6)

        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=cache_key,
            Body=compressed_data,
            ContentType='application/json',
            ContentEncoding='gzip',
            Metadata={
                'original_size': str(len(geojson_bytes)),
                'compressed_size': str(len(compressed_data)),
                'model_version': MODEL_VERSION
            }
        )

        compression_ratio = len(geojson_bytes) / len(compressed_data)
        logging.info(
            f"[CACHE] Saved GeoJSON to {cache_key} "
            f"({len(geojson_bytes)} -> {len(compressed_data)} bytes, "
            f"{compression_ratio:.1f}x compression)"
        )
        return True

    except Exception as e:
        logging.warning(f"[CACHE] Error saving GeoJSON to cache: {e}")
        return False


# ============================================================================
# Validation
# ============================================================================

def validate_country(country: str) -> bool:
    """
    Validate that the country is supported for caching.

    Args:
        country: Country name to validate

    Returns:
        True if country is supported, False otherwise
    """
    return country.lower() == SUPPORTED_COUNTRY


# ============================================================================
# Test/Debug
# ============================================================================

if __name__ == '__main__':
    # Test bbox_to_token
    bbox = (34.7748, 32.0553, 34.8129, 32.0853)
    token = bbox_to_token(bbox)
    print(f"[TEST] bbox_to_token: {token}")

    # Test build_cache_key
    cache_key = build_cache_key(
        country="israel",
        city="Tel Aviv",
        season="summer",
        is_weekend=True,
        time_of_day="morning",
        bbox=bbox
    )
    print(f"[TEST] cache_key: {cache_key}")

    # Test validate_country
    print(f"[TEST] validate_country('israel'): {validate_country('israel')}")
    print(f"[TEST] validate_country('usa'): {validate_country('usa')}")

    # Test S3 client initialization
    client = get_s3_client()
    if client:
        print(f"[TEST] S3 client initialized successfully")
    else:
        print(f"[TEST] S3 client initialization failed (check credentials)")
