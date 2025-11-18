#!/usr/bin/env python3
"""
weather_profile_store.py

Runtime store for precomputed Israel weather profiles.

This module loads precomputed weather data and provides fast lookup
for (zone, season, time_of_day) combinations during predictions.

Usage:
    # At app startup
    store = IsraelWeatherProfileStore(
        profiles_path="data/processed/israel/israel_weather_profiles.parquet",
        zones_path="data/processed/israel/israel_weather_zones.gpkg"
    )

    # During prediction
    weather = store.get_weather_for_geometry(
        geom=street_network_geometry,
        season="winter",
        time_of_day="morning"
    )
"""
import logging
import pandas as pd
import geopandas as gpd
from typing import Optional, Dict, Any
from pathlib import Path
import os

from .israel_weather_zones import (
    find_zone_for_geometry,
    load_israel_weather_zones
)


class WeatherProfileError(Exception):
    """Exception for weather profile store errors."""
    pass


class IsraelWeatherProfileStore:
    """
    Store for precomputed Israel weather profiles.

    Loads weather profiles and zones at initialization, then provides
    fast lookup during predictions.
    """

    def __init__(self,
                 profiles_path: str,
                 zones_path: Optional[str] = None,
                 fallback_function: Optional[callable] = None):
        """
        Initialize the weather profile store.

        Parameters
        ----------
        profiles_path : str
            Path to precomputed profiles parquet file OR GeoPackage file
            If GPKG, profiles are read from 'profiles' table and zones from 'zones' layer
        zones_path : str, optional
            Path to weather zones GeoPackage (deprecated if using GPKG for profiles)
        fallback_function : callable, optional
            Function to call if profile lookup fails.
            Should have signature: (lat, lon, season, time_of_day) -> dict
        """
        self.profiles_path = profiles_path
        self.zones_path = zones_path
        self.fallback_function = fallback_function

        # Check if using consolidated GPKG format
        self.use_gpkg = profiles_path.endswith('.gpkg')

        self.profiles_df = None
        self.zones_gdf = None
        self.profile_index = {}  # Fast lookup: (zone_id, season, time_of_day) -> weather dict

        self._load()

    def _load(self):
        """Load profiles and zones into memory."""
        try:
            # Check if file exists
            if not os.path.exists(self.profiles_path):
                raise WeatherProfileError(
                    f"Profiles file not found: {self.profiles_path}"
                )

            if self.use_gpkg:
                # Load from consolidated GPKG
                logging.info(f"Loading Israel weather profiles from {self.profiles_path}")

                # Read profiles from 'profiles' table using sqlite3
                import sqlite3
                conn = sqlite3.connect(self.profiles_path)
                self.profiles_df = pd.read_sql("SELECT * FROM profiles", conn)
                conn.close()

                # Load zones from 'zones' layer
                logging.info(f"Loading Israel weather zones from {self.profiles_path}")
                self.zones_gdf = load_israel_weather_zones(self.profiles_path, layer='zones')

            else:
                # Load from separate parquet + GPKG files (legacy format)
                logging.info(f"Loading Israel weather profiles from {self.profiles_path}")
                self.profiles_df = pd.read_parquet(self.profiles_path)

                # Load weather zones
                if not self.zones_path or not os.path.exists(self.zones_path):
                    raise WeatherProfileError(
                        f"Zones file not found: {self.zones_path}"
                    )

                logging.info(f"Loading Israel weather zones from {self.zones_path}")
                self.zones_gdf = load_israel_weather_zones(self.zones_path)

            # Validate required columns
            required_cols = ['zone_id', 'season', 'time_of_day',
                           'temperature', 'precipitation', 'wind_speed']
            missing_cols = set(required_cols) - set(self.profiles_df.columns)
            if missing_cols:
                raise WeatherProfileError(
                    f"Missing required columns in profiles: {missing_cols}"
                )

            # Build fast lookup index
            self._build_index()

            logging.info(f"Loaded {len(self.profiles_df)} weather profiles")
            logging.info(f"Loaded {len(self.zones_gdf)} weather zones")

            # Log summary statistics
            self._log_summary()

        except Exception as e:
            logging.error(f"Failed to load weather profile store: {e}")
            raise WeatherProfileError(f"Initialization failed: {e}")

    def _build_index(self):
        """Build fast lookup index from DataFrame."""
        for _, row in self.profiles_df.iterrows():
            key = (row['zone_id'], row['season'], row['time_of_day'])
            value = {
                'temperature': row['temperature'],
                'precipitation': row['precipitation'],
                'wind_speed': row['wind_speed']
            }
            self.profile_index[key] = value

        logging.info(f"Built lookup index with {len(self.profile_index)} entries")

    def _log_summary(self):
        """Log summary statistics about loaded profiles."""
        if self.profiles_df is None:
            return

        # Count by season
        seasons = self.profiles_df['season'].value_counts()
        logging.info(f"Profiles by season: {seasons.to_dict()}")

        # Temperature ranges
        temp_stats = self.profiles_df.groupby('season')['temperature'].agg(['min', 'max', 'mean'])
        logging.info(f"Temperature ranges:\n{temp_stats}")

    def is_loaded(self) -> bool:
        """
        Check if store is properly loaded.

        Returns
        -------
        bool
            True if profiles and zones are loaded
        """
        return (self.profiles_df is not None and
                self.zones_gdf is not None and
                len(self.profile_index) > 0)

    def get_weather_for_zone(self,
                            zone_id: str,
                            season: str,
                            time_of_day: str) -> Optional[Dict[str, float]]:
        """
        Look up weather profile for a specific zone.

        Parameters
        ----------
        zone_id : str
            Zone identifier (e.g., "IL_000")
        season : str
            Season: 'winter', 'spring', 'summer', 'autumn'
        time_of_day : str
            Time of day: 'morning', 'afternoon', 'evening', 'night'

        Returns
        -------
        dict or None
            Weather dict with temperature, precipitation, wind_speed, or None if not found
        """
        key = (zone_id, season.lower(), time_of_day.lower())
        return self.profile_index.get(key)

    def get_weather_for_geometry(self,
                                 geom,
                                 season: str,
                                 time_of_day: str) -> Dict[str, float]:
        """
        Get weather profile for a geometry (street network, polygon, point, etc.).

        Uses the geometry's centroid to find the containing weather zone,
        then looks up precomputed weather for that zone.

        Parameters
        ----------
        geom : shapely geometry
            Any shapely geometry (uses centroid for lookup)
        season : str
            Season: 'winter', 'spring', 'summer', 'autumn'
        time_of_day : str
            Time of day: 'morning', 'afternoon', 'evening', 'night'

        Returns
        -------
        dict
            Weather profile with keys: temperature, precipitation, wind_speed

        Raises
        ------
        WeatherProfileError
            If lookup fails and no fallback is available
        """
        if not self.is_loaded():
            raise WeatherProfileError("Weather profile store not loaded")

        try:
            # Find zone for geometry
            zone_id = find_zone_for_geometry(self.zones_gdf, geom)

            if zone_id is None:
                raise WeatherProfileError("Could not find zone for geometry")

            # Look up weather profile
            weather = self.get_weather_for_zone(zone_id, season, time_of_day)

            if weather is None:
                raise WeatherProfileError(
                    f"No profile found for zone={zone_id}, "
                    f"season={season}, time_of_day={time_of_day}"
                )

            # Check for NaN values (failed precomputation)
            if pd.isna(weather['temperature']):
                logging.warning(f"Profile for {zone_id}/{season}/{time_of_day} "
                              f"has NaN values, using fallback")
                raise WeatherProfileError("Profile has invalid data")

            logging.info(f"Using precomputed Israel weather profile: "
                        f"zone={zone_id}, season={season}, time_of_day={time_of_day}")

            return weather

        except WeatherProfileError as e:
            # Fallback to live weather fetch if available
            if self.fallback_function:
                logging.warning(f"Profile lookup failed ({e}), using fallback")

                # Get centroid for fallback
                centroid = geom.centroid
                lat, lon = centroid.y, centroid.x

                return self.fallback_function(
                    latitude=lat,
                    longitude=lon,
                    season=season,
                    time_of_day=time_of_day
                )
            else:
                logging.error(f"Profile lookup failed and no fallback available: {e}")
                raise

    def get_zones_count(self) -> int:
        """Get number of loaded zones."""
        return len(self.zones_gdf) if self.zones_gdf is not None else 0

    def get_profiles_count(self) -> int:
        """Get number of loaded profiles."""
        return len(self.profiles_df) if self.profiles_df is not None else 0


# Global singleton instance (initialized in app.py)
_ISRAEL_WEATHER_STORE = None


def initialize_israel_weather_store(profiles_path: str,
                                    zones_path: str,
                                    fallback_function: Optional[callable] = None) -> IsraelWeatherProfileStore:
    """
    Initialize the global Israel weather profile store.

    Should be called once at app startup.

    Parameters
    ----------
    profiles_path : str
        Path to precomputed profiles parquet
    zones_path : str
        Path to weather zones GeoPackage
    fallback_function : callable, optional
        Fallback function for live weather fetch

    Returns
    -------
    IsraelWeatherProfileStore
        Initialized store
    """
    global _ISRAEL_WEATHER_STORE

    try:
        _ISRAEL_WEATHER_STORE = IsraelWeatherProfileStore(
            profiles_path=profiles_path,
            zones_path=zones_path,
            fallback_function=fallback_function
        )
        logging.info("Israel weather profile store initialized successfully")
        return _ISRAEL_WEATHER_STORE

    except Exception as e:
        logging.error(f"Failed to initialize Israel weather store: {e}")
        logging.warning("Will use live weather fetch for all requests")
        _ISRAEL_WEATHER_STORE = None
        return None


def get_israel_weather_store() -> Optional[IsraelWeatherProfileStore]:
    """
    Get the global Israel weather profile store.

    Returns
    -------
    IsraelWeatherProfileStore or None
        Store instance if initialized, None otherwise
    """
    return _ISRAEL_WEATHER_STORE


if __name__ == "__main__":
    # Test the store
    import logging
    from shapely.geometry import Point

    logging.basicConfig(level=logging.INFO)

    print("\n=== Testing Weather Profile Store ===")

    # Paths (adjust as needed)
    profiles_path = "data/processed/israel/israel_weather_profiles.parquet"
    zones_path = "data/processed/israel/israel_weather_zones.gpkg"

    if not os.path.exists(profiles_path):
        print(f"ERROR: Profiles file not found: {profiles_path}")
        print("Run scripts/precompute_israel_weather_profiles.py first")
        exit(1)

    # Initialize store
    print(f"\nLoading profiles from {profiles_path}")
    store = IsraelWeatherProfileStore(profiles_path, zones_path)

    print(f"\nStore loaded:")
    print(f"  Zones: {store.get_zones_count()}")
    print(f"  Profiles: {store.get_profiles_count()}")

    # Test lookups for Tel Aviv
    print("\n=== Test: Tel Aviv ===")
    tel_aviv_point = Point(34.7818, 32.0853)

    for season in ["winter", "summer"]:
        for time_of_day in ["morning", "evening"]:
            weather = store.get_weather_for_geometry(
                tel_aviv_point, season, time_of_day
            )
            print(f"{season:10s} {time_of_day:10s}: "
                  f"temp={weather['temperature']:.1f}°C, "
                  f"precip={weather['precipitation']:.1f}mm, "
                  f"wind={weather['wind_speed']:.1f}km/h")
