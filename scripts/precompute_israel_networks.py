#!/usr/bin/env python3
"""
Precompute street networks for Israel weather zones.

Downloads OSM networks for each zone, computes centrality features,
and saves to GPKG files for fast predictions.

Usage:
    # High precision (200 zones)
    python scripts/precompute_israel_networks.py --grid 20x10

    # Maximum precision (800 zones)
    python scripts/precompute_israel_networks.py --grid 40x40

    # Resume from specific zone
    python scripts/precompute_israel_networks.py --grid 20x10 --start-zone 50
"""
import sys
import os
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime
import geopandas as gpd
import osmnx as ox
import networkx as nx
from shapely.geometry import box

# Add api directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))

from feature_engineering.israel_weather_zones import generate_israel_weather_zones

# Configure OSMnx to handle larger query areas
ox.settings.max_query_area_size = 50000000000  # 50 billion m² (was 2.5 billion)


def setup_logging():
    """Configure logging."""
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'network_precomputation.log'

    # Configure logging to both file and console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    # Suppress OSMnx verbose logging
    logging.getLogger('osmnx').setLevel(logging.WARNING)

    logging.info(f"Logging to: {log_file}")


def download_network_for_zone(zone_geometry, zone_id: str, network_type: str = 'walk'):
    """
    Download OSM network for a zone's bounding box.

    Parameters
    ----------
    zone_geometry : shapely Polygon
        Zone boundary polygon
    zone_id : str
        Zone identifier
    network_type : str
        OSM network type ('walk', 'drive', 'bike')

    Returns
    -------
    GeoDataFrame or None
        Network edges with geometry, or None if download fails
    """
    try:
        # Get bounding box
        bounds = zone_geometry.bounds  # (minx, miny, maxx, maxy)
        west, south, east, north = bounds

        logging.info(f"  Downloading OSM network for {zone_id}...")
        logging.info(f"    Bbox: ({west:.4f}, {south:.4f}, {east:.4f}, {north:.4f})")

        # Download street network
        # OSMnx expects bbox as (north, south, east, west) tuple
        G = ox.graph_from_bbox(
            bbox=(north, south, east, west),
            network_type=network_type,
            simplify=True,
            retain_all=False
        )

        # Convert to GeoDataFrame
        edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True)

        logging.info(f"  ✓ Downloaded {len(edges_gdf)} edges for {zone_id}")

        return G, edges_gdf

    except Exception as e:
        logging.error(f"  ✗ Failed to download network for {zone_id}: {e}")
        return None, None


def compute_centrality(G, edges_gdf):
    """
    Compute betweenness and closeness centrality for network edges.

    Parameters
    ----------
    G : networkx.MultiDiGraph
        Street network graph
    edges_gdf : GeoDataFrame
        Network edges

    Returns
    -------
    GeoDataFrame
        Edges with centrality columns added
    """
    logging.info(f"  Computing centrality for {len(edges_gdf)} edges...")
    start_time = time.time()

    try:
        # Compute edge betweenness centrality
        logging.info("    Computing betweenness centrality...")
        edge_betweenness = nx.edge_betweenness_centrality(G, weight='length')

        # Compute closeness centrality (node-based, then average for edges)
        logging.info("    Computing closeness centrality...")
        node_closeness = nx.closeness_centrality(G, distance='length')

        # Add centrality to edges
        betweenness_list = []
        closeness_list = []

        for idx, row in edges_gdf.iterrows():
            u, v, key = idx if isinstance(idx, tuple) else (row['u'], row['v'], row.get('key', 0))

            # Betweenness (edge-level)
            betweenness = edge_betweenness.get((u, v, key), 0.0)
            betweenness_list.append(betweenness)

            # Closeness (average of u and v nodes)
            closeness_u = node_closeness.get(u, 0.0)
            closeness_v = node_closeness.get(v, 0.0)
            closeness = (closeness_u + closeness_v) / 2
            closeness_list.append(closeness)

        edges_gdf['betweenness'] = betweenness_list
        edges_gdf['closeness'] = closeness_list

        elapsed = time.time() - start_time
        logging.info(f"  ✓ Centrality computed in {elapsed:.1f}s")

        return edges_gdf

    except Exception as e:
        logging.error(f"  ✗ Failed to compute centrality: {e}")
        # Add zero centrality on failure
        edges_gdf['betweenness'] = 0.0
        edges_gdf['closeness'] = 0.0
        return edges_gdf


def save_network(edges_gdf, output_path: Path, zone_id: str):
    """
    Save network to GPKG file.

    Parameters
    ----------
    edges_gdf : GeoDataFrame
        Network edges with centrality
    output_path : Path
        Output file path
    zone_id : str
        Zone identifier
    """
    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Select essential columns to save
        columns_to_save = [
            'geometry',
            'u', 'v', 'key',
            'highway',
            'betweenness',
            'closeness',
            'length'
        ]

        # Keep only columns that exist
        available_cols = [col for col in columns_to_save if col in edges_gdf.columns]
        save_gdf = edges_gdf[available_cols].copy()

        # Save to GPKG using pyogrio (more reliable for Render)
        try:
            save_gdf.to_file(output_path, driver="GPKG", layer="edges", engine="pyogrio")
        except Exception:
            # Fallback to fiona
            save_gdf.to_file(output_path, driver="GPKG", layer="edges")

        # Get file size
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logging.info(f"  ✓ Saved to {output_path.name} ({file_size_mb:.2f} MB)")

    except Exception as e:
        logging.error(f"  ✗ Failed to save network for {zone_id}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Precompute street networks for Israel weather zones"
    )
    parser.add_argument(
        '--grid',
        type=str,
        default='20x10',
        help='Grid size as "COLSxROWS" (e.g., "20x10" for 200 zones, "40x40" for 1600 zones)'
    )
    parser.add_argument(
        '--start-zone',
        type=int,
        default=0,
        help='Start from this zone index (for resuming)'
    )
    parser.add_argument(
        '--network-type',
        type=str,
        default='walk',
        choices=['walk', 'drive', 'bike', 'all'],
        help='OSM network type to download'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/processed/israel/networks',
        help='Output directory for network files'
    )

    args = parser.parse_args()

    setup_logging()

    # Parse grid size
    try:
        cols, rows = map(int, args.grid.split('x'))
    except ValueError:
        logging.error("Invalid grid format. Use 'COLSxROWS' (e.g., '20x10')")
        return 1

    total_zones = cols * rows

    logging.info("=" * 80)
    logging.info("PRECOMPUTE ISRAEL STREET NETWORKS")
    logging.info("=" * 80)
    logging.info(f"Grid size: {cols}×{rows} = {total_zones} zones")
    logging.info(f"Network type: {args.network_type}")
    logging.info(f"Output directory: {args.output_dir}")
    logging.info(f"Starting from zone: {args.start_zone}")
    logging.info("=" * 80)

    # Generate zones
    logging.info(f"\nGenerating {total_zones} weather zones...")
    zones_gdf = generate_israel_weather_zones(n_cols=cols, n_rows=rows)
    logging.info(f"✓ Generated {len(zones_gdf)} zones")

    # Save zones
    zones_output_dir = Path("data/processed/israel")
    zones_output_path = zones_output_dir / f"israel_weather_zones_{args.grid}.gpkg"
    zones_output_dir.mkdir(parents=True, exist_ok=True)
    zones_gdf.to_file(zones_output_path, driver="GPKG", layer="zones")
    logging.info(f"✓ Saved zones to {zones_output_path}")

    # Process each zone
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    success_count = 0
    failed_zones = []

    for idx, zone in zones_gdf.iterrows():
        zone_idx = int(zone['zone_id'].split('_')[1])

        # Skip zones before start index
        if zone_idx < args.start_zone:
            continue

        zone_id = zone['zone_id']
        geometry = zone['geometry']

        logging.info(f"\n[{zone_idx + 1}/{total_zones}] Processing {zone_id}...")

        # Output file path
        output_file = output_dir / f"{zone_id}_network.gpkg"

        # Skip if already exists
        if output_file.exists():
            logging.info(f"  ⊙ Already exists, skipping: {output_file.name}")
            success_count += 1
            continue

        # Download network
        G, edges_gdf = download_network_for_zone(geometry, zone_id, args.network_type)

        if G is None or edges_gdf is None or len(edges_gdf) == 0:
            logging.warning(f"  ⊙ No network data for {zone_id} (likely unpopulated area)")
            failed_zones.append(zone_id)
            continue

        # Compute centrality
        edges_gdf = compute_centrality(G, edges_gdf)

        # Save to GPKG
        save_network(edges_gdf, output_file, zone_id)

        success_count += 1

        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        avg_time_per_zone = elapsed / (zone_idx - args.start_zone + 1)
        remaining_zones = total_zones - zone_idx - 1
        eta_seconds = avg_time_per_zone * remaining_zones
        eta_hours = eta_seconds / 3600

        logging.info(f"  Progress: {zone_idx + 1}/{total_zones} ({100*(zone_idx+1)/total_zones:.1f}%)")
        logging.info(f"  Avg time/zone: {avg_time_per_zone:.1f}s | ETA: {eta_hours:.1f}h")

        # Brief pause to avoid rate limiting
        time.sleep(2)

    # Summary
    total_time = (datetime.now() - start_time).total_seconds()
    total_hours = total_time / 3600

    logging.info("\n" + "=" * 80)
    logging.info("SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Total zones: {total_zones}")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Failed/skipped: {len(failed_zones)}")
    logging.info(f"Total time: {total_hours:.2f} hours")

    if failed_zones:
        logging.info(f"\nFailed zones: {', '.join(failed_zones[:10])}")
        if len(failed_zones) > 10:
            logging.info(f"  ... and {len(failed_zones) - 10} more")

    # Calculate total storage
    total_size_mb = sum(
        f.stat().st_size for f in output_dir.glob("*.gpkg")
    ) / (1024 * 1024)
    logging.info(f"\nTotal storage: {total_size_mb:.1f} MB ({total_size_mb/1024:.2f} GB)")

    logging.info("\n" + "=" * 80)
    logging.info("NEXT STEPS")
    logging.info("=" * 80)
    logging.info("1. Upload networks to Vultr:")
    logging.info(f"   python scripts/upload_networks_to_vultr.py --grid {args.grid}")
    logging.info("2. Update app.py to use precomputed networks")
    logging.info("3. Deploy to Render")

    return 0


if __name__ == '__main__':
    sys.exit(main())
