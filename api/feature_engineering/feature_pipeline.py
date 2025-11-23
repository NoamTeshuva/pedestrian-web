#!/usr/bin/env python3
"""
feature_pipeline.py

Unified feature extraction pipeline for pedestrian volume prediction.
Combines land use, centrality, highway, and temporal features into a single workflow.
Follows CLAUDE.md guidelines for production-ready, modular, and type-safe code.
"""
import logging
import time
from datetime import datetime
from functools import lru_cache
from typing import Optional, Dict, Any, Tuple, Union, List
import pandas as pd
import geopandas as gpd
import osmnx as ox
import networkx as nx

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
            G = ox.graph_from_bbox(
                bbox=bbox_osmnx,
                network_type=PipelineConfig.NETWORK_TYPE
            )
        
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

def validate_features(features_gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
    """Validate extracted features and return validation summary.
    
    Args:
        features_gdf: GeoDataFrame with extracted features
        
    Returns:
        dict: Validation summary with statistics
        
    Raises:
        PipelineError: If critical validation fails
    """
    validation_summary = {
        "n_edges": len(features_gdf),
        "missing_features": {},
        "feature_stats": {},
        "warnings": []
    }
    
    # Check for missing required columns
    missing_columns = [col for col in PipelineConfig.FEATURE_COLUMNS if col not in features_gdf.columns]
    if missing_columns:
        raise PipelineError(
            f"Missing required feature columns: {missing_columns}",
            code=500,
            details={"missing_columns": missing_columns}
        )
    
    # Validate each feature
    for col in PipelineConfig.FEATURE_COLUMNS:
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

def run_feature_pipeline(place: Optional[str] = None,
                        bbox: Optional[Tuple[float, float, float, float]] = None,
                        timestamp: Optional[Union[str, datetime]] = None) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """Run the complete feature extraction pipeline.
    
    This is the main entry point that orchestrates all feature extraction steps:
    1. Input validation
    2. Street network extraction
    3. Feature extraction (land use, centrality, highway, temporal)
    4. Feature validation
    5. Return processed data ready for model prediction
    
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
# Cached Pipeline Wrapper
# =========================

@lru_cache(maxsize=64)
def run_feature_pipeline_cached(
    place: Optional[str],
    bbox_key: Optional[Tuple[float, float, float, float]],
    timestamp_str: Optional[str]
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    Cached wrapper for run_feature_pipeline.

    This wrapper enables caching of expensive feature extraction to avoid
    recomputing the same features when multiple endpoints (e.g., /predict-multi
    and /predict-gpkg) request features for the same place/bbox.

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox_key: Bounding box as hashable tuple (west, south, east, north) or None
        timestamp_str: ISO timestamp string or None

    Returns:
        tuple: (features_gdf, pipeline_metadata) same as run_feature_pipeline

    Note:
        All arguments must be hashable for LRU cache to work. GeoDataFrames and
        datetime objects are converted to/from hashable types by the normalized wrapper.
    """
    # Convert timestamp string back to datetime if provided
    timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None

    # Call the original pipeline
    return run_feature_pipeline(
        place=place,
        bbox=bbox_key,
        timestamp=timestamp
    )


def run_feature_pipeline_cached_normalized(
    place: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    timestamp: Optional[Union[str, datetime]] = None
) -> Tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    """
    Normalized wrapper for cached pipeline that handles type conversion.

    This function normalizes input types to hashable forms before calling the
    cached wrapper, making it easy to use from API endpoints.

    Args:
        place: Place name (e.g., "Monaco", "Tel Aviv")
        bbox: Bounding box as tuple/list (west, south, east, north) or None
        timestamp: ISO timestamp string or datetime object or None

    Returns:
        tuple: (features_gdf COPY, pipeline_metadata) from cached pipeline

    Example:
        # Both endpoints can use the same cached result:
        features_gdf, metadata = run_feature_pipeline_cached_normalized(
            place="Tel Aviv",
            bbox=None,
            timestamp=None
        )

    Note:
        Returns a COPY of the cached GeoDataFrame to prevent endpoints from
        modifying the cached object (which would corrupt subsequent calls).
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

    # Call cached wrapper with hashable arguments
    features_gdf, metadata = run_feature_pipeline_cached(
        place=place,
        bbox_key=bbox_key,
        timestamp_str=timestamp_str
    )

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