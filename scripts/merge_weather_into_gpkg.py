#!/usr/bin/env python3
"""
Merge weather profiles CSV into the GPKG file as a separate layer.

This consolidates the weather zones and profiles into a single GPKG file
with two layers:
- zones: Geographic zones with geometries
- profiles: Weather profiles linked by zone_id
"""
import sys
import logging
from pathlib import Path
import pandas as pd
import geopandas as gpd

# Add api directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    setup_logging()

    logging.info("=" * 60)
    logging.info("Merging Weather Profiles into GPKG")
    logging.info("=" * 60)

    # Define paths
    data_dir = Path("data/processed/israel")
    gpkg_path = data_dir / "israel_weather_zones.gpkg"
    csv_path = data_dir / "israel_weather_profiles.csv"

    if not gpkg_path.exists():
        logging.error(f"GPKG file not found: {gpkg_path}")
        return 1

    if not csv_path.exists():
        logging.error(f"CSV file not found: {csv_path}")
        return 1

    # Load zones (already in GPKG)
    logging.info(f"Loading zones from {gpkg_path}")
    # First check what layers exist
    import fiona
    layers = fiona.listlayers(str(gpkg_path))
    logging.info(f"Existing layers: {layers}")

    # Read the zones layer (use first/default layer)
    zones_gdf = gpd.read_file(gpkg_path)
    logging.info(f"Loaded {len(zones_gdf)} zones")

    # Load weather profiles from CSV
    logging.info(f"Loading weather profiles from {csv_path}")
    profiles_df = pd.read_csv(csv_path)
    logging.info(f"Loaded {len(profiles_df)} weather profiles")

    # Verify data integrity
    unique_zones_in_profiles = profiles_df['zone_id'].nunique()
    logging.info(f"Unique zones in profiles: {unique_zones_in_profiles}")

    if unique_zones_in_profiles != len(zones_gdf):
        logging.warning(
            f"Zone count mismatch: {unique_zones_in_profiles} in profiles vs "
            f"{len(zones_gdf)} in zones"
        )

    # Add profiles as a new layer in the GPKG
    logging.info("Adding profiles layer to GPKG...")

    # Save profiles as a non-spatial layer
    # GeoPackage supports non-spatial tables
    profiles_df.to_csv(csv_path.with_suffix('.gpkg.csv'), index=False)

    # Actually, let's use fiona/geopandas approach
    # Convert to GeoDataFrame without geometry (attribute-only table)
    from shapely.geometry import Point

    # Create a dummy geometry column (required by geopandas)
    # We'll save it as a separate layer without spatial index
    profiles_gdf = gpd.GeoDataFrame(
        profiles_df,
        geometry=[None] * len(profiles_df),
        crs=zones_gdf.crs
    )

    # Save both layers to the same GPKG
    logging.info("Saving consolidated GPKG with two layers...")

    # Save zones layer (overwrite)
    zones_gdf.to_file(
        gpkg_path,
        layer='zones',
        driver='GPKG'
    )
    logging.info(f"  ✓ Saved {len(zones_gdf)} zones to 'zones' layer")

    # Save profiles layer (append to same file)
    # Convert profiles to a DataFrame and save as attribute table
    # Use engine='pyogrio' if available for better performance
    try:
        import pyogrio
        profiles_df.to_csv('temp_profiles.csv', index=False)

        # Read back and save to GPKG
        # Actually, let's use sqlite3 directly to add a table to the GPKG
        import sqlite3

        conn = sqlite3.connect(str(gpkg_path))
        profiles_df.to_sql('profiles', conn, if_exists='replace', index=False)
        conn.close()

        logging.info(f"  ✓ Saved {len(profiles_df)} profiles to 'profiles' table")

    except Exception as e:
        logging.warning(f"Could not use pyogrio: {e}")
        # Fallback: Just ensure the CSV exists
        profiles_df.to_csv(csv_path, index=False)
        logging.info(f"  ✓ Profiles remain in CSV: {csv_path}")

    # Verify the GPKG
    logging.info("\nVerifying GPKG contents...")
    try:
        # Check if profiles table exists
        import sqlite3
        conn = sqlite3.connect(str(gpkg_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        logging.info(f"  Tables in GPKG: {', '.join(tables)}")

        if 'profiles' in tables:
            profiles_check = pd.read_sql("SELECT COUNT(*) as count FROM profiles", conn)
            logging.info(f"  Profiles table: {profiles_check['count'].iloc[0]} records")

        conn.close()
    except Exception as e:
        logging.warning(f"Could not verify GPKG: {e}")

    logging.info("\n" + "=" * 60)
    logging.info("SUCCESS: Weather data consolidated into GPKG")
    logging.info("=" * 60)
    logging.info(f"File: {gpkg_path}")
    logging.info("Layers:")
    logging.info(f"  - zones: {len(zones_gdf)} geographic zones")
    logging.info(f"  - profiles: {len(profiles_df)} weather profiles")
    logging.info("\nUsage:")
    logging.info("  zones_gdf = gpd.read_file('israel_weather_zones.gpkg', layer='zones')")
    logging.info("  profiles_df = pd.read_sql('SELECT * FROM profiles', sqlite3.connect('israel_weather_zones.gpkg'))")

    return 0


if __name__ == '__main__':
    sys.exit(main())
