#!/usr/bin/env python3
"""
weather_features.py

Provides weather features for pedestrian volume prediction using Open-Meteo API.
Implements smart weather fetching:
- Same season → Use last week's weather (most recent)
- Different season → Use last occurrence of that season

Falls back to seasonal defaults if API is unavailable.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import geopandas as gpd
import requests


class WeatherError(Exception):
    """Exception for weather feature extraction errors."""
    def __init__(self, message: str, code: int = 500, details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


def get_season(date: datetime) -> str:
    """
    Get season for a given date (Northern Hemisphere).

    Parameters
    ----------
    date : datetime
        Date to determine season for

    Returns
    -------
    str
        Season name: 'winter', 'spring', 'summer', 'autumn'
    """
    month = date.month
    if month in [12, 1, 2]:
        return 'winter'
    elif month in [3, 4, 5]:
        return 'spring'
    elif month in [6, 7, 8]:
        return 'summer'
    else:  # 9, 10, 11
        return 'autumn'


def get_seasonal_sample_dates(target_timestamp: datetime, n_samples: int = 5) -> list:
    """
    Get multiple representative dates from the target season for averaging.

    This provides more robust seasonal weather by averaging across multiple days
    rather than relying on a single day's weather.

    Parameters
    ----------
    target_timestamp : datetime
        The timestamp user is requesting prediction for
    n_samples : int
        Number of sample dates to fetch from the season (default 5)

    Returns
    -------
    list
        List of datetime objects representing different days in the target season
    """
    now = datetime.now()
    target_season = get_season(target_timestamp)

    # Get the 3 months that belong to this season
    season_months = {
        'winter': [12, 1, 2],
        'spring': [3, 4, 5],
        'summer': [6, 7, 8],
        'autumn': [9, 10, 11]
    }

    months = season_months[target_season]
    sample_dates = []

    # For each month in the season, sample from early, mid, and late parts
    # Always use last year's complete season to ensure all dates are in the past
    base_year = now.year

    # Determine which year to sample from
    # If current month is in the target season and we're past mid-season, use this year
    # Otherwise, go back one year to ensure complete historical data
    current_season = get_season(now)
    if current_season == target_season:
        # Same season: check if we have enough historical data
        # Use last year's season to get complete data
        year_offset = 1
    else:
        # Different season: check if that season has occurred this year yet
        # For example, if today is Nov 2025 and we want summer, use 2025
        # If today is Nov 2025 and we want winter (Dec-Feb), use 2024
        if months[0] == 12:  # Winter season starts in December
            # Winter spans Dec-Jan-Feb, need to check carefully
            if now.month >= 3:  # After February, last winter is Dec prev year to Feb this year
                year_offset = 1  # Use last year's December
            else:  # Jan-Feb, we're in winter now
                year_offset = 1  # Use previous winter
        else:
            # For other seasons, if the latest month of the season hasn't passed yet, go back a year
            if now.month < months[2]:
                year_offset = 1
            else:
                year_offset = 0

    # Always go back at least one year to ensure historical data availability
    year_offset = 1
    sample_year = base_year - year_offset

    # Sample from different days across the season
    # Early season
    sample_dates.append(datetime(sample_year, months[0], 10))
    # Mid-early season
    sample_dates.append(datetime(sample_year, months[1], 5))
    # Mid season
    sample_dates.append(datetime(sample_year, months[1], 15))
    # Mid-late season
    sample_dates.append(datetime(sample_year, months[1], 25))
    # Late season
    sample_dates.append(datetime(sample_year, months[2], 20))

    logging.info(f"Sampling {target_season} weather from {len(sample_dates)} dates in {sample_year}")
    return sample_dates[:n_samples]


def get_time_of_day_hours(time_of_day: str) -> list:
    """
    Get representative hours for each time of day to average weather.

    Parameters
    ----------
    time_of_day : str
        Time of day: 'morning', 'afternoon', 'evening', 'night'

    Returns
    -------
    list
        List of hours (0-23) representing that time of day
    """
    time_of_day_map = {
        'morning': [6, 7, 8, 9],          # 6am - 9am
        'afternoon': [12, 13, 14, 15],    # 12pm - 3pm
        'evening': [18, 19, 20, 21],      # 6pm - 9pm
        'night': [22, 23, 0, 1]           # 10pm - 1am
    }
    return time_of_day_map.get(time_of_day.lower(), [12])  # Default to noon


def get_location_center(gdf: gpd.GeoDataFrame) -> Tuple[float, float]:
    """
    Get the center coordinates (lat, lon) of the GeoDataFrame.

    Parameters
    ----------
    gdf : GeoDataFrame
        Street edges GeoDataFrame

    Returns
    -------
    tuple
        (latitude, longitude) in EPSG:4326
    """
    # Ensure we're in WGS84 (EPSG:4326) for lat/lon
    if gdf.crs and gdf.crs != "EPSG:4326":
        gdf_wgs84 = gdf.to_crs("EPSG:4326")
    else:
        gdf_wgs84 = gdf

    # Get centroid of all geometries
    total_bounds = gdf_wgs84.total_bounds  # (minx, miny, maxx, maxy)
    center_lon = (total_bounds[0] + total_bounds[2]) / 2
    center_lat = (total_bounds[1] + total_bounds[3]) / 2

    return center_lat, center_lon


def fetch_weather_from_open_meteo(lat: float, lon: float,
                                   fetch_dates: list,
                                   target_hours: list) -> Dict[str, float]:
    """
    Fetch historical weather data from Open-Meteo API and average across multiple dates and hours.

    This provides more robust seasonal weather by sampling multiple days within the season
    rather than relying on a single day's weather.

    Open-Meteo provides:
    - Free historical weather back to 1940
    - No API key required
    - Hourly data resolution

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees
    lon : float
        Longitude in decimal degrees
    fetch_dates : list
        List of datetime objects to fetch weather for and average
    target_hours : list
        List of hours (0-23) to fetch and average weather for

    Returns
    -------
    dict
        Averaged weather data with keys: temperature, precipitation, wind_speed

    Raises
    ------
    WeatherError
        If API request fails
    """
    all_temp_values = []
    all_precip_values = []
    all_wind_values = []

    successful_fetches = 0

    try:
        for fetch_date in fetch_dates:
            try:
                # Open-Meteo Archive API (historical data)
                url = "https://archive-api.open-meteo.com/v1/archive"

                # Format date for API (YYYY-MM-DD)
                date_str = fetch_date.strftime("%Y-%m-%d")

                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": date_str,
                    "end_date": date_str,
                    "hourly": "temperature_2m,precipitation,wind_speed_10m",
                    "timezone": "auto"
                }

                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()

                data = response.json()

                # Extract hourly data
                hourly = data.get("hourly", {})
                temperatures = hourly.get("temperature_2m", [])
                precipitations = hourly.get("precipitation", [])
                wind_speeds = hourly.get("wind_speed_10m", [])

                # Collect weather data for target hours on this date
                for hour in target_hours:
                    if hour < len(temperatures) and temperatures[hour] is not None:
                        all_temp_values.append(temperatures[hour])
                        all_precip_values.append(precipitations[hour])
                        all_wind_values.append(wind_speeds[hour])

                successful_fetches += 1

            except Exception as e:
                logging.warning(f"Failed to fetch weather for {date_str}: {e}")
                continue

        # Calculate overall averages across all dates and hours
        if all_temp_values:
            temperature = sum(all_temp_values) / len(all_temp_values)
            precipitation = sum(all_precip_values) / len(all_precip_values)
            wind_speed = sum(all_wind_values) / len(all_wind_values)

            logging.info(f"Seasonal weather averaged from {successful_fetches} dates, {len(all_temp_values)} total samples: "
                        f"temp={temperature:.1f}°C, precip={precipitation:.1f}mm, wind={wind_speed:.1f}km/h")

            return {
                "temperature": temperature,
                "precipitation": precipitation,
                "wind_speed": wind_speed
            }
        else:
            raise WeatherError("No successful weather data fetched from any date")

    except WeatherError:
        raise
    except Exception as e:
        logging.warning(f"Open-Meteo API request failed: {e}. Using seasonal defaults.")
        raise WeatherError(f"Weather API failed: {e}")


def get_seasonal_defaults(timestamp: datetime) -> Dict[str, float]:
    """
    Get seasonal default weather values based on the month.

    These are conservative averages for when API is unavailable.

    Parameters
    ----------
    timestamp : datetime
        Timestamp to determine season for

    Returns
    -------
    dict
        Default weather data
    """
    month = timestamp.month

    # Seasonal defaults (Northern Hemisphere averages)
    if month in [12, 1, 2]:  # Winter
        return {
            "temperature": 8.0,      # 8°C (cold but not extreme)
            "precipitation": 2.0,    # 2mm (some rain/snow)
            "wind_speed": 15.0       # 15 km/h (breezy)
        }
    elif month in [3, 4, 5]:  # Spring
        return {
            "temperature": 15.0,     # 15°C (mild)
            "precipitation": 1.5,    # 1.5mm (occasional rain)
            "wind_speed": 12.0       # 12 km/h (moderate breeze)
        }
    elif month in [6, 7, 8]:  # Summer
        return {
            "temperature": 25.0,     # 25°C (warm)
            "precipitation": 0.5,    # 0.5mm (light/rare rain)
            "wind_speed": 10.0       # 10 km/h (light breeze)
        }
    else:  # Fall (9, 10, 11)
        return {
            "temperature": 16.0,     # 16°C (cool)
            "precipitation": 1.8,    # 1.8mm (moderate rain)
            "wind_speed": 13.0       # 13 km/h (moderate breeze)
        }


def compute_weather_features(gdf: gpd.GeoDataFrame,
                            timestamp: Optional[datetime] = None,
                            time_of_day: Optional[str] = None) -> gpd.GeoDataFrame:
    """
    Add weather features to street edges using seasonal averaging.

    Weather Strategy:
    - Fetches weather from multiple representative dates within the target season
    - Averages across 5 different days spanning the entire season (early, mid, late)
    - Averages weather across representative hours for the specified time_of_day
    - Provides more robust seasonal representation than single-day sampling

    Uses Open-Meteo API (free, no key required, historical data back to 1940).
    Falls back to seasonal defaults if API is unavailable.

    Parameters
    ----------
    gdf : GeoDataFrame
        Street edges to which weather features will be added
    timestamp : datetime, optional
        Timestamp for prediction. Defaults to now.
    time_of_day : str, optional
        Time of day: 'morning', 'afternoon', 'evening', 'night'
        If provided, weather is averaged across representative hours.

    Returns
    -------
    GeoDataFrame
        The same GeoDataFrame with new columns:
          - temperature: float (°C)
          - precipitation: float (mm)
          - wind_speed: float (km/h)

    Raises
    ------
    WeatherError
        If feature computation fails critically (non-critical errors use defaults)
    """
    try:
        gdf = gdf.copy()

        # Default timestamp to now if not provided
        if timestamp is None:
            timestamp = datetime.now()
        elif isinstance(timestamp, str):
            timestamp = pd.to_datetime(timestamp)

        # Get location center
        lat, lon = get_location_center(gdf)

        # Get multiple sample dates from the target season for averaging
        fetch_dates = get_seasonal_sample_dates(timestamp, n_samples=5)
        target_season = get_season(timestamp)

        # Get hours to average based on time_of_day
        if time_of_day:
            target_hours = get_time_of_day_hours(time_of_day)
            logging.info(f"Fetching {target_season} weather averaged from {len(fetch_dates)} dates, "
                        f"time of day: {time_of_day} (hours: {target_hours})")
        else:
            target_hours = [timestamp.hour]
            logging.info(f"Fetching {target_season} weather averaged from {len(fetch_dates)} dates")

        # Fetch weather from Open-Meteo (multi-date averaging)
        try:
            weather_data = fetch_weather_from_open_meteo(
                lat, lon, fetch_dates, target_hours
            )
        except WeatherError:
            # Fallback to seasonal defaults
            logging.warning(f"Using seasonal defaults for {target_season}")
            weather_data = get_seasonal_defaults(timestamp)

        # Add weather features to all edges
        gdf["temperature"] = weather_data["temperature"]
        gdf["precipitation"] = weather_data["precipitation"]
        gdf["wind_speed"] = weather_data["wind_speed"]

        return gdf

    except Exception as e:
        # Critical error: use seasonal defaults
        logging.error(f"Weather feature extraction failed: {e}. Using seasonal defaults.")
        gdf = gdf.copy()
        if timestamp is None:
            timestamp = datetime.now()
        defaults = get_seasonal_defaults(timestamp)
        gdf["temperature"] = defaults["temperature"]
        gdf["precipitation"] = defaults["precipitation"]
        gdf["wind_speed"] = defaults["wind_speed"]
        return gdf


if __name__ == "__main__":
    # Quick smoke test
    import geopandas as gpd
    from shapely.geometry import LineString

    # Test GeoDataFrame (Monaco-ish location)
    test_gdf = gpd.GeoDataFrame({
        'geometry': [LineString([(7.42, 43.73), (7.43, 43.74)])],
        'highway': ['primary']
    }, crs="EPSG:4326")

    # Test 1: Winter season (should average from 5 winter dates)
    print("\n=== Test 1: Winter Season ===")
    result1 = compute_weather_features(test_gdf, datetime(2025, 1, 15, 9, 0, 0), time_of_day='morning')
    print(f"Temperature: {result1['temperature'].iloc[0]:.1f}°C")
    print(f"Precipitation: {result1['precipitation'].iloc[0]:.1f}mm")
    print(f"Wind Speed: {result1['wind_speed'].iloc[0]:.1f}km/h")

    # Test 2: Summer season (should average from 5 summer dates)
    print("\n=== Test 2: Summer Season ===")
    test_date = datetime(2025, 7, 15, 14, 0, 0)
    result2 = compute_weather_features(test_gdf, test_date, time_of_day='afternoon')
    print(f"Temperature: {result2['temperature'].iloc[0]:.1f}°C")
    print(f"Precipitation: {result2['precipitation'].iloc[0]:.1f}mm")
    print(f"Wind Speed: {result2['wind_speed'].iloc[0]:.1f}km/h")

    # Test 3: Autumn season
    print("\n=== Test 3: Autumn Season ===")
    result3 = compute_weather_features(test_gdf, datetime(2025, 10, 15, 19, 0, 0), time_of_day='evening')
    print(f"Temperature: {result3['temperature'].iloc[0]:.1f}°C")
    print(f"Precipitation: {result3['precipitation'].iloc[0]:.1f}mm")
    print(f"Wind Speed: {result3['wind_speed'].iloc[0]:.1f}km/h")
