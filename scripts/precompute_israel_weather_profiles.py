#!/usr/bin/env python3
"""
precompute_israel_weather_profiles.py

Offline script to precompute weather profiles for all Israel weather zones.

This script:
1. Loads or generates ~50 weather zones covering Israel
2. For each zone and each (season, time_of_day) combination:
   - Calls the existing weather API logic
   - Samples 5 dates and averages across the season
3. Stores results to:
   - data/processed/israel/israel_weather_profiles.parquet
   - data/processed/israel/israel_weather_profiles.csv (for inspection)

Run this script periodically (e.g., monthly) to refresh weather data.

Usage:
    python scripts/precompute_israel_weather_profiles.py [--force] [--zones-file path]

Options:
    --force          Overwrite existing profiles
    --zones-file     Path to weather zones .gpkg file (default: auto-detect)
    --output-dir     Output directory (default: data/processed/israel)
"""
import sys
import os
import logging
import argparse
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
import geopandas as gpd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

# Import our modules
from feature_engineering.israel_weather_zones import (
    load_israel_weather_zones,
    generate_israel_weather_zones,
    save_israel_weather_zones
)
from feature_engineering.weather_features import get_seasonal_weather_profile


# Configuration
SEASONS = ["winter", "spring", "summer", "autumn"]
TIMES_OF_DAY = ["morning", "afternoon", "evening", "night"]


def setup_logging():
    """Configure logging for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('precompute_weather.log')
        ]
    )


def precompute_zone_weather(zone_id: str,
                           center_lat: float,
                           center_lon: float,
                           seasons: list,
                           times_of_day: list) -> list:
    """
    Precompute weather for one zone across all season/time_of_day combinations.

    Parameters
    ----------
    zone_id : str
        Zone identifier (e.g., "IL_000")
    center_lat : float
        Zone center latitude
    center_lon : float
        Zone center longitude
    seasons : list
        List of seasons to compute
    times_of_day : list
        List of times of day to compute

    Returns
    -------
    list
        List of dicts, one per (season, time_of_day) combo
    """
    results = []

    for season in seasons:
        for time_of_day in times_of_day:
            try:
                logging.info(f"Computing {zone_id}: {season}/{time_of_day}")

                # Call the existing weather function
                weather_data = get_seasonal_weather_profile(
                    latitude=center_lat,
                    longitude=center_lon,
                    season=season,
                    time_of_day=time_of_day,
                    n_samples=5
                )

                # Store result
                results.append({
                    'zone_id': zone_id,
                    'season': season,
                    'time_of_day': time_of_day,
                    'temperature': weather_data['temperature'],
                    'precipitation': weather_data['precipitation'],
                    'wind_speed': weather_data['wind_speed'],
                    'computed_at': datetime.now().isoformat()
                })

                # Small delay to avoid rate limiting
                time.sleep(0.5)

            except Exception as e:
                logging.error(f"Failed to compute weather for {zone_id} "
                            f"{season}/{time_of_day}: {e}")
                # Store with NaN values so we can detect failures
                results.append({
                    'zone_id': zone_id,
                    'season': season,
                    'time_of_day': time_of_day,
                    'temperature': None,
                    'precipitation': None,
                    'wind_speed': None,
                    'computed_at': datetime.now().isoformat(),
                    'error': str(e)
                })

    return results


def main():
    """Main script execution."""
    parser = argparse.ArgumentParser(
        description="Precompute weather profiles for Israel zones"
    )
    parser.add_argument('--force', action='store_true',
                       help="Overwrite existing profiles")
    parser.add_argument('--zones-file', type=str,
                       help="Path to weather zones .gpkg file")
    parser.add_argument('--output-dir', type=str,
                       default='data/processed/israel',
                       help="Output directory")
    parser.add_argument('--test-mode', action='store_true',
                       help="Test mode: only process first 3 zones")

    args = parser.parse_args()

    setup_logging()

    logging.info("="*60)
    logging.info("Israel Weather Profiles Precomputation")
    logging.info("="*60)

    # Define output paths
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = output_dir / "israel_weather_profiles.parquet"
    csv_path = output_dir / "israel_weather_profiles.csv"
    zones_path = output_dir / "israel_weather_zones.gpkg"

    # Check if profiles already exist
    if parquet_path.exists() and not args.force:
        logging.error(f"Profiles already exist at {parquet_path}")
        logging.error("Use --force to overwrite")
        return 1

    # Load or generate weather zones
    logging.info("\n" + "="*60)
    logging.info("Step 1: Loading Weather Zones")
    logging.info("="*60)

    try:
        if args.zones_file:
            zones_gdf = load_israel_weather_zones(args.zones_file)
        elif zones_path.exists():
            zones_gdf = load_israel_weather_zones(str(zones_path))
        else:
            logging.info("Generating new weather zones...")
            zones_gdf = generate_israel_weather_zones(n_cols=10, n_rows=5)
            save_israel_weather_zones(zones_gdf, str(zones_path))

        logging.info(f"Loaded {len(zones_gdf)} weather zones")

        # Test mode: only process first 3 zones
        if args.test_mode:
            logging.warning("TEST MODE: Only processing first 3 zones")
            zones_gdf = zones_gdf.head(3)

    except Exception as e:
        logging.error(f"Failed to load/generate zones: {e}")
        return 1

    # Precompute weather for all zones
    logging.info("\n" + "="*60)
    logging.info("Step 2: Precomputing Weather Profiles")
    logging.info("="*60)
    logging.info(f"Total combinations: {len(zones_gdf)} zones × "
                f"{len(SEASONS)} seasons × {len(TIMES_OF_DAY)} times = "
                f"{len(zones_gdf) * len(SEASONS) * len(TIMES_OF_DAY)} API calls")

    all_results = []
    start_time = time.time()

    for idx, zone in zones_gdf.iterrows():
        zone_id = zone['zone_id']
        center_lat = zone['center_lat']
        center_lon = zone['center_lon']

        logging.info(f"\nProcessing zone {idx+1}/{len(zones_gdf)}: {zone_id} "
                    f"({center_lat:.4f}, {center_lon:.4f})")

        zone_results = precompute_zone_weather(
            zone_id=zone_id,
            center_lat=center_lat,
            center_lon=center_lon,
            seasons=SEASONS,
            times_of_day=TIMES_OF_DAY
        )

        all_results.extend(zone_results)

        # Progress update
        elapsed = time.time() - start_time
        progress = (idx + 1) / len(zones_gdf)
        eta = elapsed / progress - elapsed if progress > 0 else 0
        logging.info(f"Progress: {progress*100:.1f}% | "
                    f"Elapsed: {elapsed/60:.1f}min | "
                    f"ETA: {eta/60:.1f}min")

    # Create DataFrame
    logging.info("\n" + "="*60)
    logging.info("Step 3: Saving Results")
    logging.info("="*60)

    df = pd.DataFrame(all_results)

    # Check for failures
    failed_count = df['temperature'].isna().sum()
    if failed_count > 0:
        logging.warning(f"{failed_count} weather fetches failed (will use defaults at runtime)")

    # Save to parquet (primary format for production)
    logging.info(f"Saving to parquet: {parquet_path}")
    df.to_parquet(parquet_path, index=False, engine='pyarrow')

    # Save to CSV (for manual inspection)
    logging.info(f"Saving to CSV: {csv_path}")
    df.to_csv(csv_path, index=False)

    # Summary statistics
    logging.info("\n" + "="*60)
    logging.info("Summary")
    logging.info("="*60)
    logging.info(f"Total profiles computed: {len(df)}")
    logging.info(f"Successful: {len(df) - failed_count}")
    logging.info(f"Failed: {failed_count}")
    logging.info(f"Total time: {(time.time() - start_time)/60:.1f} minutes")

    logging.info("\nTemperature statistics:")
    logging.info(df.groupby(['season', 'time_of_day'])['temperature'].describe())

    logging.info("\n" + "="*60)
    logging.info("Precomputation Complete!")
    logging.info("="*60)
    logging.info(f"Profiles saved to: {parquet_path}")
    logging.info(f"CSV for inspection: {csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
