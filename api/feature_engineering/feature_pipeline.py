#!/usr/bin/env python3
"""
feature_pipeline.py

Unified feature extraction pipeline for pedestrian volume prediction.
Combines land use, centrality, highway, and temporal features into a single workflow.
Follows CLAUDE.md guidelines for production-ready, modular, and type-safe code.
"""
import logging
import os
import time
from datetime import datetime
from functools import lru_cache
from typing import Optional, Dict, Any, Tuple, Union, List
import pandas as pd
import geopandas as gpd
import osmnx as ox
import networkx as nx

# Configure OSMnx to be less conservative about Overpass API limits
# Default is too cautious and subdivides even small areas into 25+ pieces
# Increase this to allow larger single queries before subdivision
ox.settings.max_query_area_size = 50000 * 50000  # 50km x 50km = reasonable max

# Import loading animation control from app.py
try:
    import sys
    import os
    # Add the parent directory to the path to import from app.py
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import clear_loading_animation
except ImportError:
    # Fallback if import fails
    def clear_loading_animation():
        pass

def log_with_clear(message: str):
    """Log a message and clear loading animation if active."""
    clear_loading_animation()
    logging.info(message)

from .landuse_features import (
    get_landuse_polygons,
    compute_landuse_edges,
    LandUseError
)
from .centrality_features import (
    compute_centrality,
    CentralityError
)
from .highway_features import (
    compute_highway,
    HighwayError
)
from .time_features import compute_time_features, get_time_of_day
from .environmental_features import (
    compute_environmental_features,
    EnvironmentalError
)
from .weather_features import (
    compute_weather_features,
    WeatherError
)
from .disk_cache import get_disk_cache

# Import city name resolver for per-city optimization
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from city_name_resolver import CityNameResolver
    city_resolver = CityNameResolver()
except ImportError:
    city_resolver = None
    logging.warning("CityNameResolver not available - city-specific optimizations disabled")

# Configuration
class PipelineConfig:
    """Configuration constants for the feature extraction pipeline."""

    # STATIC feature columns (extracted once, cached, time-independent)
    STATIC_FEATURE_COLUMNS = [
        # NETWORK (4)
        "betweenness",            # Betweenness centrality (0-1)
        "closeness",              # Closeness centrality (0-1)
        "land_use",               # Categorical: residential/retail/commercial/other
        "highway",                # Categorical: primary/secondary/residential/etc

        # ENVIRONMENTAL (3)
        "sensor_canopy_pct",      # Tree canopy coverage (0-1)
        "terrain_complexity",     # Terrain complexity index (0-1)
        "topographic_position",   # Topographic position index (0-1)
    ]

    # PRODUCTION MODEL feature columns in expected order (15 features)
    # cb_model_3city_with_weather.cbm expects these exact features in this order
    FEATURE_COLUMNS = [
        # TEMPORAL (5)
        "Hour",                    # Hour of day (0-23)
        "Month",                   # Month (1-12)
        "DayOfWeek",              # Day of week (0-6, Monday=0)
        "is_weekend",             # Boolean weekend flag (0/1)
        "time_of_day",            # Categorical: morning/afternoon/evening/night

        # NETWORK (4)
        "betweenness",            # Betweenness centrality (0-1)
        "closeness",              # Closeness centrality (0-1)
        "land_use",               # Categorical: residential/retail/commercial/other
        "highway",                # Categorical: primary/secondary/residential/etc

        # ENVIRONMENTAL (3)
        "sensor_canopy_pct",      # Tree canopy coverage (0-1)
        "terrain_complexity",     # Terrain complexity index (0-1)
        "topographic_position",   # Topographic position index (0-1)

        # WEATHER (3)
        "temperature",            # Temperature in Celsius
        "precipitation",          # Precipitation in mm
        "wind_speed",             # Wind speed in km/h
    ]

    # Categorical features for model processing (must match production model training)
    CATEGORICAL_COLUMNS = ["Month", "DayOfWeek", "is_weekend", "time_of_day", "land_use", "highway"]
    
    # Network processing settings
    NETWORK_TYPE = "walk"
    CRS_METRIC = 3857  # EPSG:3857 for accurate length calculations
    
    # Performance settings
    MAX_NODES_FOR_EXACT_CENTRALITY = 1000
    CENTRALITY_SAMPLE_SIZE = 500

class PipelineError(Exception):
    """Exception for feature pipeline errors."""
    def __init__(self, message: str, code: int = 500, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON responses."""
        return {
            "error": self.message,
            "code": self.code,
            "details": self.details
        }

def validate_pipeline_inputs(place: Optional[str] = None, 
                           bbox: Optional[Tuple[float, float, float, float]] = None,
                           timestamp: Optional[Union[str, datetime]] = None) -> None:
    """Validate pipeline input parameters.
    
    Args:
        place: Place name for OSM query
        bbox: Bounding box coordinates  
        timestamp: Timestamp for temporal features
        
    Raises:
        PipelineError: If inputs are invalid
    """
    if place is None and bbox is None:
        raise PipelineError(
            "Either 'place' or 'bbox' must be provided",
            code=400,
            details={"place": place, "bbox": bbox}
        )
    
    if place and not isinstance(place, str):
        raise PipelineError("Place must be a string", code=400)
    
    if bbox and (not isinstance(bbox, (list, tuple)) or len(bbox) != 4):
        raise PipelineError("Bbox must be a tuple/list of 4 coordinates", code=400)

def extract_street_network(place: Optional[str] = None, 
                          bbox: Optional[Tuple[float, float, float, float]] = None) -> Tuple[nx.Graph, gpd.GeoDataFrame]:
    """Extract street network graph and edges for the specified location.
    
    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox: Bounding box as (west, south, east, north) in EPSG:4326
        
    Returns:
        tuple: (NetworkX graph, edges GeoDataFrame)
        
    Raises:
        PipelineError: If network extraction fails
    """
    try:
        log_with_clear(f"Extracting street network for {place or 'bbox'}")

        # Download street network
        if place:
            G = ox.graph_from_place(place, network_type=PipelineConfig.NETWORK_TYPE)
        else:
            # OSMnx 2.0+ expects bbox as (west, south, east, north) tuple
            bbox_osmnx = (bbox[0], bbox[1], bbox[2], bbox[3])  # (west, south, east, north)

            logging.info(f"[OSMNX] Calling ox.graph_from_bbox with:")
            logging.info(f"[OSMNX]   bbox: {bbox_osmnx}")
            logging.info(f"[OSMNX]   network_type: {PipelineConfig.NETWORK_TYPE}")
            logging.info(f"[OSMNX]   ox.settings.max_query_area_size: {ox.settings.max_query_area_size} m²")

            # Calculate expected area to compare with OSMnx's calculation
            width_deg = bbox_osmnx[2] - bbox_osmnx[0]
            height_deg = bbox_osmnx[3] - bbox_osmnx[1]
            approx_area_m2 = (width_deg * 95000) * (height_deg * 111000)
            logging.info(f"[OSMNX]   Approx area: {approx_area_m2:.0f} m²")
            logging.info(f"[OSMNX]   Will subdivide: {approx_area_m2 > ox.settings.max_query_area_size}")
            logging.info(f"[OSMNX] Starting download... (this may take time for large areas)")

            import time
            start_time = time.time()

            G = ox.graph_from_bbox(
                bbox=bbox_osmnx,
                network_type=PipelineConfig.NETWORK_TYPE
            )

            elapsed = time.time() - start_time
            logging.info(f"[OSMNX] Download completed in {elapsed:.1f} seconds")
            logging.info(f"[OSMNX] Downloaded {len(G.nodes)} nodes, {len(G.edges)} edges")
        
        # Project to metric CRS for accurate length calculation
        G_proj = ox.project_graph(G, to_crs=f"EPSG:{PipelineConfig.CRS_METRIC}")
        
        # Convert to GeoDataFrame
        edges_gdf = ox.graph_to_gdfs(G_proj, nodes=False, edges=True)
        edges_gdf = edges_gdf.reset_index()
        
        # Add length column in meters
        edges_gdf['length'] = edges_gdf.geometry.length
        
        # Convert back to EPSG:4326 for consistency with other modules
        edges_gdf = edges_gdf.to_crs("EPSG:4326")
        G = ox.project_graph(G_proj, to_crs="EPSG:4326")
        
        log_with_clear(f"Extracted network: {len(G.nodes)} nodes, {len(edges_gdf)} edges")
        return G, edges_gdf
        
    except Exception as e:
        raise PipelineError(
            f"Failed to extract street network: {str(e)}",
            code=500,
            details={"place": place, "bbox": bbox}
        )

def extract_static_features(edges_gdf: gpd.GeoDataFrame,
                           graph: nx.Graph,
                           place: Optional[str] = None,
                           bbox: Optional[Tuple[float, float, float, float]] = None) -> gpd.GeoDataFrame:
    """Extract STATIC features only (no temporal, no weather).

    This extracts features that don't change with time:
    - Land use
    - Centrality
    - Highway types
    - Environmental (NDVI/DEM)

    Args:
        edges_gdf: Street edges GeoDataFrame
        graph: NetworkX graph for centrality computation
        place: Place name for land use data
        bbox: Bounding box for land use data

    Returns:
        GeoDataFrame: Edges with static features only

    Raises:
        PipelineError: If feature extraction fails
    """
    try:
        result_gdf = edges_gdf.copy()
        extraction_times = {}

        # Try to resolve place to city name for per-city optimizations
        city = None
        if place and city_resolver:
            try:
                city = city_resolver.resolve(place)
                if city:
                    logging.info(f"Resolved '{place}' to city '{city}' for per-city optimizations")
            except Exception as e:
                logging.warning(f"Failed to resolve city name from '{place}': {e}")

        # 1. Extract land use features
        start_time = time.time()
        try:
            result_gdf = compute_landuse_edges(
                result_gdf,
                place=place,
                bbox=bbox,
                city=city
            )
            extraction_times['landuse'] = time.time() - start_time
            log_with_clear(f"Land use extraction completed in {extraction_times['landuse']:.2f}s")
        except LandUseError as e:
            logging.error(f"Land use extraction failed: {e.message}")
            result_gdf['land_use'] = 'other'
            extraction_times['landuse'] = time.time() - start_time

        # 2. Extract centrality features
        start_time = time.time()
        try:
            sample_size = None
            if len(graph.nodes) > PipelineConfig.MAX_NODES_FOR_EXACT_CENTRALITY:
                sample_size = PipelineConfig.CENTRALITY_SAMPLE_SIZE

            result_gdf = compute_centrality(graph, result_gdf, sample_size=sample_size)
            extraction_times['centrality'] = time.time() - start_time
            log_with_clear(f"Centrality extraction completed in {extraction_times['centrality']:.2f}s")
        except CentralityError as e:
            logging.error(f"Centrality extraction failed: {e.message}")
            result_gdf['betweenness'] = 0.0
            result_gdf['closeness'] = 0.0
            extraction_times['centrality'] = time.time() - start_time

        # 3. Extract highway features
        start_time = time.time()
        try:
            result_gdf = compute_highway(result_gdf)
            extraction_times['highway'] = time.time() - start_time
            log_with_clear(f"Highway extraction completed in {extraction_times['highway']:.2f}s")
        except HighwayError as e:
            logging.error(f"Highway extraction failed: {e.message}")
            result_gdf['highway'] = 'unclassified'
            extraction_times['highway'] = time.time() - start_time

        # 4. Extract environmental features (NDVI, DEM)
        start_time = time.time()
        try:
            result_gdf = compute_environmental_features(result_gdf, city=city)
            extraction_times['environmental'] = time.time() - start_time
            log_with_clear(f"Environmental extraction completed in {extraction_times['environmental']:.2f}s")
        except EnvironmentalError as e:
            logging.error(f"Environmental extraction failed: {e.message}")
            result_gdf['sensor_canopy_pct'] = 0.3
            result_gdf['terrain_complexity'] = 0.5
            result_gdf['topographic_position'] = 0.5
            extraction_times['environmental'] = time.time() - start_time

        # NO TEMPORAL OR WEATHER FEATURES - those are added by endpoints separately

        total_time = sum(extraction_times.values())
        log_with_clear(f"Static feature extraction completed in {total_time:.2f}s")
        log_with_clear(f"Extraction breakdown: {extraction_times}")

        return result_gdf

    except Exception as e:
        raise PipelineError(
            f"Static feature extraction failed: {str(e)}",
            code=500,
            details={"n_edges": len(edges_gdf)}
        )

def extract_all_features(edges_gdf: gpd.GeoDataFrame,
                        graph: nx.Graph,
                        place: Optional[str] = None,
                        bbox: Optional[Tuple[float, float, float, float]] = None,
                        timestamp: Optional[Union[str, datetime]] = None) -> gpd.GeoDataFrame:
    """Extract all features for the edges using the modular feature functions.

    Args:
        edges_gdf: Street edges GeoDataFrame
        graph: NetworkX graph for centrality computation
        place: Place name for land use data
        bbox: Bounding box for land use data
        timestamp: Timestamp for temporal features

    Returns:
        GeoDataFrame: Edges with all features extracted

    Raises:
        PipelineError: If feature extraction fails
    """
    try:
        result_gdf = edges_gdf.copy()
        extraction_times = {}

        # Try to resolve place to city name for per-city optimizations
        city = None
        if place and city_resolver:
            try:
                city = city_resolver.resolve(place)
                if city:
                    logging.info(f"Resolved '{place}' to city '{city}' for per-city optimizations")
            except Exception as e:
                logging.warning(f"Failed to resolve city name from '{place}': {e}")

        # 1. Extract land use features
        start_time = time.time()
        try:
            result_gdf = compute_landuse_edges(
                result_gdf,
                place=place,
                bbox=bbox,
                city=city
            )
            extraction_times['landuse'] = time.time() - start_time
            log_with_clear(f"Land use extraction completed in {extraction_times['landuse']:.2f}s")
        except LandUseError as e:
            logging.error(f"Land use extraction failed: {e.message}")
            # Graceful degradation: assign default land use
            result_gdf['land_use'] = 'other'
            extraction_times['landuse'] = time.time() - start_time
        
        # 2. Extract centrality features
        start_time = time.time()
        try:
            # Use sampling for large graphs
            sample_size = None
            if len(graph.nodes) > PipelineConfig.MAX_NODES_FOR_EXACT_CENTRALITY:
                sample_size = PipelineConfig.CENTRALITY_SAMPLE_SIZE
            
            result_gdf = compute_centrality(graph, result_gdf, sample_size=sample_size)
            extraction_times['centrality'] = time.time() - start_time
            log_with_clear(f"Centrality extraction completed in {extraction_times['centrality']:.2f}s")
        except CentralityError as e:
            logging.error(f"Centrality extraction failed: {e.message}")
            # Graceful degradation: assign default centrality
            result_gdf['betweenness'] = 0.0
            result_gdf['closeness'] = 0.0
            extraction_times['centrality'] = time.time() - start_time
        
        # 3. Extract highway features  
        start_time = time.time()
        try:
            result_gdf = compute_highway(result_gdf)
            extraction_times['highway'] = time.time() - start_time
            log_with_clear(f"Highway extraction completed in {extraction_times['highway']:.2f}s")
        except HighwayError as e:
            logging.error(f"Highway extraction failed: {e.message}")
            # Graceful degradation: assign default highway type
            result_gdf['highway'] = 'unclassified'
            extraction_times['highway'] = time.time() - start_time
        
        # 4. Extract temporal features
        start_time = time.time()
        result_gdf = compute_time_features(result_gdf, timestamp=timestamp)
        extraction_times['temporal'] = time.time() - start_time
        log_with_clear(f"Temporal extraction completed in {extraction_times['temporal']:.2f}s")

        # 5. Extract environmental features
        start_time = time.time()
        try:
            result_gdf = compute_environmental_features(result_gdf, city=city)
            extraction_times['environmental'] = time.time() - start_time
            log_with_clear(f"Environmental extraction completed in {extraction_times['environmental']:.2f}s")
        except EnvironmentalError as e:
            logging.error(f"Environmental extraction failed: {e.message}")
            # Graceful degradation: assign default environmental values
            result_gdf['sensor_canopy_pct'] = 0.3
            result_gdf['terrain_complexity'] = 0.5
            result_gdf['topographic_position'] = 0.5
            extraction_times['environmental'] = time.time() - start_time

        # 6. Extract weather features
        start_time = time.time()
        try:
            # Extract time_of_day from timestamp for weather averaging
            time_of_day_value = None
            if timestamp:
                ts = pd.to_datetime(timestamp) if isinstance(timestamp, str) else timestamp
                time_of_day_value = get_time_of_day(ts.hour)

            result_gdf = compute_weather_features(
                result_gdf,
                timestamp=timestamp,
                time_of_day=time_of_day_value
            )
            extraction_times['weather'] = time.time() - start_time
            log_with_clear(f"Weather extraction completed in {extraction_times['weather']:.2f}s")
        except WeatherError as e:
            logging.error(f"Weather extraction failed: {e.message}")
            # Graceful degradation: assign default weather values
            result_gdf['temperature'] = 20.0
            result_gdf['precipitation'] = 0.0
            result_gdf['wind_speed'] = 10.0
            extraction_times['weather'] = time.time() - start_time

        # Log total extraction time
        total_time = sum(extraction_times.values())
        log_with_clear(f"Total feature extraction completed in {total_time:.2f}s")
        log_with_clear(f"Extraction breakdown: {extraction_times}")

        return result_gdf
        
    except Exception as e:
        raise PipelineError(
            f"Feature extraction failed: {str(e)}",
            code=500,
            details={"n_edges": len(edges_gdf)}
        )

def validate_features(features_gdf: gpd.GeoDataFrame,
                     required_columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """Validate extracted features and return validation summary.

    Args:
        features_gdf: GeoDataFrame with extracted features
        required_columns: List of required column names. If None, uses all FEATURE_COLUMNS

    Returns:
        dict: Validation summary with statistics

    Raises:
        PipelineError: If critical validation fails
    """
    # Default to all features if not specified
    if required_columns is None:
        required_columns = PipelineConfig.FEATURE_COLUMNS

    validation_summary = {
        "n_edges": len(features_gdf),
        "missing_features": {},
        "feature_stats": {},
        "warnings": []
    }

    # Check for missing required columns
    missing_columns = [col for col in required_columns if col not in features_gdf.columns]
    if missing_columns:
        raise PipelineError(
            f"Missing required feature columns: {missing_columns}",
            code=500,
            details={"missing_columns": missing_columns}
        )
    
    # Validate each feature
    for col in required_columns:
        if col in features_gdf.columns:
            series = features_gdf[col]
            
            # Count missing values
            n_missing = series.isna().sum()
            validation_summary["missing_features"][col] = n_missing
            
            if n_missing > 0:
                validation_summary["warnings"].append(f"{col}: {n_missing} missing values")
            
            # Collect statistics
            if col in ["length", "betweenness", "closeness", "Hour"]:
                validation_summary["feature_stats"][col] = {
                    "min": float(series.min()) if not series.empty else None,
                    "max": float(series.max()) if not series.empty else None,
                    "mean": float(series.mean()) if not series.empty else None
                }
            elif col in PipelineConfig.CATEGORICAL_COLUMNS:
                validation_summary["feature_stats"][col] = {
                    "unique_values": series.value_counts().to_dict()
                }
    
    # Validate data ranges
    if 'Hour' in features_gdf.columns:
        hour_range = features_gdf['Hour'].dropna()
        if not hour_range.empty and (hour_range < 0).any() or (hour_range > 23).any():
            validation_summary["warnings"].append("Hour values outside valid range [0-23]")
    
    if 'length' in features_gdf.columns:
        length_values = features_gdf['length'].dropna()
        if not length_values.empty and (length_values <= 0).any():
            validation_summary["warnings"].append("Non-positive length values found")
    
    log_with_clear(f"Feature validation completed: {len(validation_summary['warnings'])} warnings")
    
    return validation_summary

def run_static_feature_pipeline(place: Optional[str] = None,
                                bbox: Optional[Tuple[float, float, float, float]] = None) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """Run feature extraction for STATIC features only (no timestamp-dependent features).

    This extracts only the features that don't change with time:
    - Street network structure
    - Land use
    - Centrality
    - Highway types
    - Environmental (NDVI, DEM)

    Temporal and weather features are NOT included (add them separately).

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox: Bounding box as (minx, miny, maxx, maxy) in EPSG:4326

    Returns:
        tuple: (features_gdf, pipeline_metadata)
            - features_gdf: GeoDataFrame with static features only
            - pipeline_metadata: Dict with processing statistics

    Raises:
        PipelineError: If any step in the pipeline fails
    """
    pipeline_start = time.time()

    try:
        # 1. Validate inputs (no timestamp needed)
        validate_pipeline_inputs(place, bbox, timestamp=None)
        log_with_clear(f"Starting STATIC feature pipeline for {place or 'bbox'}")

        # 2. Extract street network
        graph, edges_gdf = extract_street_network(place, bbox)

        # 3. Extract STATIC features only (no temporal, no weather)
        features_gdf = extract_static_features(
            edges_gdf, graph, place=place, bbox=bbox
        )

        # 4. Validate results (only static features, not temporal/weather)
        validation_summary = validate_features(features_gdf, required_columns=PipelineConfig.STATIC_FEATURE_COLUMNS)

        # 5. Compile metadata
        pipeline_metadata = {
            "processing_time": time.time() - pipeline_start,
            "location": {"place": place, "bbox": bbox},
            "network_stats": {
                "n_nodes": len(graph.nodes),
                "n_edges": len(features_gdf)
            },
            "validation": validation_summary,
            "feature_type": "static_only"
        }

        log_with_clear(f"Static pipeline completed in {pipeline_metadata['processing_time']:.2f}s")

        return features_gdf, pipeline_metadata

    except Exception as e:
        if isinstance(e, PipelineError):
            raise
        else:
            raise PipelineError(
                f"Static pipeline execution failed: {str(e)}",
                code=500,
                details={"place": place, "bbox": bbox}
            )

def run_feature_pipeline(place: Optional[str] = None,
                        bbox: Optional[Tuple[float, float, float, float]] = None,
                        timestamp: Optional[Union[str, datetime]] = None) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """Run the complete feature extraction pipeline (LEGACY - use run_static_feature_pipeline instead).

    This is kept for backward compatibility but should be replaced with:
    1. run_static_feature_pipeline() for cacheable features
    2. Manual temporal/weather addition for dynamic features

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox: Bounding box as (minx, miny, maxx, maxy) in EPSG:4326
        timestamp: Timestamp for temporal features (ISO format or datetime)

    Returns:
        tuple: (features_gdf, pipeline_metadata)
            - features_gdf: GeoDataFrame with all features extracted
            - pipeline_metadata: Dict with processing statistics and validation info

    Raises:
        PipelineError: If any step in the pipeline fails
    """
    pipeline_start = time.time()

    try:
        # 1. Validate inputs
        validate_pipeline_inputs(place, bbox, timestamp)
        log_with_clear(f"Starting feature pipeline for {place or 'bbox'}")

        # 2. Extract street network
        graph, edges_gdf = extract_street_network(place, bbox)

        # 3. Extract all features
        features_gdf = extract_all_features(
            edges_gdf, graph, place=place, bbox=bbox, timestamp=timestamp
        )

        # 4. Validate results
        validation_summary = validate_features(features_gdf)

        # 5. Compile metadata
        pipeline_metadata = {
            "processing_time": time.time() - pipeline_start,
            "location": {"place": place, "bbox": bbox},
            "timestamp": str(timestamp) if timestamp else None,
            "network_stats": {
                "n_nodes": len(graph.nodes),
                "n_edges": len(features_gdf)
            },
            "validation": validation_summary,
            "feature_columns": PipelineConfig.FEATURE_COLUMNS,
            "categorical_columns": PipelineConfig.CATEGORICAL_COLUMNS
        }

        log_with_clear(f"Pipeline completed successfully in {pipeline_metadata['processing_time']:.2f}s")

        return features_gdf, pipeline_metadata

    except Exception as e:
        if isinstance(e, PipelineError):
            raise
        else:
            raise PipelineError(
                f"Pipeline execution failed: {str(e)}",
                code=500,
                details={"place": place, "bbox": bbox}
            )

def prepare_model_features(features_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Prepare features for model prediction by selecting and ordering columns.

    Args:
        features_gdf: GeoDataFrame with extracted features

    Returns:
        DataFrame: Features ready for model input with correct column order

    Raises:
        PipelineError: If required features are missing
    """
    try:
        # Select only the required feature columns in correct order
        model_features = features_gdf[PipelineConfig.FEATURE_COLUMNS].copy()

        # Validate no missing values in critical features
        critical_nulls = model_features.isnull().sum()
        if critical_nulls.any():
            logging.warning(f"Found null values in features: {critical_nulls[critical_nulls > 0].to_dict()}")

        # Fill any remaining nulls with defaults
        defaults = {
            # Temporal features
            'Hour': 12,  # Default to noon
            'Month': 6,  # Default to June
            'DayOfWeek': 2,  # Default to Wednesday
            'is_weekend': 0,
            'time_of_day': 'afternoon',
            # Network features
            'betweenness': 0.0,
            'closeness': 0.0,
            'land_use': 'other',
            'highway': 'unclassified',
            # Environmental features
            'sensor_canopy_pct': 0.3,
            'terrain_complexity': 0.5,
            'topographic_position': 0.5,
            # Weather features
            'temperature': 20.0,
            'precipitation': 0.0,
            'wind_speed': 10.0
        }

        for col, default_val in defaults.items():
            if col in model_features.columns:
                model_features[col] = model_features[col].fillna(default_val)

        log_with_clear(f"Prepared {len(model_features)} feature vectors for model input")

        return model_features

    except Exception as e:
        raise PipelineError(
            f"Failed to prepare model features: {str(e)}",
            code=500,
            details={"available_columns": list(features_gdf.columns)}
        )


# =========================
# Cached Pipeline Wrapper with Disk Cache
# =========================

# DISK CACHE: Works across multiple Gunicorn workers by storing cache on disk.
# This solves the multi-worker problem where each process has its own memory space.

def _prepare_gdf_for_cache(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Prepare GeoDataFrame for Parquet serialization by normalizing problematic columns.

    Issues with OSMnx data:
    - osmid: can be int, list of ints, or tuple
    - reversed: can be bool or list of bools
    - Other columns may also have mixed types

    Parquet doesn't handle mixed types well, so we convert to consistent string format.

    Args:
        gdf: GeoDataFrame to prepare

    Returns:
        Cleaned copy of GeoDataFrame safe for Parquet serialization
    """
    gdf_clean = gdf.copy()

    # Normalize osmid column if present
    if 'osmid' in gdf_clean.columns:
        def serialize_osmid(v):
            """Convert osmid to string format, handling lists/tuples."""
            if isinstance(v, (list, tuple)):
                return ",".join(map(str, v)) if v else None
            return str(v) if v is not None else None

        gdf_clean['osmid'] = gdf_clean['osmid'].apply(serialize_osmid)
        logging.debug(f"[CACHE PREP] Normalized osmid column")

    # Normalize reversed column if present
    if 'reversed' in gdf_clean.columns:
        def serialize_reversed(v):
            """Convert reversed to string format, handling lists."""
            if isinstance(v, (list, tuple)):
                return ",".join(map(str, v)) if v else None
            return str(v) if v is not None else None

        gdf_clean['reversed'] = gdf_clean['reversed'].apply(serialize_reversed)
        logging.debug(f"[CACHE PREP] Normalized reversed column")

    # Normalize any other list/tuple columns
    for col in gdf_clean.columns:
        if col not in ['geometry', 'osmid', 'reversed']:
            # Check if column has any list/tuple values
            sample = gdf_clean[col].iloc[0] if len(gdf_clean) > 0 else None
            if isinstance(sample, (list, tuple)):
                def serialize_list(v):
                    if isinstance(v, (list, tuple)):
                        return ",".join(map(str, v)) if v else None
                    return str(v) if v is not None else None

                gdf_clean[col] = gdf_clean[col].apply(serialize_list)
                logging.debug(f"[CACHE PREP] Normalized {col} column")

    return gdf_clean


def run_static_feature_pipeline_cached(
    place: Optional[str],
    bbox_key: Optional[Tuple[float, float, float, float]]
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    Disk-cached wrapper for run_static_feature_pipeline.

    Cache key: (place, bbox) only - NO timestamp!
    This allows perfect cache reuse between /predict-multi and /predict-gpkg
    since static features don't change with time.

    Uses disk-based cache that works across multiple Gunicorn workers.

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox_key: Bounding box as hashable tuple (west, south, east, north) or None

    Returns:
        tuple: (features_gdf, pipeline_metadata) with STATIC features only

    Note:
        Returns features WITHOUT temporal/weather. Endpoints must add those separately.
    """
    # Try disk cache first
    disk_cache = get_disk_cache()
    cached_result = disk_cache.get(place, bbox_key)

    if cached_result is not None:
        # Cache hit - return copy to avoid modification
        return cached_result[0].copy(), cached_result[1]

    # Cache miss - compute features
    features_gdf, metadata = run_static_feature_pipeline(
        place=place,
        bbox=bbox_key
    )

    # Clean GeoDataFrame for Parquet serialization (normalize osmid)
    gdf_for_cache = _prepare_gdf_for_cache(features_gdf)

    # Store in disk cache
    disk_cache.set(place, bbox_key, gdf_for_cache, metadata)

    return features_gdf, metadata

# LEGACY: Old cached function with timestamp - kept for backward compatibility
@lru_cache(maxsize=64)
def run_feature_pipeline_cached(
    place: Optional[str],
    bbox_key: Optional[Tuple[float, float, float, float]],
    timestamp_str: Optional[str]
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    LEGACY: Cached wrapper for run_feature_pipeline (includes timestamp).

    USE run_static_feature_pipeline_cached instead for better cache hits!

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox_key: Bounding box as hashable tuple (west, south, east, north) or None
        timestamp_str: ISO timestamp string or None

    Returns:
        tuple: (features_gdf, pipeline_metadata) same as run_feature_pipeline
    """
    # Convert timestamp string back to datetime if provided
    timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None

    # Call the original pipeline
    return run_feature_pipeline(
        place=place,
        bbox=bbox_key,
        timestamp=timestamp
    )


def run_static_feature_pipeline_cached_normalized(
    place: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    Normalized wrapper for cached STATIC feature pipeline with disk cache.

    This returns features WITHOUT temporal/weather. Endpoints must add those separately.

    Cache key: (place, bbox) only - NO timestamp!
    Perfect cache reuse between endpoints for the same location.

    Uses disk-based cache that works across multiple Gunicorn workers.

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox: Bounding box as tuple/list (west, south, east, north) or None

    Returns:
        tuple: (features_gdf COPY, pipeline_metadata) with STATIC features only

    Example:
        # Both endpoints can use the same cached static features:
        static_gdf, metadata = run_static_feature_pipeline_cached_normalized(
            place="Tel Aviv",
            bbox=None
        )
        # Then each endpoint adds its own temporal/weather features
    """
    # Normalize bbox to hashable tuple
    bbox_key = tuple(bbox) if bbox is not None else None

    # DEBUG: Log cache key and process info BEFORE calling cached function
    pid = os.getpid()
    logging.info(f"[DISK CACHE DEBUG] PID={pid} | Checking cache: place={place}, bbox_key={bbox_key}")

    # Call cached wrapper with hashable arguments (NO TIMESTAMP!)
    features_gdf, metadata = run_static_feature_pipeline_cached(
        place=place,
        bbox_key=bbox_key
    )

    # CRITICAL: Return a COPY of the GeoDataFrame
    # Each endpoint modifies temporal features (Hour, is_weekend, etc.)
    # If we return the same object, modifications corrupt the cache
    return features_gdf.copy(), metadata

# LEGACY: Old normalized function with timestamp
def run_feature_pipeline_cached_normalized(
    place: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    timestamp: Optional[Union[str, datetime]] = None
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    LEGACY: Normalized wrapper for cached pipeline with timestamp.

    USE run_static_feature_pipeline_cached_normalized instead for better cache hits!

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox: Bounding box as tuple/list (west, south, east, north) or None
        timestamp: ISO timestamp string or datetime object or None

    Returns:
        tuple: (features_gdf COPY, pipeline_metadata) from cached pipeline
    """
    # Normalize bbox to hashable tuple
    bbox_key = tuple(bbox) if bbox is not None else None

    # Normalize timestamp to ISO string
    if timestamp is None:
        timestamp_str = None
    elif isinstance(timestamp, datetime):
        timestamp_str = timestamp.isoformat()
    else:
        # Already a string
        timestamp_str = str(timestamp)

    # DEBUG: Log cache key and process info BEFORE calling cached function
    pid = os.getpid()
    logging.info(f"[LEGACY CACHE DEBUG] PID={pid} | Cache key: place={place}, bbox_key={bbox_key}, timestamp_str={timestamp_str}")

    # Call cached wrapper with hashable arguments
    features_gdf, metadata = run_feature_pipeline_cached(
        place=place,
        bbox_key=bbox_key,
        timestamp_str=timestamp_str
    )

    # DEBUG: Log cache statistics AFTER calling cached function
    cache_info = run_feature_pipeline_cached.cache_info()
    logging.info(f"[LEGACY CACHE DEBUG] PID={pid} | Cache stats: hits={cache_info.hits}, misses={cache_info.misses}, size={cache_info.currsize}/{cache_info.maxsize}")

    # CRITICAL: Return a COPY of the GeoDataFrame
    # Each endpoint modifies temporal features (Hour, is_weekend, etc.)
    # If we return the same object, modifications corrupt the cache
    return features_gdf.copy(), metadata

def example_usage():
    """Example of how to use the feature pipeline."""
    try:
        # Run pipeline for Monaco
        features_gdf, metadata = run_feature_pipeline(
            place="Monaco",
            timestamp="2024-01-15T14:30:00"
        )
        
        print(f"Pipeline completed for {metadata['network_stats']['n_edges']} edges")
        print(f"Processing time: {metadata['processing_time']:.2f}s")
        print(f"Features: {list(features_gdf.columns)}")
        
        # Prepare for model
        model_features = prepare_model_features(features_gdf)
        print(f"Model features ready: {model_features.shape}")
        
    except Exception as e:
        print(f"Pipeline failed: {e}")

if __name__ == "__main__":
    example_usage()