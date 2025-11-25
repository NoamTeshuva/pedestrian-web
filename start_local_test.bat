@echo off
echo Starting Flask app with cache enabled...
echo.
echo Watch for these messages:
echo   [CACHE SAVE] - First prediction (slow path)
echo   [CACHE HIT]  - Cached prediction (fast path)
echo.
echo Press Ctrl+C to stop
echo.
cd api
python app.py
