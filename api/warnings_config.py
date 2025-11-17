# api/warnings_config.py
"""
Central place to configure warning filters for the backend.

We only suppress very specific noisy warnings that we know are safe to ignore,
to keep Render logs clean while still allowing real problems to surface.
"""

import warnings

# 1) pyproj + NumPy 1.25 deprecation:
#    "Conversion of an array with ndim > 0 to a scalar is deprecated..."
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r"Conversion of an array with ndim > 0 to a scalar is deprecated.*",
    module=r"pyproj\.transformer",
)

# 2) OSMnx FutureWarning about settings.timeout:
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message=r"`settings\.timeout` is deprecated and will be removed in the v2\.0\.0 release.*",
)
