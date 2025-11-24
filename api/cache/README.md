# Vultr Object Storage Caching

This module implements prediction result caching using Vultr Object Storage (S3-compatible).

## Overview

The caching system provides a **fast path/slow path** architecture:

- **Fast path**: Check Vultr cache first, return immediately if found (~100ms)
- **Slow path**: Run expensive model pipeline, cache result for future use (~5-10s)

## Supported Regions

**CRITICAL**: Only **Israel** is currently supported for caching.

Requests with `country != "israel"` will return a 400 error.

## Cache Key Structure

Cache keys follow this format:

```
predictions/<model_version>/israel/<city>/<season>/weekend<0_or_1>/<time_of_day>/bbox_<token>.geojson.gz
```

### Example Cache Keys

```
predictions/cb_model_israel_v1/israel/tel_aviv/summer/weekend1/morning/bbox_34.77_32.06_34.81_32.09.geojson.gz
predictions/cb_model_israel_v1/israel/haifa/winter/weekend0/evening/bbox_34.98_32.79_35.08_32.84.geojson.gz
```

### Cache Key Components

1. **model_version**: From `MODEL_VERSION` env var (e.g., `cb_model_israel_v1`)
2. **country**: Country name (normalized to lowercase) - **must be "israel"**
3. **city**: City name (normalized: lowercase, spaces→underscores)
4. **season**: Season name (`winter`, `spring`, `summer`, `autumn`)
5. **weekend flag**: `weekend1` (weekend) or `weekend0` (weekday)
6. **time_of_day**: Time period (`morning`, `afternoon`, `evening`, `night`)
7. **bbox_token**: Rounded bbox coordinates (2 decimal places): `min_lon_min_lat_max_lon_max_lat`

## Storage Format

Results are stored as **gzipped GeoJSON** files:

- **Compression**: gzip level 6
- **Content-Type**: `application/json`
- **Content-Encoding**: `gzip`
- **Typical compression ratio**: 5-10x

## Configuration

Set these environment variables:

```bash
# S3-compatible credentials (reused from existing config)
S3_ACCESS_KEY=<vultr_access_key>
S3_SECRET_KEY=<vultr_secret_key>
S3_ENDPOINT=https://ams1.vultrobjects.com
S3_BUCKET=pedestrian-data-prod

# Model version for cache namespacing
MODEL_VERSION=cb_model_israel_v1
```

## Usage in Flask App

The caching is automatically integrated into the `/predict-multi` endpoint:

```python
# Example request (with caching)
GET /predict-multi?place=Tel Aviv&seasons=summer,winter&week_types=weekday,weekend&times_of_day=morning,evening

# Explicit country parameter (optional, defaults to israel)
GET /predict-multi?place=Haifa&country=israel&seasons=summer
```

### Cache Hit Behavior

1. Check cache for each layer (season/week_type/time_of_day combination)
2. If cache exists, load compressed GeoJSON and return immediately
3. If cache miss, run model pipeline and save result

### Error Handling

Caching uses **best-effort** error handling:

- Cache read errors: Log warning, fall back to model pipeline
- Cache write errors: Log warning, don't crash (user still gets result)
- S3 credentials missing: Caching disabled, always run model

## Cache Invalidation

### When to Invalidate

Invalidate cache when:

1. **Model changes**: New model version trained
2. **Feature changes**: New features added or modified
3. **Data updates**: OSM network data updated
4. **Weather data changes**: Historical weather data corrected

### How to Invalidate

#### Option 1: Change MODEL_VERSION

Update the `MODEL_VERSION` environment variable:

```bash
# Old cache keys (ignored)
predictions/cb_model_israel_v1/...

# New cache keys (empty)
predictions/cb_model_israel_v2/...
```

#### Option 2: Delete Specific City

Use AWS CLI or Vultr web interface to delete cache for specific city:

```bash
aws s3 rm s3://pedestrian-data-prod/predictions/cb_model_israel_v1/israel/tel_aviv/ --recursive --endpoint-url https://ams1.vultrobjects.com
```

#### Option 3: Delete Entire Cache

Delete the entire predictions prefix:

```bash
aws s3 rm s3://pedestrian-data-prod/predictions/ --recursive --endpoint-url https://ams1.vultrobjects.com
```

## API Reference

### `build_cache_key(country, city, season, is_weekend, time_of_day, bbox)`

Build cache key from prediction parameters.

**Parameters:**
- `country` (str): Country name (must be "israel")
- `city` (str): City name (normalized automatically)
- `season` (str): Season name
- `is_weekend` (bool): Weekend flag
- `time_of_day` (str): Time of day
- `bbox` (tuple): Bounding box (min_lon, min_lat, max_lon, max_lat)

**Returns:** S3 object key (str)

### `cache_exists(cache_key)`

Check if cache entry exists.

**Parameters:**
- `cache_key` (str): S3 object key

**Returns:** True if exists, False otherwise

### `load_cached_geojson(cache_key)`

Load and decompress cached GeoJSON.

**Parameters:**
- `cache_key` (str): S3 object key

**Returns:** GeoJSON dict if found, None otherwise

### `save_cached_geojson(cache_key, geojson)`

Compress and save GeoJSON to cache.

**Parameters:**
- `cache_key` (str): S3 object key
- `geojson` (dict): GeoJSON dict to cache

**Returns:** True if successful, False otherwise

### `validate_country(country)`

Validate country is supported for caching.

**Parameters:**
- `country` (str): Country name

**Returns:** True if supported (israel), False otherwise

## Monitoring

Check logs for cache performance:

```bash
# Cache hits
grep "CACHE HIT" logs/flask.log

# Cache misses (saves)
grep "CACHE SAVE" logs/flask.log

# Cache errors
grep "CACHE.*Error" logs/flask.log
```

## Performance Metrics

**Without cache (cold)**:
- Feature extraction: ~3s
- Model prediction (32 layers): ~5-7s
- Total: **~8-10s**

**With cache (warm)**:
- Cache checks (32 layers): ~100-200ms
- Cache loads (32 layers): ~300-500ms
- Total: **~400-700ms** (15-20x speedup)

## Security Notes

1. **Credentials**: Never commit S3 credentials to git
2. **Bucket policy**: Ensure bucket is private (not public)
3. **Cache keys**: Include model version to prevent stale data
4. **Input validation**: Country parameter validated before cache access

## Troubleshooting

### Cache not being used

Check:
1. S3 credentials set in environment
2. `CACHE_ENABLED` flag is True (check app startup logs)
3. `place` parameter provided (caching requires city name)
4. `bbox` parameter provided (needed for cache key)

### Cache errors

Common issues:
1. **403 Forbidden**: Check S3 credentials and bucket permissions
2. **404 Not Found**: Cache miss (expected on first request)
3. **Connection timeout**: Check S3_ENDPOINT URL
4. **Gzip errors**: Corrupted cache file (delete and regenerate)

### Performance not improving

Possible causes:
1. Cache misses (check logs for "CACHE HIT")
2. Different bbox values (bbox rounded to 2 decimals)
3. Model version changed (new cache namespace)
4. Cache cleared/invalidated

## Future Enhancements

Possible improvements:

1. **Multi-country support**: Add USA, Europe regions
2. **Cache warming**: Pre-compute popular cities
3. **TTL/expiration**: Auto-invalidate old cache entries
4. **Cache statistics**: Track hit rates, storage usage
5. **Compression optimization**: Test different compression levels
6. **CDN integration**: Use CloudFlare or similar for faster access
