#!/usr/bin/env python3
"""
disk_cache.py

Simple disk-based cache for GeoDataFrames that works across multiple Gunicorn workers.
Stores cached results as GeoPackage files with metadata.
"""
import os
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import geopandas as gpd


class DiskCache:
    """Disk-based cache for GeoDataFrames."""

    def __init__(self, cache_dir: str = "cache/features"):
        """Initialize disk cache.

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Initialized DiskCache at {self.cache_dir.absolute()}")

    def _get_cache_key(self, place: Optional[str], bbox: Optional[Tuple[float, float, float, float]]) -> str:
        """Generate cache key from place and bbox.

        Args:
            place: Place name
            bbox: Bounding box tuple

        Returns:
            str: MD5 hash of cache key
        """
        key_parts = []
        if place:
            key_parts.append(f"place={place}")
        if bbox:
            key_parts.append(f"bbox={bbox}")

        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(self, place: Optional[str], bbox: Optional[Tuple[float, float, float, float]]) -> Optional[Tuple[gpd.GeoDataFrame, Dict[str, Any]]]:
        """Get cached features if available.

        Args:
            place: Place name
            bbox: Bounding box tuple

        Returns:
            Tuple of (GeoDataFrame, metadata) if found, None otherwise
        """
        try:
            cache_key = self._get_cache_key(place, bbox)
            parquet_file = self.cache_dir / f"{cache_key}.parquet"
            metadata_file = self.cache_dir / f"{cache_key}_metadata.json"

            if not parquet_file.exists() or not metadata_file.exists():
                logging.debug(f"[DISK CACHE] MISS: {place or bbox}")
                return None

            # Load GeoDataFrame from Parquet (faster and more reliable than GPKG)
            gdf = gpd.read_parquet(str(parquet_file))

            # Load metadata
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            logging.info(f"[DISK CACHE] HIT: {place or bbox} | {len(gdf)} features")
            return gdf.copy(), metadata

        except Exception as e:
            logging.warning(f"[DISK CACHE] Error reading cache: {e}")
            return None

    def set(self, place: Optional[str], bbox: Optional[Tuple[float, float, float, float]],
            gdf: gpd.GeoDataFrame, metadata: Dict[str, Any]) -> None:
        """Store features in disk cache.

        Args:
            place: Place name
            bbox: Bounding box tuple
            gdf: GeoDataFrame to cache
            metadata: Pipeline metadata
        """
        try:
            cache_key = self._get_cache_key(place, bbox)
            parquet_file = self.cache_dir / f"{cache_key}.parquet"
            metadata_file = self.cache_dir / f"{cache_key}_metadata.json"

            # Save GeoDataFrame as Parquet (faster and more reliable than GPKG)
            # Parquet doesn't use Fiona, avoiding compatibility issues
            gdf.to_parquet(str(parquet_file))

            # Save metadata (make it JSON-serializable)
            serializable_metadata = self._make_serializable(metadata)
            with open(metadata_file, 'w') as f:
                json.dump(serializable_metadata, f, indent=2)

            logging.info(f"[DISK CACHE] STORED: {place or bbox} | {len(gdf)} features")

        except Exception as e:
            logging.error(f"[DISK CACHE] Error writing cache: {e}")

    def _make_serializable(self, obj: Any) -> Any:
        """Convert object to JSON-serializable format.

        Args:
            obj: Object to serialize

        Returns:
            JSON-serializable version of object
        """
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        else:
            return str(obj)

    def clear(self) -> None:
        """Clear all cache files."""
        try:
            for file in self.cache_dir.glob("*"):
                file.unlink()
            logging.info(f"[DISK CACHE] Cleared all cache files")
        except Exception as e:
            logging.error(f"[DISK CACHE] Error clearing cache: {e}")


# Global disk cache instance
_disk_cache = None

def get_disk_cache() -> DiskCache:
    """Get global disk cache instance."""
    global _disk_cache
    if _disk_cache is None:
        _disk_cache = DiskCache()
    return _disk_cache
