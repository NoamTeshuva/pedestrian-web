#!/usr/bin/env python3
"""
Build city_names_mapping.json from Vultr city directories.

This script:
1. Lists all city directories in Vultr (data/processed/israel/cities/)
2. For each city, queries Nominatim to get Hebrew and English names
3. Builds a complete mapping: city_file_name -> {hebrew, english}
4. Writes to api/city_names_mapping.json

Usage:
    python scripts/build_city_names_mapping.py
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import boto3
from botocore.client import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_s3_client():
    """Initialize S3 client for Vultr Object Storage."""
    return boto3.client(
        's3',
        endpoint_url=os.environ.get('S3_ENDPOINT', 'https://ams1.vultrobjects.com'),
        aws_access_key_id=os.environ.get('S3_ACCESS_KEY'),
        aws_secret_access_key=os.environ.get('S3_SECRET_KEY'),
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )


def list_cities_in_vultr(s3_client, bucket: str) -> List[str]:
    """
    List all city directories in Vultr.

    Args:
        s3_client: Boto3 S3 client
        bucket: Bucket name

    Returns:
        List of city names (file names without path)
    """
    logger.info("Listing cities in Vultr bucket...")

    prefix = "data/processed/israel/cities/"
    cities = set()

    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter='/'):
        # CommonPrefixes contains subdirectories
        if 'CommonPrefixes' in page:
            for obj in page['CommonPrefixes']:
                # Extract city name from path like "data/processed/israel/cities/einat/"
                city_dir = obj['Prefix'].rstrip('/')
                city_name = city_dir.split('/')[-1]
                cities.add(city_name)

    cities_list = sorted(list(cities))
    logger.info(f"Found {len(cities_list)} cities in Vultr")
    return cities_list


def query_nominatim_for_city(city_file_name: str) -> Optional[Dict]:
    """
    Query Nominatim for city information.

    Args:
        city_file_name: Internal file name (e.g., "einat", "tel_aviv")

    Returns:
        Dict with hebrew and english names, or None if not found
    """
    import requests

    # Convert file name to query string (replace _ with space, capitalize)
    query = city_file_name.replace('_', ' ').title()

    # Query Nominatim
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': f"{query}, Israel",
        'format': 'json',
        'addressdetails': 1,
        'extratags': 1,
        'namedetails': 1,
        'limit': 1
    }
    headers = {
        'User-Agent': 'PedestrianVolumeApp/1.0'
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            logger.warning(f"No results for {city_file_name} ({query})")
            return None

        result = data[0]

        # Extract names
        namedetails = result.get('namedetails', {})

        # Hebrew name
        hebrew = namedetails.get('name:he', namedetails.get('name', ''))

        # English variations
        english_names = []

        # Add English name if exists
        if 'name:en' in namedetails:
            english_names.append(namedetails['name:en'])

        # Add default name (usually English for Israel)
        default_name = namedetails.get('name', '')
        if default_name and default_name not in english_names:
            # Check if it's not Hebrew (simple heuristic)
            if not any('\u0590' <= c <= '\u05FF' for c in default_name):
                english_names.append(default_name)

        # Add the capitalized query as fallback
        if query not in english_names:
            english_names.append(query)

        logger.info(f"✓ {city_file_name}: {hebrew} | {', '.join(english_names)}")

        return {
            'hebrew': hebrew,
            'english': english_names
        }

    except Exception as e:
        logger.error(f"Error querying {city_file_name}: {e}")
        return None


def build_city_mapping(cities: List[str]) -> Dict:
    """
    Build complete city name mapping.

    Args:
        cities: List of city file names

    Returns:
        Dict mapping city_file_name -> {hebrew, english}
    """
    mapping = {}
    total = len(cities)

    logger.info(f"Querying Nominatim for {total} cities...")
    logger.info("This may take a while (rate limit: 1 request/second)")

    for i, city in enumerate(cities, 1):
        logger.info(f"[{i}/{total}] Querying {city}...")

        city_data = query_nominatim_for_city(city)

        if city_data:
            mapping[city] = city_data
        else:
            # Fallback: use file name as English, mark Hebrew as TO_FILL
            logger.warning(f"  Using fallback for {city}")
            mapping[city] = {
                'hebrew': '[TO_FILL]',
                'english': [city.replace('_', ' ').title()]
            }

        # Respect Nominatim rate limit (1 request per second)
        if i < total:
            time.sleep(1.1)

    logger.info(f"Successfully built mapping for {len(mapping)}/{total} cities")
    return mapping


def save_mapping(mapping: Dict, output_file: Path):
    """
    Save mapping to JSON file.

    Args:
        mapping: City name mapping
        output_file: Output file path
    """
    # Ensure directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write with nice formatting
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)

    logger.info(f"Saved mapping to {output_file}")

    # Print statistics
    with_hebrew = sum(1 for v in mapping.values() if v['hebrew'] and not v['hebrew'].startswith('[TO_FILL'))
    logger.info(f"Statistics:")
    logger.info(f"  Total cities: {len(mapping)}")
    logger.info(f"  With Hebrew names: {with_hebrew}")
    logger.info(f"  Missing Hebrew: {len(mapping) - with_hebrew}")


def main():
    """Main execution."""
    # Check environment variables
    if not os.environ.get('S3_ACCESS_KEY') or not os.environ.get('S3_SECRET_KEY'):
        logger.error("Missing S3_ACCESS_KEY or S3_SECRET_KEY environment variables")
        return 1

    bucket = os.environ.get('S3_BUCKET', 'pedestrian-data-prod')

    # Initialize S3 client
    s3_client = get_s3_client()

    # List cities in Vultr
    cities = list_cities_in_vultr(s3_client, bucket)

    if not cities:
        logger.error("No cities found in Vultr!")
        return 1

    # Build mapping
    mapping = build_city_mapping(cities)

    # Save to file
    output_file = Path(__file__).parent.parent / 'api' / 'city_names_mapping.json'
    save_mapping(mapping, output_file)

    logger.info("Done! 🎉")
    logger.info(f"You can now use CityNameResolver to resolve Hebrew city names")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
