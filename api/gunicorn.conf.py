# Gunicorn configuration optimized for Render Pro (4GB RAM, 2 CPU)

import multiprocessing
import os

# Render Pro: 2 CPUs, 4GB RAM
# Optimal worker count: (2 * CPU) + 1 = 5, but we use 4 for memory headroom
# Each worker can use ~1GB RAM (4GB / 4 workers)
workers = 4

# CRITICAL: Extended timeout for large city predictions (32 layers)
# Tiberias with 32 layers takes ~3 minutes, so we allow 15 minutes for safety
# This prevents WORKER TIMEOUT errors on large cities
timeout = 900  # 15 minutes (was 30 seconds default)

# Graceful timeout: time to finish current requests during shutdown
graceful_timeout = 120  # 2 minutes

# Keep-alive for client connections
keepalive = 5

# Worker class: 'sync' is best for CPU-bound work (model predictions)
# 'gevent' or 'eventlet' would be better for I/O-bound, but OSMnx + CatBoost are CPU-heavy
worker_class = 'sync'

# Threads per worker: helps with I/O-bound OSMnx downloads
# 2 threads * 4 workers = 8 concurrent operations max
threads = 2

# Restart workers after N requests to prevent memory leaks
# OSMnx and geopandas can accumulate memory over time
max_requests = 1000
max_requests_jitter = 50  # Add randomness to prevent all workers restarting at once

# Logging
accesslog = '-'  # Log to stdout (Render captures this)
errorlog = '-'   # Log to stderr
loglevel = 'info'

# Preload app before forking workers (saves memory via copy-on-write)
preload_app = True

# Bind address (Render sets PORT env var)
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"

# Worker process name (helps with monitoring)
proc_name = 'pedestrian-prediction-api'

# Security: limit request header/body size
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

print("=" * 60)
print("Gunicorn Configuration for Render Pro Plan")
print("=" * 60)
print(f"Workers: {workers}")
print(f"Timeout: {timeout}s (15 minutes)")
print(f"Threads per worker: {threads}")
print(f"Total concurrent capacity: {workers * threads} requests")
print(f"Memory per worker: ~{4096 // workers}MB (estimate)")
print(f"Graceful timeout: {graceful_timeout}s")
print("=" * 60)
