#!/usr/bin/env python3
"""
Check if all cache environment variables are set correctly.
Run this on Render to diagnose cache issues.
"""
import os
import sys

print("=" * 60)
print("CACHE ENVIRONMENT CHECK")
print("=" * 60)

# Check required environment variables
env_vars = {
    'S3_ACCESS_KEY': os.getenv('S3_ACCESS_KEY'),
    'S3_SECRET_KEY': os.getenv('S3_SECRET_KEY'),
    'S3_ENDPOINT': os.getenv('S3_ENDPOINT'),
    'S3_BUCKET': os.getenv('S3_BUCKET'),
    'MODEL_VERSION': os.getenv('MODEL_VERSION'),
}

all_set = True
for key, value in env_vars.items():
    if value:
        # Mask secrets
        if 'SECRET' in key or 'KEY' in key:
            display_value = value[:8] + '...' if len(value) > 8 else '***'
        else:
            display_value = value
        print(f"[OK] {key}: {display_value}")
    else:
        print(f"[MISSING] {key}: NOT SET")
        all_set = False

print()

# Try importing cache module
print("Testing cache module import...")
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from cache.vultr_cache import get_s3_client, build_cache_key
    print("[OK] Cache module imported successfully")

    # Try initializing S3 client
    client = get_s3_client()
    if client:
        print("[OK] S3 client initialized")

        # Try listing predictions folder
        try:
            bucket = os.getenv('S3_BUCKET')
            response = client.list_objects_v2(
                Bucket=bucket,
                Prefix='predictions/',
                MaxKeys=5
            )
            if 'Contents' in response:
                print(f"[OK] Found {len(response['Contents'])} cached predictions")
            else:
                print("[INFO] predictions/ folder is empty (expected for first run)")
        except Exception as e:
            print(f"[WARN] Could not list bucket: {e}")
    else:
        print("[FAIL] S3 client initialization failed")

except Exception as e:
    print(f"[FAIL] Cache module import failed: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 60)

if all_set:
    print("RESULT: All environment variables are set correctly")
    print("If cache still not working, check app.py CACHE_ENABLED flag")
else:
    print("RESULT: Some environment variables are MISSING")
    print("Add them in Render dashboard → Environment tab")

print("=" * 60)
