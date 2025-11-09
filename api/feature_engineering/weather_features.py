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
        Season name: 'winter', 'spring', 'summer', 'fall'
    """
    month = date.month
    if month in [12, 1, 2]:
        return 'winter'
    elif month in [3, 4, 5]:
        return 'spring'
    elif month in [6, 7, 8]:
        return 'summer'
    else:  # 9, 10, 11
        return 'fall'


def get_weather_fetch_date(target_timestamp: datetime) -> Tuple[datetime, str]:
    """
    Determine which date to fetch weather for based on season logic.

    Logic:
    - If target is in current season → Use last week (7 days ago)
    - If target is in different season → Use same date from last occurrence of that season

    Parameters
    ----------
    target_timestamp : datetime
        The timestamp user is requesting prediction for

    Returns
    -------
    tuple
        (fetch_date, reason) - Date to fetch weather for and explanation
    """
    now = datetime.now()
    target_season = get_season(target_timestamp)
    current_season = get_season(now)

    if target_season == current_season:
        # Same season: use last week's weather
        fetch_date = now - timedelta(days=7)
        reason = f"current_{current_season}"
        logging.info(f"Same season ({current_season}): fetching weather from 7 days ago")
    else:
        # Different season: use last occurrence of that season
        # Go back to same month/day in previous year(s) until we find that season
        year_offset = 0
        while True:
            candidate = target_timestamp.replace(year=now.year - year_offset)
            if candidate > now:
                # Future date, go back one more year
                year_offset += 1
                continue
            if get_season(candidate) == target_season:
                fetch_date = candidate
                reason = f"last_{target_season}"
                logging.info(f"Different season: fetching {target_season} weather from {fetch_date.date()}")
                break
            year_offset += 1
            if year_offset > 5:
                # Safety: fallback to 1 year ago if something goes wrong
                fetch_date = target_timestamp.replace(year=now.year - 1)
                reason = "fallback"
                break

    return fetch_date, reason


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
                                   fetch_date: datetime,
                                   target_hours: list) -> Dict[str, float]:
    """
    Fetch historical weather data from Open-Meteo API and average across multiple hours.

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
    fetch_date : datetime
        Date to fetch weather for
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
        times = hourly.get("time", [])
        temperatures = hourly.get("temperature_2m", [])
        precipitations = hourly.get("precipitation", [])
        wind_speeds = hourly.get("wind_speed_10m", [])

        # Collect weather data for target hours
        temp_values = []
        precip_values = []
        wind_values = []

        for hour in target_hours:
            if hour < len(temperatures):
                temp_values.append(temperatures[hour])
                precip_values.append(precipitations[hour])
                wind_values.append(wind_speeds[hour])

        # Calculate averages
        temperature = sum(temp_values) / len(temp_values) if temp_values else 20.0
        precipitation = sum(precip_values) / len(precip_values) if precip_values else 0.0
        wind_speed = sum(wind_values) / len(wind_values) if wind_values else 10.0

        logging.info(f"Open-Meteo weather fetched for {date_str} at hours {target_hours}: "
                    f"temp={temperature:.1f}°C, precip={precipitation:.1f}mm, wind={wind_speed:.1f}km/h (averaged)")

        return {
            "temperature": temperature,
            "precipitation": precipitation,
            "wind_speed": wind_speed
        }

    except requests.exceptions.RequestException as e:
        logging.warning(f"Open-Meteo API request failed: {e}. Using seasonal defaults.")
        raise WeatherError(f"Weather API failed: {e}")
    except (KeyError, ValueError, IndexError) as e:
        logging.warning(f"Failed to parse Open-Meteo data: {e}. Using seasonal defaults.")
        raise WeatherError(f"Weather parsing failed: {e}")


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
    Add weather features to street edges using smart seasonal fetching.

    Weather Strategy:
    - Same season as now → Use last week's weather (most recent)
    - Different season → Use last occurrence of that season
    - Averages weather across representative hours for the specified time_of_day

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

        # Determine which date to fetch weather for
        fetch_date, reason = get_weather_fetch_date(timestamp)

        # Get hours to average based on time_of_day
        if time_of_day:
            target_hours = get_time_of_day_hours(time_of_day)
            logging.info(f"Weather strategy: {reason} | Target: {timestamp.date()}, Fetch: {fetch_date.date()}, "
                        f"Time of day: {time_of_day} (hours: {target_hours})")
        else:
            target_hours = [timestamp.hour]
            logging.info(f"Weather strategy: {reason} | Target: {timestamp.date()}, Fetch: {fetch_date.date()}")

        # Fetch weather from Open-Meteo
        try:
            weather_data = fetch_weather_from_open_meteo(
                lat, lon, fetch_date, target_hours
            )
        except WeatherError:
            # Fallback to seasonal defaults
            logging.warning(f"Using seasonal defaults for {get_season(timestamp)}")
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

    # Test 1: Current season (should use last week)
    print("\n=== Test 1: Current Season ===")
    result1 = compute_weather_features(test_gdf, datetime.now())
    print(f"Temperature: {result1['temperature'].iloc[0]}°C")
    print(f"Precipitation: {result1['precipitation'].iloc[0]}mm")
    print(f"Wind Speed: {result1['wind_speed'].iloc[0]}km/h")

    # Test 2: Different season (should use last summer if winter, etc.)
    print("\n=== Test 2: Different Season ===")
    # If it's November, request July weather
    test_date = datetime(2025, 7, 15, 14, 0, 0)
    result2 = compute_weather_features(test_gdf, test_date)
    print(f"Temperature: {result2['temperature'].iloc[0]}°C")
    print(f"Precipitation: {result2['precipitation'].iloc[0]}mm")
    print(f"Wind Speed: {result2['wind_speed'].iloc[0]}km/h")
