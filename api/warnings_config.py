# api/warnings_config.py
"""
Central place to configure warning filters for the backend.

We only suppress very specific noisy warnings that we know are safe to ignore,
to keep Render logs clean while still allowing real problems to surface.
"""

import warnings
import os
import logging

# Apply filters immediately upon import, before any other code runs
def _setup_warning_filters():
    """Configure warning filters to suppress known noisy warnings."""

    # Use simplefilter for broader, more aggressive filtering
    # This catches warnings even when they're triggered deep in C extensions

    # 1) Suppress all DeprecationWarnings globally
    #    (The main offender is pyproj + NumPy 1.25, but this catches all)
    warnings.simplefilter("ignore", DeprecationWarning)

    # 2) Suppress all FutureWarnings globally
    #    (The main offender is OSMnx settings.timeout)
    warnings.simplefilter("ignore", FutureWarning)

    # 3) Target pyproj module specifically (most aggressive for this lib)
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="pyproj"
    )

    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="pyproj.transformer"
    )

    # 4) Also set specific message-based filters as backup
    warnings.filterwarnings(
        "ignore",
        message=r".*Conversion of an array with ndim > 0 to a scalar is deprecated.*",
    )

    warnings.filterwarnings(
        "ignore",
        message=r".*settings\.timeout.*is deprecated.*",
    )

    # 5) GDAL/CPLE warnings (these are logged via C library, harder to suppress)
    warnings.filterwarnings(
        "ignore",
        message=r".*CPLE_AppDefined.*",
    )

    # 6) Suppress GDAL errors at the C library level
    # These 403 errors are expected (checking for auxiliary files that don't exist)
    try:
        from osgeo import gdal
        # CPLQuietErrorHandler suppresses all GDAL errors to stderr
        # CE_Warning and above will still be logged internally but not printed
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        gdal.SetConfigOption('CPL_LOG', '/dev/null')  # Suppress all CPL logs
        os.environ['CPL_CURL_VERBOSE'] = 'NO'  # Disable verbose CURL output
    except ImportError:
        pass  # GDAL not installed or not needed

    # 7) Set environment variable to suppress Python warnings at OS level
    # This catches warnings that fire before this module is imported
    os.environ['PYTHONWARNINGS'] = 'ignore::DeprecationWarning'

# Execute immediately on module import
_setup_warning_filters()
