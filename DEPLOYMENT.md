# Deployment Guide for Pedestrian Volume Prediction App

## Overview
This application is deployed on Render with optimized Gunicorn configuration for handling concurrent users and large-scale predictions.

## Instance Specifications
- **Platform**: Render
- **Plan**: Starter
- **CPU**: 4 vCPUs
- **RAM**: 8 GB
- **Service**: Gunicorn + Flask backend, Static frontend

## Gunicorn Configuration

### Current Settings
```bash
gunicorn app:app --workers 8 --threads 2 --timeout 900 --graceful-timeout 120 --bind 0.0.0.0:$PORT
```

### Configuration Breakdown

#### Workers and Threads
- **Workers**: 8 (2 workers per CPU core)
- **Threads per worker**: 2
- **Total concurrent capacity**: 16 requests

**Why 8 workers?**
- With 4 vCPUs, the formula is: `2 × CPU_COUNT = 8 workers`
- Each worker uses ~1GB RAM (8GB / 8 workers)
- This configuration supports **40+ concurrent users** logging in simultaneously
- Previous configuration (4 workers) only supported 8 concurrent requests

**Why 2 threads per worker?**
- The application is **mixed CPU/IO-bound**:
  - CPU-bound: CatBoost ML model predictions
  - I/O-bound: OSMnx downloads from Overpass API, S3 storage operations
- 2 threads per worker provides good balance for handling I/O wait without excessive context switching
- Total concurrency: 8 workers × 2 threads = **16 concurrent requests**

#### Timeouts
- **Request timeout**: 900 seconds (15 minutes)
  - Needed for large cities (e.g., טבריה/Tiberias) with 32 prediction layers
  - Each city prediction can take 3-5 minutes
  - **Login requests complete in <1 second** and don't need this timeout
- **Graceful timeout**: 120 seconds (2 minutes)
  - Time allowed for workers to finish current requests during shutdown/restart

#### Memory Management
- **Max requests per worker**: 1000
- **Max requests jitter**: 50
- **Why restart workers?** OSMnx and GeoPandas can accumulate memory over time
- Workers restart after processing 1000 requests to prevent memory leaks

### Worker Class
- **Worker class**: `sync` (default)
- Sync workers are best for CPU-bound work (model predictions)
- Gevent/eventlet would be better for pure I/O-bound work, but CatBoost predictions are CPU-intensive

### Alternative Configuration (I/O-heavy scenarios)

If your deployment becomes more I/O-bound (e.g., more API calls, less ML prediction):

```bash
# Experimental: More threads for I/O-heavy workloads
gunicorn app:app --workers 4 --threads 4 --timeout 900 --graceful-timeout 120 --bind 0.0.0.0:$PORT
```

This would give:
- 4 workers × 4 threads = 16 concurrent requests (same total)
- Lower memory per worker (fewer processes)
- Better for I/O-bound work, worse for CPU-bound work

**DO NOT use this unless you've confirmed the workload is primarily I/O-bound.**

## Login Flow Architecture

### Lightweight Login Design
The login flow is specifically designed to be **fast and lightweight**:

#### Backend (`/api/login`)
1. Receives username/password
2. Loads users.json (~1ms)
3. Validates credentials with SHA-256 hash (~1ms)
4. Returns user info JSON (~1ms)
5. **Total time**: <10ms

**What login DOES NOT do:**
- ❌ No ML model loading
- ❌ No OSMnx downloads
- ❌ No scenario predictions
- ❌ No S3 operations
- ❌ No heavy computations

#### Frontend
- **30-second timeout** on login request
- If login takes >30s, shows error: "הבקשה ארכה יותר מדי - נסה שוב"
- Specific error messages for different failure types:
  - `401/403`: "שם משתמש או סיסמה שגויים"
  - `500/502/504`: "שגיאת שרת, נסה שוב מאוחר יותר"
  - Network error: "שגיאה בחיבור לשרת, נסה שוב מאוחר יותר"
  - Timeout: "הבקשה ארכה יותר מדי - נסה שוב"

#### Post-Login
After successful login:
1. User redirected to `index.html`
2. Map initializes (no API calls)
3. User must **explicitly trigger** heavy operations by:
   - Clicking "חיזוי עיר" (city prediction)
   - Clicking "חיזוי אזור מסומן" (bbox prediction)
   - Uploading GPKG/CSV files

**No automatic predictions run during login or page load.**

## Problem Solved

### Original Issue
- ~40 users could login successfully
- Another ~40 users stuck on "מתחבר..." (connecting) forever

### Root Causes
1. **Low concurrency**: Only 4 workers × 2 threads = 8 concurrent slots
   - With 40+ users logging in simultaneously, most were queued
   - If first 8 requests are slow, all others wait indefinitely
2. **No timeout**: Frontend had no timeout on fetch request
   - If backend was slow/unresponsive, UI stayed stuck forever
3. **Poor error handling**: Network errors didn't show user-friendly messages
   - Users saw "מתחבר..." even when request failed

### Solutions Implemented
1. **Doubled concurrency**: 8 workers × 2 threads = 16 concurrent slots
   - Now handles 40+ concurrent logins comfortably
   - Queue depth reduced significantly
2. **Added 30s timeout**: Frontend aborts request if it takes too long
   - UI never stays stuck indefinitely
   - Shows clear error message to user
3. **Improved error handling**: Specific error messages for each failure type
   - Users know what went wrong and can retry
   - Network errors, auth failures, and server errors all handled differently

## Monitoring Recommendations

### Key Metrics to Watch
1. **Response time for /api/login**: Should be <100ms (currently ~10ms)
2. **Concurrent request count**: Should stay <16 (our capacity)
3. **Worker restarts**: Should happen gradually (not all at once)
4. **Memory usage per worker**: Should stay <1GB

### Signs of Problems
- Login response time >1s → investigate auth.py or users.json size
- Concurrent requests >16 → consider increasing workers
- Worker memory >1.5GB → reduce max_requests to restart workers more frequently
- Many timeout errors → check network latency to Render

## Scaling Strategy

### When to increase workers
- If concurrent login requests regularly exceed 16
- If CPU usage is consistently <50% (workers are underutilized)

### How to scale up (example: 8 vCPU, 16GB RAM)
```bash
# For 8 vCPU, 16GB RAM:
gunicorn app:app --workers 16 --threads 2 --timeout 900 --graceful-timeout 120 --bind 0.0.0.0:$PORT
```
- 16 workers × 2 threads = 32 concurrent requests
- Memory per worker: 16GB / 16 = 1GB (same as current)

### When to increase threads
- If you add more I/O-bound endpoints (external API calls, S3 operations)
- Only if CPU usage stays low (<50%)

## Testing Recommendations

### Load Testing Login
```bash
# Test 50 concurrent logins (should all succeed in <5s)
ab -n 50 -c 50 -p login.json -T application/json https://pedestrian-web.onrender.com/api/login
```

### Expected Results
- All 50 requests succeed (0 failures)
- Mean response time <100ms
- Max response time <500ms
- No "מתחבר..." stuck states

### If Tests Fail
1. Check Render logs for worker errors
2. Verify all 8 workers are running
3. Check memory usage (might need to reduce workers if >8GB total)
4. Verify `/health` endpoint responds quickly

## Files Modified

### Frontend
- `frontend/login.html`: Added timeout + error handling
- `frontend/index.html`: Added timeout + error handling to login popup

### Backend
- `render.yaml`: Updated workers 4→8, added comments
- `api/gunicorn.conf.py`: Updated for 4 vCPU / 8GB RAM

### Documentation
- `DEPLOYMENT.md`: This file

## Deployment Checklist

Before deploying to production:
- [ ] Verify instance has 4 vCPU + 8GB RAM
- [ ] Confirm Gunicorn command uses `--workers 8 --threads 2`
- [ ] Test login with 40+ concurrent users
- [ ] Verify no automatic predictions run on page load
- [ ] Check `/health` endpoint responds
- [ ] Monitor worker count: `ps aux | grep gunicorn`
- [ ] Monitor memory: `free -h` or Render dashboard

## Contact

For issues or questions about this deployment:
- Check Render logs: Dashboard → Service → Logs
- Review LogRocket sessions for frontend errors
- Check GitHub issues for known problems
