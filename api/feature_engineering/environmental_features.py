#!/usr/bin/env python3
"""
environmental_features.py

Provides environmental features for pedestrian volume prediction.
Extracts real data from DEM and NDVI rasters stored in Vultr Object Storage.
"""
import logging
import pandas as pd
import geopandas as gpd
import numpy as np
from typing import Optional, Tuple
import os

try:
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.io import MemoryFile
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False
    logging.warning("rasterio not installed. Environmental features will use defaults.")


class EnvironmentalError(Exception):
    """Exception for environmental feature extraction errors."""
    def __init__(self, message: str, code: int = 500, details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


def get_raster_url_from_vultr(raster_type: str, bounds: Tuple[float, float, float, float], city: Optional[str] = None) -> Optional[str]:
    """
    Get presigned URL for raster file from Vultr storage.

    Tries to use city-specific rasters first for better performance,
    falls back to national rasters if city files not available.

    Args:
        raster_type: Type of raster ('ndvi' or 'dem')
        bounds: Bounding box (minx, miny, maxx, maxy) in EPSG:4326
        city: Optional city name to use city-specific rasters

    Returns:
        Presigned URL or None if not available
    """
    try:
        import sys
        from pathlib import Path
        # Add parent directory to path to import storage_utils
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from storage_utils import get_vultr_storage

        storage = get_vultr_storage()
        if not storage:
            return None

        raster_file = None

        # Try city-specific raster first if city is provided
        if city:
            city_raster = f"data/processed/israel/cities/{city}/{city}_{raster_type}.tif"
            if storage.file_exists(city_raster):
                raster_file = city_raster
                logging.info(f"Using city-specific {raster_type} raster for {city}")
            else:
                logging.info(f"City-specific {raster_type} not found for {city}, trying national fallback")

        # If city-specific file not found, try national rasters as fallback
        if not raster_file:
            # National rasters are in the project/ directory in Vultr
            national_raster_map = {
                "ndvi": "project/data/processed/israel/rasters/israel_ndvi_sentinel2.tif",
                "dem": "project/data/processed/israel/rasters/israel_dem_copernicus30.tif"
            }

            national_raster = national_raster_map.get(raster_type)
            if national_raster and storage.file_exists(national_raster):
                raster_file = national_raster
                logging.info(f"Using national {raster_type} raster as fallback: {national_raster}")
            else:
                if city:
                    logging.info(f"City-specific {raster_type} not available for {city}, and no national fallback found, using default values")
                else:
                    logging.info(f"No city specified for {raster_type}, using default values")
                return None

        # Generate direct public URL (bucket has public read policy)
        # Format: https://bucket-name.endpoint/object-key
        bucket_name = storage.bucket_name
        endpoint = storage.endpoint_url.replace('https://', '')
        url = f"https://{bucket_name}.{endpoint}/{raster_file}"
        logging.info(f"Generated public URL for {raster_type}: {raster_file}")
        return url

    except Exception as e:
        logging.error(f"Failed to get {raster_type} raster URL: {e}")
        return None


def sample_raster_at_points(raster_url: str, gdf: gpd.GeoDataFrame, buffer_meters: float = 10.0) -> np.ndarray:
    """
    Sample raster values at street edge locations with buffer averaging.

    For better vegetation detection, samples at street center + 2 buffer points
    on each side, then takes the maximum value to represent canopy coverage.

    Args:
        raster_url: URL to Cloud Optimized GeoTIFF
        gdf: GeoDataFrame with street edges
        buffer_meters: Distance (in meters) to sample on each side of street centerline

    Returns:
        Array of sampled values (maximum of center + buffer samples)
    """
    if not RASTERIO_AVAILABLE:
        return None

    try:
        # Ensure WGS84 for coordinate matching
        if gdf.crs and gdf.crs != "EPSG:4326":
            gdf_wgs84 = gdf.to_crs("EPSG:4326")
        else:
            gdf_wgs84 = gdf

        # Calculate centroids in projected CRS to avoid geographic CRS warning
        # Use Web Mercator (EPSG:3857) for accurate centroid calculation and buffering
        gdf_projected = gdf_wgs84.to_crs("EPSG:3857")
        centroids_projected = gdf_projected.geometry.centroid

        # For each street, sample at center and optionally at perpendicular offsets
        # Buffer sampling helps detect tree canopy along streets
        all_sample_coords = []
        use_buffer = buffer_meters > 0

        for idx, (geom, centroid) in enumerate(zip(gdf_projected.geometry, centroids_projected)):
            center_coords = (centroid.x, centroid.y)

            if use_buffer:
                # Get the bearing of the street at the centroid
                # For LineString, get the angle from the line direction
                coords_line = list(geom.coords)
                if len(coords_line) >= 2:
                    # Use midpoint direction
                    mid_idx = len(coords_line) // 2
                    if mid_idx > 0:
                        dx = coords_line[mid_idx][0] - coords_line[mid_idx-1][0]
                        dy = coords_line[mid_idx][1] - coords_line[mid_idx-1][1]
                    else:
                        dx = coords_line[1][0] - coords_line[0][0]
                        dy = coords_line[1][1] - coords_line[0][1]

                    # Calculate perpendicular offset (90 degrees)
                    length = np.sqrt(dx**2 + dy**2)
                    if length > 0:
                        # Perpendicular unit vector
                        perp_x = -dy / length
                        perp_y = dx / length

                        # Sample points: center, left side, right side
                        left_coords = (centroid.x + perp_x * buffer_meters, centroid.y + perp_y * buffer_meters)
                        right_coords = (centroid.x - perp_x * buffer_meters, centroid.y - perp_y * buffer_meters)

                        all_sample_coords.append([center_coords, left_coords, right_coords])
                    else:
                        # Fallback: just use center
                        all_sample_coords.append([center_coords] * 3)
                else:
                    # Fallback: just use center
                    all_sample_coords.append([center_coords] * 3)
            else:
                # No buffer: just sample at center (for DEM)
                all_sample_coords.append([center_coords])

        # Convert all sample points back to WGS84
        all_coords_wgs84 = []
        for sample_set in all_sample_coords:
            sample_gdf = gpd.GeoDataFrame(
                geometry=gpd.points_from_xy([c[0] for c in sample_set], [c[1] for c in sample_set]),
                crs="EPSG:3857"
            )
            sample_wgs84 = sample_gdf.to_crs("EPSG:4326")
            coords_wgs84 = [(point.x, point.y) for point in sample_wgs84.geometry]
            all_coords_wgs84.append(coords_wgs84)

        # Flatten for single sampling call
        coords = [coord for sample_set in all_coords_wgs84 for coord in sample_set]

        # Sample raster at point locations
        with rasterio.open(raster_url) as src:
            # Transform coordinates from WGS84 to raster's CRS
            if src.crs and src.crs != "EPSG:4326":
                # Convert WGS84 points to raster's CRS
                from pyproj import Transformer
                transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                coords_transformed = [transformer.transform(x, y) for x, y in coords]
            else:
                coords_transformed = coords

            # Sample values at transformed coordinates
            values = [val[0] for val in src.sample(coords_transformed)]
            values_array = np.array(values)

            # Handle NoData values (common value is -9999)
            nodata = src.nodata
            if nodata is not None:
                # Replace NoData with NaN for proper handling
                values_array = np.where(values_array == nodata, np.nan, values_array)

            # Process based on whether buffer sampling was used
            n_streets = len(gdf)
            if use_buffer:
                # Reshape to (n_streets, 3) for center + left + right samples
                values_reshaped = values_array.reshape(n_streets, 3)

                # Check if all values are NaN (no coverage)
                if np.isnan(values_reshaped).all():
                    logging.warning("All sampled raster values are NaN (no coverage for this area)")
                    return np.full(n_streets, np.nan)

                # Take maximum value across center and buffer samples
                # This captures roadside vegetation better than just center sampling
                result_values = np.nanmax(values_reshaped, axis=1)
            else:
                # No buffer: check for all-NaN before returning
                if np.isnan(values_array).all():
                    logging.warning("All sampled raster values are NaN (no coverage for this area)")
                    return np.full(n_streets, np.nan)

                # No buffer: just return center values directly
                result_values = values_array

            return result_values

    except Exception as e:
        logging.error(f"Failed to sample raster: {e}", exc_info=True)
        return None


def calculate_terrain_complexity(dem_values: np.ndarray, gdf: gpd.GeoDataFrame) -> np.ndarray:
    """
    Calculate terrain complexity from DEM elevation values.

    Uses elevation variance within a local neighborhood as a proxy for complexity.

    Args:
        dem_values: Array of elevation values, may contain NaN
        gdf: GeoDataFrame (for spatial context)

    Returns:
        Normalized complexity values [0-1]
    """
    try:
        # Check if all values are NaN (no coverage)
        if np.isnan(dem_values).all():
            logging.warning("All DEM values are NaN (no coverage); using default terrain complexity")
            return np.full(len(dem_values), 0.5)

        # Simple approach: use elevation range/variance as complexity
        # In production, this would use a proper TPI (Topographic Position Index) calculation

        # Normalize values to 0-1 range based on variance
        if len(dem_values) > 1:
            # Calculate local variance using nanmean to handle NaN
            mean_elev = np.nanmean(dem_values)
            variance = np.abs(dem_values - mean_elev)

            # Handle NaN in variance
            variance = np.where(np.isnan(variance), 0, variance)

            # Check if we have any non-zero variance
            valid_variance = variance[~np.isnan(variance)]
            if len(valid_variance) == 0 or np.nanmax(variance) == 0:
                complexity = np.full_like(dem_values, 0.5)
            else:
                # Normalize to 0-1
                complexity = variance / np.nanmax(variance)
        else:
            complexity = np.full_like(dem_values, 0.5)

        # Replace any remaining NaN with default
        complexity = np.where(np.isnan(complexity), 0.5, complexity)
        return complexity

    except Exception as e:
        logging.error(f"Failed to calculate terrain complexity: {e}", exc_info=True)
        return np.full(len(dem_values), 0.5)


def calculate_topographic_position(dem_values: np.ndarray) -> np.ndarray:
    """
    Calculate topographic position index from DEM values.

    TPI compares elevation of a point to the mean elevation of surrounding area.
    Positive = ridges/peaks, Negative = valleys, Zero = flat/mid-slope

    Args:
        dem_values: Array of elevation values, may contain NaN

    Returns:
        Normalized TPI values [0-1]
    """
    try:
        if len(dem_values) > 1:
            # Check if all values are NaN (no coverage)
            if np.isnan(dem_values).all():
                logging.warning("All DEM values are NaN (no coverage); using default TPI")
                return np.full(len(dem_values), 0.5)

            # Use nanmean to handle NaN values
            mean_elev = np.nanmean(dem_values)
            tpi = dem_values - mean_elev

            # Check if we have any valid values for normalization
            valid_tpi = tpi[~np.isnan(tpi)]
            if len(valid_tpi) == 0:
                logging.warning("No valid DEM values for TPI calculation; using defaults")
                return np.full(len(dem_values), 0.5)

            # Normalize to 0-1 range using nanmin, nanmax
            tpi_range = np.nanmax(tpi) - np.nanmin(tpi)
            if tpi_range > 0:
                tpi_norm = (tpi - np.nanmin(tpi)) / tpi_range
            else:
                tpi_norm = np.full_like(tpi, 0.5)
        else:
            tpi_norm = np.full_like(dem_values, 0.5)

        # Replace any remaining NaN with default
        tpi_norm = np.where(np.isnan(tpi_norm), 0.5, tpi_norm)
        return tpi_norm

    except Exception as e:
        logging.error(f"Failed to calculate topographic position: {e}", exc_info=True)
        return np.full(len(dem_values), 0.5)


def ndvi_to_canopy_pct(ndvi_values: np.ndarray) -> np.ndarray:
    """
    Convert NDVI values to estimated canopy coverage percentage.

    NDVI ranges from -1 to 1:
    - < 0: Water, snow, clouds
    - 0-0.1: Bare soil, rock, sand
    - 0.1-0.3: Sparse vegetation / tree-lined streets
    - 0.3-0.5: Moderate vegetation / parks
    - 0.5-0.7: Dense vegetation/forest
    - > 0.7: Very dense forest

    Args:
        ndvi_values: Array of NDVI values [-1 to 1], may contain NaN

    Returns:
        Array of canopy coverage estimates [0-1]
    """
    try:
        # Handle NaN values - replace with default
        ndvi_clean = np.where(np.isnan(ndvi_values), 0.15, ndvi_values)

        # Clip to valid NDVI range
        ndvi_clipped = np.clip(ndvi_clean, -1, 1)

        # More aggressive mapping for better forest detection:
        # NDVI 0.1 → 0% canopy (bare/sparse)
        # NDVI 0.3 → 33% canopy (tree-lined street)
        # NDVI 0.5 → 67% canopy (park/moderate forest)
        # NDVI 0.7 → 100% canopy (dense forest)
        # Range: 0.1 to 0.7 = 0.6 width
        canopy_pct = np.clip((ndvi_clipped - 0.1) / 0.6, 0, 1)

        return canopy_pct

    except Exception as e:
        logging.error(f"Failed to convert NDVI to canopy: {e}")
        return np.full(len(ndvi_values), 0.3)


def compute_environmental_features(gdf: gpd.GeoDataFrame, city: Optional[str] = None) -> gpd.GeoDataFrame:
    """
    Add environmental features to street edges using real DEM and NDVI data.

    Fetches data from Vultr Object Storage and extracts:
    - sensor_canopy_pct: Tree canopy coverage from NDVI satellite imagery
    - terrain_complexity: Terrain complexity from DEM elevation data
    - topographic_position: Topographic position index from DEM data

    Parameters
    ----------
    gdf : GeoDataFrame
        Street edges to which environmental features will be added
    city : str, optional
        City name to use city-specific rasters (faster, smaller files)

    Returns
    -------
    GeoDataFrame
        The same GeoDataFrame with new columns:
          - sensor_canopy_pct: float [0-1] (tree canopy coverage)
          - terrain_complexity: float [0-1] (terrain complexity index)
          - topographic_position: float [0-1] (topographic position index)

    Raises
    ------
    EnvironmentalError
        If feature computation fails
    """
    try:
        gdf = gdf.copy()

        # Get bounding box
        if gdf.crs and gdf.crs != "EPSG:4326":
            gdf_wgs84 = gdf.to_crs("EPSG:4326")
        else:
            gdf_wgs84 = gdf

        bounds = gdf_wgs84.total_bounds  # (minx, miny, maxx, maxy)

        # Try to get real data from Vultr
        use_real_data = False

        # Try NDVI data with 15m buffer for vegetation detection
        ndvi_url = get_raster_url_from_vultr('ndvi', bounds, city=city)
        if ndvi_url:
            # Use buffer sampling for NDVI to capture roadside trees and parks
            # 15m buffer helps capture trees in parks/forests better
            ndvi_values = sample_raster_at_points(ndvi_url, gdf_wgs84, buffer_meters=15.0)
            if ndvi_values is not None and len(ndvi_values) == len(gdf):
                # Log NDVI statistics before conversion
                valid_ndvi = ndvi_values[~np.isnan(ndvi_values)]

                # Check if we have any valid NDVI values
                if len(valid_ndvi) > 0:
                    logging.info(f"Sampled NDVI with 15m buffer: min={valid_ndvi.min():.3f}, max={valid_ndvi.max():.3f}, mean={valid_ndvi.mean():.3f}, median={np.median(valid_ndvi):.3f}")
                    gdf["sensor_canopy_pct"] = ndvi_to_canopy_pct(ndvi_values)
                    use_real_data = True
                    logging.info(f"Canopy coverage (NDVI→%): mean={gdf['sensor_canopy_pct'].mean():.1%}, max={gdf['sensor_canopy_pct'].max():.1%}")
                else:
                    # All values are NaN - no coverage for this area
                    logging.warning(f"NDVI coverage missing for this area (all NaN values); filling with defaults")
                    gdf["sensor_canopy_pct"] = 0.3

        # Try DEM data (no buffer needed for elevation)
        dem_url = get_raster_url_from_vultr('dem', bounds, city=city)
        if dem_url:
            # Use center sampling only for DEM (elevation doesn't need buffer)
            dem_values = sample_raster_at_points(dem_url, gdf_wgs84, buffer_meters=0.0)
            if dem_values is not None and len(dem_values) == len(gdf):
                # Check if we have any valid DEM values
                valid_dem = dem_values[~np.isnan(dem_values)]
                if len(valid_dem) > 0:
                    gdf["terrain_complexity"] = calculate_terrain_complexity(dem_values, gdf_wgs84)
                    gdf["topographic_position"] = calculate_topographic_position(dem_values)
                    use_real_data = True
                    logging.info(f"Extracted terrain features from DEM")
                else:
                    # All DEM values are NaN - no coverage
                    logging.warning(f"DEM coverage missing for this area (all NaN values); filling with defaults")
                    gdf["terrain_complexity"] = 0.5
                    gdf["topographic_position"] = 0.5

        # Fallback to defaults if real data unavailable
        if not use_real_data:
            logging.warning("Using default environmental values (Vultr storage not configured or data unavailable)")
            gdf["sensor_canopy_pct"] = 0.3
            gdf["terrain_complexity"] = 0.5
            gdf["topographic_position"] = 0.5

        return gdf

    except Exception as e:
        # Graceful degradation: use defaults on error
        logging.error(f"Environmental feature extraction failed: {e}. Using defaults.", exc_info=True)
        gdf = gdf.copy()
        gdf["sensor_canopy_pct"] = 0.3
        gdf["terrain_complexity"] = 0.5
        gdf["topographic_position"] = 0.5
        return gdf


if __name__ == "__main__":
    # Quick smoke test
    import geopandas as gpd
    from shapely.geometry import LineString

    test_gdf = gpd.GeoDataFrame({
        'geometry': [LineString([(0, 0), (1, 1)])],
        'highway': ['primary']
    })

    result = compute_environmental_features(test_gdf)
    print("Environmental features added:")
    print(result[['sensor_canopy_pct', 'terrain_complexity', 'topographic_position']])
