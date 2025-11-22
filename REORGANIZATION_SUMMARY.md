# Vultr Data Reorganization Summary

## Date: 2025-11-21

## What Was Done

### 1. Data Reorganization in Vultr

Reorganized all Israel city data into a unified structure:

**Old Structure:**
```
data/processed/israel/cities_landuse/{city}_landuse.gpkg
data/processed/israel/cities/{city}/{city}_ndvi.tif
data/processed/israel/cities/{city}/{city}_dem.tif
```

**New Structure:**
```
data/processed/israel/cities/{city}/
├── {city}_landuse.gpkg
├── {city}_ndvi.tif
└── {city}_dem.tif
```

**Results:**
- Successfully reorganized 277 landuse files
- Total files in new structure: 830 files
  - 277 landuse files (.gpkg)
  - 276 NDVI files (.tif)
  - 277 DEM files (.tif)

### 2. Code Updates

Updated two key API files to use the new structure:

#### `api/feature_engineering/environmental_features.py`

**Changes:**
- Added `city` parameter to `get_raster_url_from_vultr()` function
- Added `city` parameter to `compute_environmental_features()` function
- Now tries city-specific rasters first: `data/processed/israel/cities/{city}/{city}_ndvi.tif`
- Falls back to national rasters if city files not available
- Updated path format (removed "project/" prefix)

**Benefits:**
- Faster: Loads smaller city-specific files instead of large national rasters
- More efficient: Only downloads data needed for specific city
- Backwards compatible: Falls back to national rasters for non-Israeli cities

#### `api/feature_engineering/landuse_features.py`

**Changes:**
- Added `city` parameter to `get_landuse_polygons()` function
- Added `city` parameter to `compute_landuse_edges()` function
- Added `city` parameter to `_get_or_load_landuse_data()` function
- Now tries precomputed landuse files first: `data/processed/israel/cities/{city}/{city}_landuse.gpkg`
- Falls back to OSMnx download if precomputed files not available

**Benefits:**
- Much faster: Uses precomputed files instead of downloading from OSMnx
- More reliable: No dependency on OSMnx API availability
- Backwards compatible: Falls back to OSMnx for non-Israeli cities

### 3. How to Use

The API will now automatically use city-specific files when a `city` parameter is provided:

```python
# For environmental features
gdf = compute_environmental_features(edges_gdf, city="tel_aviv")

# For landuse features
edges_with_landuse = compute_landuse_edges(
    edges_gdf,
    place="Tel Aviv",
    city="tel_aviv"
)
```

The `city` parameter should match the file names in Vultr (e.g., "tel_aviv", "haifa", "jerusalem").

### 4. National Raster Fallback (Optional)

National-level processed NDVI data exists in Vultr but in zip format:
- `project/assets/browser_images/browser_images_8.zip` (40MB)
- `project/assets/browser_images/browser_images_9.zip` (40MB)

**Current Behavior:** When city-specific files aren't found, uses default values (fast, reasonable)

**Optional Enhancement:** Extract these zips and upload as TIF files for true national fallback:
1. Download and extract browser_images_8.zip and browser_images_9.zip
2. Combine/process into single `data/processed/israel/rasters/israel_ndvi.tif`
3. Upload to Vultr
4. Update code to use as fallback

**Note:** Downloading 40MB zips on every API call is not practical for production.

### 5. Next Steps

1. ✅ **Update app.py** to pass city parameter to feature engineering functions
2. **Test the API** to ensure it loads from the new structure correctly
3. **Delete old directory** (optional): Remove `data/processed/israel/cities_landuse/` from Vultr after verification
4. **Monitor performance**: Check that city-specific files are being used in logs

### 5. City Name Resolution

The `CityNameResolver` class (in `api/city_name_resolver.py`) can help convert:
- Hebrew names → English file names
- English variations → Standard file names

Example: "תל אביב" → "tel_aviv"

This ensures the correct `city` parameter is passed to the feature functions.

## Files Modified

1. `api/feature_engineering/environmental_features.py`
2. `api/feature_engineering/landuse_features.py`
3. `scripts/reorganize_city_data_vultr.py` (created)
4. `scripts/verify_reorganization.py` (created)

## Scripts Created

- `scripts/reorganize_city_data_vultr.py` - Reorganizes files in Vultr
- `scripts/verify_reorganization.py` - Verifies reorganization was successful
