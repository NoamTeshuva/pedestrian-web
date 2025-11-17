# api/warnings_config.py
"""
Central place to configure warning filters for the backend.

We only suppress very specific noisy warnings that we know are safe to ignore,
to keep Render logs clean while still allowing real problems to surface.
"""

import warnings
import sys

# Apply filters immediately upon import, before any other code runs
def _setup_warning_filters():
    """Configure warning filters to suppress known noisy warnings."""

    # 1) pyproj + NumPy 1.25 deprecation:
    #    "Conversion of an array with ndim > 0 to a scalar is deprecated..."
    #    We don't specify 'module' to ensure it catches all occurrences
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message=r".*Conversion of an array with ndim > 0 to a scalar is deprecated.*",
    )

    # 2) OSMnx FutureWarning about settings.timeout:
    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        message=r".*settings\.timeout.*is deprecated.*",
    )

    # 3) GDAL/CPLE warnings from rasterio/GDAL trying auxiliary files (safe to ignore)
    warnings.filterwarnings(
        "ignore",
        message=r".*CPLE_AppDefined.*",
    )

# Execute immediately on module import
_setup_warning_filters()

# Also set PYTHONWARNINGS environment variable as a fallback for subprocesses
if 'PYTHONWARNINGS' not in sys.argv:
    # This helps catch warnings in worker processes
    import os
    os.environ.setdefault('PYTHONWARNINGS',
        'ignore::DeprecationWarning:pyproj,'
        'ignore::FutureWarning:osmnx'
    )
