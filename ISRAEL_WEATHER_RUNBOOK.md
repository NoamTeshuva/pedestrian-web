# Israel Precomputed Weather Zones - Runbook

## Overview

This system provides **fast, precomputed weather profiles for Israel** to dramatically reduce prediction latency. Instead of making live API calls for every prediction request (which can take 3-5 minutes for 16 season/time combinations), the system:

1. Divides Israel into ~50 weather zones
2. Precomputes weather for each zone × season × time_of_day offline
3. Looks up precomputed values at runtime (milliseconds instead of minutes)
4. Falls back to live API for non-Israel locations

## Architecture

### Components

1. **`api/feature_engineering/israel_weather_zones.py`**
   - Defines ~50 weather zones covering Israel as a grid
   - Provides spatial lookup: coordinate → zone_id
   - Checks if a location is in Israel

2. **`api/feature_engineering/weather_features.py`** (modified)
   - Extracted `get_seasonal_weather_profile()` function for reuse
   - Modified `compute_weather_features()` to check if location is in Israel
   - Uses precomputed profiles for Israel, live API for others

3. **`api/feature_engineering/weather_profile_store.py`**
   - Loads precomputed profiles at app startup
   - Provides fast lookup: (zone, season, time_of_day) → weather dict
   - Handles fallback if profiles missing

4. **`scripts/precompute_israel_weather_profiles.py`**
   - Offline script to generate all weather profiles
   - Iterates over 50 zones × 4 seasons × 4 times = 800 profiles
   - Saves to parquet and CSV

5. **`scripts/test_israel_weather.py`**
   - Test suite for zones and profiles
   - Validates system works correctly

6. **`api/app.py`** (modified)
   - Initializes weather profile store at startup
   - Configuration via environment variables

## Quick Start

### Step 1: Generate Weather Zones (Optional)

Zones are automatically generated on first use, but you can pre-generate:

```bash
cd /path/to/Pedestrain_Volume_app
python scripts/test_israel_weather.py --generate-zones
```

This creates: `data/processed/israel/israel_weather_zones.gpkg`

### Step 2: Precompute Weather Profiles

**⚠️ This takes ~45-60 minutes and makes 800 API calls to Open-Meteo**

```bash
cd /path/to/Pedestrain_Volume_app
python scripts/precompute_israel_weather_profiles.py
```

Output files:
- `data/processed/israel/israel_weather_profiles.parquet` (for production)
- `data/processed/israel/israel_weather_profiles.csv` (for inspection)
- `precompute_weather.log` (detailed log)

**Test mode** (only 3 zones, faster):
```bash
python scripts/precompute_israel_weather_profiles.py --test-mode
```

**Force overwrite** existing profiles:
```bash
python scripts/precompute_israel_weather_profiles.py --force
```

### Step 3: Verify Installation

```bash
python scripts/test_israel_weather.py --all
```

This runs:
- Zone generation and lookup test
- Profile loading test
- Comparison with live weather

Expected output:
```
==============================================================
ISRAEL WEATHER ZONES SYSTEM - TEST SUITE
==============================================================

TEST 1: Weather Zones Generation and Lookup
==============================================================
✓ Generated 50 zones
...

TEST 2: Precomputed Weather Profiles
==============================================================
✓ Store loaded:
  - Zones: 50
  - Profiles: 800
...

✓ ALL TESTS COMPLETED
```

### Step 4: Enable in Production

The system is **enabled by default** if profiles are present. To control:

**Environment Variables** (in `.env` or Render dashboard):

```bash
# Enable/disable precomputed weather for Israel
USE_ISRAEL_PRECOMPUTED_WEATHER=true

# Custom paths (optional)
ISRAEL_WEATHER_PROFILES_PATH=data/processed/israel/israel_weather_profiles.parquet
ISRAEL_WEATHER_ZONES_PATH=data/processed/israel/israel_weather_zones.gpkg
```

**To disable** (use live API for everything):
```bash
USE_ISRAEL_PRECOMPUTED_WEATHER=false
```

### Step 5: Deploy to Render

1. **Commit files to git:**
```bash
git add api/feature_engineering/israel_weather_zones.py
git add api/feature_engineering/weather_profile_store.py
git add api/feature_engineering/weather_features.py
git add api/app.py
git add scripts/precompute_israel_weather_profiles.py
git add scripts/test_israel_weather.py
git add data/processed/israel/israel_weather_profiles.parquet
git add data/processed/israel/israel_weather_zones.gpkg
git commit -m "feat: add precomputed weather zones for Israel"
git push origin main
```

2. **Or upload to Vultr S3:**
```bash
# Upload profiles to S3 (if using Vultr storage)
aws s3 cp data/processed/israel/israel_weather_profiles.parquet \
    s3://pedestrian-data-prod/project/data/processed/israel/ \
    --endpoint-url=https://ams1.vultrobjects.com

aws s3 cp data/processed/israel/israel_weather_zones.gpkg \
    s3://pedestrian-data-prod/project/data/processed/israel/ \
    --endpoint-url=https://ams1.vultrobjects.com
```

3. **Render will auto-deploy** on git push

## Maintenance

### Refresh Weather Profiles

Weather profiles should be refreshed periodically (monthly or seasonally) to reflect recent weather patterns:

```bash
# Refresh profiles
python scripts/precompute_israel_weather_profiles.py --force

# Test after refresh
python scripts/test_israel_weather.py --test-profiles
```

### Monitor Logs

At app startup, look for:

```
✓ Israel weather profile store initialized successfully
  - Zones: 50
  - Profiles: 800
```

During predictions for Israel:

```
Using precomputed Israel weather for winter/morning
Retrieved precomputed weather: temp=12.5°C, precip=1.2mm, wind=8.3km/h
```

For non-Israel:

```
Fetching winter weather averaged from 5 dates, time of day: morning (hours: [6, 7, 8, 9])
```

### Troubleshooting

**Problem:** "Profiles file not found"

```
Israel weather profiles not found at data/processed/israel/israel_weather_profiles.parquet
Run scripts/precompute_israel_weather_profiles.py to generate profiles
Will use live weather API for all locations
```

**Solution:** Run the precomputation script (Step 2)

---

**Problem:** Weather still slow for Israel

**Check:**
1. Is `USE_ISRAEL_PRECOMPUTED_WEATHER=true`?
2. Are profiles loaded? Check startup logs
3. Are coordinates actually in Israel? Check with:
   ```python
   from api.feature_engineering.israel_weather_zones import is_in_israel
   print(is_in_israel(32.0853, 34.7818))  # Tel Aviv: should be True
   ```

---

**Problem:** "Failed to use precomputed Israel weather: ..."

**Action:** System automatically falls back to live API. Check:
- Parquet file is not corrupted
- GeoPandas can load zones file
- Profiles have valid (non-NaN) values

---

**Problem:** Test mode profiles don't work in production

**Solution:** Test mode only processes 3 zones. Must run full precomputation for production:
```bash
python scripts/precompute_israel_weather_profiles.py  # No --test-mode flag
```

## Performance Impact

### Before (Live API for Israel)
- Single town prediction: **3-5 minutes** (16 API calls × ~10-20s each)
- Multi-location request: **timeout / very slow**

### After (Precomputed Profiles for Israel)
- Single town prediction: **< 30 seconds** (weather lookup: milliseconds)
- Multi-location request: **feasible** (no weather API bottleneck)
- Non-Israel locations: **unchanged** (still use live API)

## File Sizes

- `israel_weather_zones.gpkg`: ~50 KB (50 polygons)
- `israel_weather_profiles.parquet`: ~25-50 KB (800 rows, compressed)
- `israel_weather_profiles.csv`: ~80-100 KB (for inspection)

Total: < 200 KB (negligible for git/S3)

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_ISRAEL_PRECOMPUTED_WEATHER` | `true` | Enable precomputed Israel weather |
| `ISRAEL_WEATHER_PROFILES_PATH` | `data/processed/israel/israel_weather_profiles.parquet` | Path to profiles file |
| `ISRAEL_WEATHER_ZONES_PATH` | `data/processed/israel/israel_weather_zones.gpkg` | Path to zones file |

### Grid Configuration

In `israel_weather_zones.py`:
```python
generate_israel_weather_zones(n_cols=10, n_rows=5)  # 50 zones
```

To increase resolution:
```python
generate_israel_weather_zones(n_cols=15, n_rows=8)  # 120 zones
```

Note: More zones = more precomputation time but finer spatial resolution.

### Israel Bounding Box

In `israel_weather_zones.py`:
```python
ISRAEL_BOUNDS = {
    'west': 34.2,    # Mediterranean coast
    'east': 35.9,    # Jordan Valley
    'south': 29.4,   # Eilat region
    'north': 33.3    # Northern border
}
```

## API Behavior

### For Israel Locations

```python
# Request for Tel Aviv
GET /predict-multi?place=תל-אביב-יפו&seasons=winter&times_of_day=morning

# Backend behavior:
# 1. Extract street network (OSM)
# 2. Compute features (land use, centrality, etc.)
# 3. Check if in Israel: YES
# 4. Look up precomputed weather: zone IL_023, winter, morning
# 5. Return predictions (fast!)
```

### For Non-Israel Locations

```python
# Request for Paris
GET /predict?place=Paris&date=2025-01-15T09:00:00

# Backend behavior:
# 1. Extract street network (OSM)
# 2. Compute features
# 3. Check if in Israel: NO
# 4. Fetch live weather from Open-Meteo API (slower)
# 5. Return predictions
```

## Future Enhancements

1. **Other Countries:** Add precomputed zones for other frequently-requested countries
2. **S3 Integration:** Fetch profiles directly from S3 instead of git
3. **Auto-refresh:** Scheduled job to refresh profiles monthly
4. **Finer Resolution:** Increase from 50 to 100+ zones for better accuracy
5. **Caching:** Cache live API results for non-Israel locations

## Support

For issues or questions:
1. Check logs for error messages
2. Run test suite: `python scripts/test_israel_weather.py --all`
3. Verify profiles exist and are valid
4. Try disabling: `USE_ISRAEL_PRECOMPUTED_WEATHER=false`

## Summary

This system provides **10-20x speedup** for Israel weather features by precomputing weather zones offline. It's **transparent to users** (same API), **safe** (automatic fallback), and **maintainable** (simple scripts to refresh).

Key files:
- **Zones:** `data/processed/israel/israel_weather_zones.gpkg`
- **Profiles:** `data/processed/israel/israel_weather_profiles.parquet`
- **Precompute:** `scripts/precompute_israel_weather_profiles.py`
- **Test:** `scripts/test_israel_weather.py`
- **Config:** Environment variable `USE_ISRAEL_PRECOMPUTED_WEATHER`
