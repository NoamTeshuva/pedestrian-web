# High-Precision Israel Network Precomputation Guide

## Overview

This guide explains how to precompute high-precision street networks and weather data for Israel, enabling **10x faster predictions** with **complete coverage** of the entire country.

## Architecture

### Zone-Based System
- Divide Israel into a regular grid (200-800 zones)
- Precompute street networks + centrality for each zone
- Precompute weather profiles for each zone
- Cache everything on Vultr Object Storage
- Runtime: instant lookups, no downloads or computation

### Benefits
- ✅ **10x faster predictions** (1-2s instead of 15-25s)
- ✅ **Complete Israel coverage** - every location cached
- ✅ **Consistent performance** - no network downloads at runtime
- ✅ **Offline-capable** - all data precomputed
- ✅ **Cost-effective** - one-time computation, unlimited usage

## Grid Size Recommendations

### Option 1: **High Precision (Recommended)** - 200 zones (20×10)
- **Cell size:** ~8.5km × 10km
- **Network download:** 2-4 hours
- **Weather profiles:** 2-3 hours (3,200 profiles)
- **Storage:** 1-2 GB total
- **Precision:** Excellent for urban + rural areas

### Option 2: Maximum Precision - 400 zones (40×20)
- **Cell size:** ~4.25km × 5km
- **Network download:** 4-8 hours
- **Weather profiles:** 4-6 hours (6,400 profiles)
- **Storage:** 2-4 GB total
- **Precision:** Maximum detail

### Option 3: Ultra-Precision - 800 zones (40×40)
- **Cell size:** ~4.25km × 2.5km
- **Network download:** 8-16 hours
- **Weather profiles:** 8-12 hours (12,800 profiles)
- **Storage:** 4-8 GB total
- **Precision:** Research-grade

## Step-by-Step Process

### Step 1: Precompute Street Networks (2-4 hours)

Download OSM networks and compute centrality for all zones:

```bash
# High precision (200 zones - RECOMMENDED)
python scripts/precompute_israel_networks.py --grid 20x10

# Maximum precision (400 zones)
python scripts/precompute_israel_networks.py --grid 40x20

# Ultra precision (800 zones)
python scripts/precompute_israel_networks.py --grid 40x40
```

**What it does:**
1. Generates weather zone grid
2. For each zone:
   - Downloads OSM street network via Overpass API
   - Computes betweenness centrality (~5-15s per zone)
   - Computes closeness centrality (~3-8s per zone)
   - Saves to GPKG with all features
3. Outputs to: `data/processed/israel/networks/IL_XXX_network.gpkg`

**Resume if interrupted:**
```bash
# Resume from zone 50
python scripts/precompute_israel_networks.py --grid 20x10 --start-zone 50
```

**Output files:**
```
data/processed/israel/networks/
├── IL_000_network.gpkg  (~5-10 MB each)
├── IL_001_network.gpkg
├── ...
└── IL_199_network.gpkg

data/processed/israel/
└── israel_weather_zones_20x10.gpkg  (zone boundaries)
```

### Step 2: Precompute Weather Profiles (2-3 hours)

Compute weather for all zones × seasons × times:

```bash
# High precision (200 zones)
python scripts/precompute_israel_weather_profiles.py --force --grid 20x10

# Maximum precision (400 zones)
python scripts/precompute_israel_weather_profiles.py --force --grid 40x20

# Ultra precision (800 zones)
python scripts/precompute_israel_weather_profiles.py --force --grid 40x40
```

**What it does:**
1. Loads zones from previous step
2. For each zone × season × time_of_day (200 zones × 4 × 4 = 3,200 calls):
   - Calls Open-Meteo API for zone center
   - Samples 5 representative dates per season
   - Averages weather data
3. Saves to parquet + CSV

**Output files:**
```
data/processed/israel/
├── israel_weather_profiles.parquet  (~1-5 MB)
├── israel_weather_profiles.csv      (for inspection)
└── israel_weather_zones.gpkg        (zone boundaries)
```

### Step 3: Consolidate into Single GPKG

Merge weather profiles into zone GPKG:

```bash
python scripts/merge_weather_into_gpkg.py
```

**Output:**
```
data/processed/israel/
└── israel_weather_zones.gpkg
    ├── zones layer (spatial - polygons with zone_id)
    └── profiles table (non-spatial - weather data)
```

### Step 4: Upload to Vultr

Upload all precomputed data to Vultr Object Storage:

```bash
# Upload weather data
python scripts/upload_weather_to_vultr.py

# Upload all network files (TODO: create this script)
python scripts/upload_networks_to_vultr.py --grid 20x10
```

**Vultr structure:**
```
s3://pedestrian-data-prod/
└── project/data/processed/israel/
    ├── israel_weather_zones.gpkg       (~200 KB)
    └── networks/
        ├── IL_000_network.gpkg         (~5-10 MB each)
        ├── IL_001_network.gpkg
        ├── ...
        └── IL_199_network.gpkg
```

### Step 5: Update app.py Runtime Logic

Modify `app.py` to load precomputed networks instead of downloading via OSMnx:

```python
# At app startup - download all networks from Vultr to /tmp
for zone_id in all_zone_ids:
    network_path = download_network_from_vultr(zone_id)
    ISRAEL_NETWORKS[zone_id] = gpd.read_file(network_path)

# During prediction
def predict(place, date):
    # Find which zone(s) contain the place
    zones = find_zones_for_place(place)

    # Load precomputed networks (already have centrality!)
    networks = [ISRAEL_NETWORKS[zone_id] for zone_id in zones]

    # Merge networks if spanning multiple zones
    network = pd.concat(networks)

    # Extract time features
    hour, is_weekend, time_of_day = extract_time_features(date)

    # Get precomputed weather
    weather = weather_store.get_weather_for_geometry(
        network.unary_union, season, time_of_day
    )

    # Compute land_use (only remaining feature)
    network['land_use'] = compute_land_use(network)

    # Run model - ALL other features already in network!
    predictions = model.predict(network[FEATURE_COLUMNS])

    return geojson_response(network, predictions)
```

## Storage Summary

### 200 Zones (20×10) - RECOMMENDED
| Component | Size | Count | Total |
|-----------|------|-------|-------|
| Zone boundaries | 200 KB | 1 file | 200 KB |
| Weather profiles | 1 MB | 3,200 records | 1 MB |
| Street networks | 5-10 MB | 200 files | 1-2 GB |
| **TOTAL** | | | **~1-2 GB** |

### 400 Zones (40×20)
| Component | Size | Count | Total |
|-----------|------|-------|-------|
| Zone boundaries | 400 KB | 1 file | 400 KB |
| Weather profiles | 2 MB | 6,400 records | 2 MB |
| Street networks | 5-10 MB | 400 files | 2-4 GB |
| **TOTAL** | | | **~2-4 GB** |

### 800 Zones (40×40)
| Component | Size | Count | Total |
|-----------|------|-------|-------|
| Zone boundaries | 800 KB | 1 file | 800 KB |
| Weather profiles | 4 MB | 12,800 records | 4 MB |
| Street networks | 5-10 MB | 800 files | 4-8 GB |
| **TOTAL** | | | **~4-8 GB** |

## Performance Comparison

### Current (On-Demand)
```
User requests Tel Aviv prediction
├─ Download OSM network: 5-10s
├─ Compute betweenness: 5-15s
├─ Compute closeness: 3-8s
├─ Fetch weather API: 1-2s
├─ Compute land_use: 0.5s
└─ Run model: 0.2s
TOTAL: 15-36s
```

### With Precomputation (200 zones)
```
User requests Tel Aviv prediction
├─ Lookup zone(s): 0.1s
├─ Load network from cache: 0.5s (already has centrality!)
├─ Get precomputed weather: 0.1s
├─ Compute land_use: 0.5s
└─ Run model: 0.2s
TOTAL: 1.4s

Speed improvement: 10-25x faster!
```

## Monitoring & Maintenance

### Check Coverage
```bash
# Count zones with networks
ls data/processed/israel/networks/*.gpkg | wc -l

# Expected: 200 (for 20x10), 400 (for 40x20), etc.
```

### Verify Quality
```bash
# Check for empty/failed zones
python scripts/check_network_quality.py --grid 20x10
```

### Refresh Schedule
- **Networks:** Annually (roads don't change often)
- **Weather:** Seasonally (4x per year for accuracy)
- **Both:** Can be refreshed independently

## Troubleshooting

### OSM Download Failures
Some zones (deserts, water) may have no streets. This is normal - script logs warnings and continues.

### Rate Limiting
If Overpass API throttles requests:
- Script auto-pauses 2s between zones
- If blocked, resume with `--start-zone XXX`

### Out of Memory
Large zones may consume RAM during centrality computation:
- Use smaller grid (e.g., 20x10 instead of 40x40)
- Or split into batches with `--start-zone`

## Next Steps

1. **Choose grid size** (recommended: 20×10 = 200 zones)
2. **Run network precomputation** (2-4 hours)
3. **Run weather precomputation** (2-3 hours)
4. **Upload to Vultr**
5. **Update app.py** to use precomputed data
6. **Deploy to Render**
7. **Enjoy 10x faster predictions!**

## Cost Analysis

### One-Time Costs (Your Time)
- Setup: 1 hour
- Computation wait: 4-7 hours (can run overnight)
- Upload: 30 minutes
- Integration: 2 hours
- **Total:** ~8 hours of work (mostly automated)

### Ongoing Costs
- Vultr storage: $0.01/GB/month × 2GB = **$0.02/month**
- API calls (weather): Near-zero (cached forever)
- Render compute: Free tier (no change)

### Value
- **10x faster predictions** = Better UX
- **100% Israel coverage** = More users
- **Predictable performance** = No API timeouts
- **ROI:** Priceless!
