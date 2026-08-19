from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"

SOIL_HOURLY_VARS = [
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm",
    "soil_moisture_27_to_81cm",
]


def _get_openweather_key():
    try:
        import streamlit as st
        return st.secrets["OPENWEATHER_API_KEY"]
    except Exception as exc:
        raise RuntimeError(
            "OPENWEATHER_API_KEY is missing. Add it to .streamlit/secrets.toml as "
            'OPENWEATHER_API_KEY = "your_key_here".'
        ) from exc


def _sat_vp(temp_c: float) -> float:
    return 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))


def _extraterrestrial_radiation(latitude_deg: float, day_of_year: int) -> float:
    lat = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    solar_dec = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    x = -math.tan(lat) * math.tan(solar_dec)
    x = max(-1.0, min(1.0, x))
    ws = math.acos(x)
    gsc = 0.0820
    return (24 * 60 / math.pi) * gsc * dr * (
        ws * math.sin(lat) * math.sin(solar_dec)
        + math.cos(lat) * math.cos(solar_dec) * math.sin(ws)
    )


def _estimated_solar_radiation(tmin: float, tmax: float, latitude: float, day_of_year: int) -> float:
    """
    Hargreaves radiation estimate:
      Rs = kRs * sqrt(Tmax - Tmin) * Ra

    kRs = 0.16 is used as an inland starting value.
    """
    ra = _extraterrestrial_radiation(latitude, day_of_year)
    return 0.16 * math.sqrt(max(tmax - tmin, 0.0)) * ra


def _fao56_pm_et0(
    tmean: float,
    tmin: float,
    tmax: float,
    rh_mean: float,
    wind_10m: float,
    rs: float,
    latitude: float,
    day_of_year: int,
    elevation_m: float = 0.0,
) -> float:
    """
    Daily FAO-56 Penman-Monteith ET0 (mm/day).

    Note:
    - OpenWeather standard Current + 5 day/3 hour endpoints supply weather data.
    - Daily solar radiation is estimated here using the Hargreaves radiation method.
    - Wind is converted approximately from 10 m to 2 m using the FAO-56 logarithmic relation.
    """
    es = (_sat_vp(tmax) + _sat_vp(tmin)) / 2.0
    ea = max(0.0, es * rh_mean / 100.0)

    delta = 4098 * _sat_vp(tmean) / ((tmean + 237.3) ** 2)
    pressure = 101.3 * (((293 - 0.0065 * elevation_m) / 293) ** 5.26)
    gamma = 0.000665 * pressure

    u2 = wind_10m * 4.87 / math.log(67.8 * 10 - 5.42)

    ra = _extraterrestrial_radiation(latitude, day_of_year)
    rso = (0.75 + 2e-5 * elevation_m) * ra
    rns = (1 - 0.23) * rs

    sigma = 4.903e-9
    tmax_k = tmax + 273.16
    tmin_k = tmin + 273.16
    rs_rso = min(max(rs / max(rso, 1e-6), 0.05), 1.0)
    cloud_factor = max(0.05, 1.35 * rs_rso - 0.35)
    rnl = sigma * ((tmax_k**4 + tmin_k**4) / 2) * (
        0.34 - 0.14 * math.sqrt(max(ea, 0))
    ) * cloud_factor

    rn = max(0.0, rns - rnl)
    g = 0.0

    numerator = (
        0.408 * delta * (rn - g)
        + gamma * (900 / (tmean + 273)) * u2 * (es - ea)
    )
    denominator = delta + gamma * (1 + 0.34 * u2)

    return max(0.0, numerator / max(denominator, 1e-9))


def fetch_openweather_current(latitude: float, longitude: float):
    api_key = _get_openweather_key()

    params = {
        "lat": float(latitude),
        "lon": float(longitude),
        "appid": api_key,
        "units": "metric",
    }

    r = requests.get(OPENWEATHER_CURRENT_URL, params=params, timeout=25)

    if r.status_code == 401:
        raise RuntimeError("OpenWeather rejected the API key (401).")
    if r.status_code == 429:
        raise RuntimeError("OpenWeather request limit reached (429).")

    r.raise_for_status()
    data = r.json()

    rain_1h = float((data.get("rain") or {}).get("1h", 0.0) or 0.0)

    return {
        "temperature_c": float(data["main"]["temp"]),
        "feels_like_c": float(data["main"].get("feels_like", np.nan)),
        "humidity_pct": float(data["main"]["humidity"]),
        "pressure_hpa": float(data["main"]["pressure"]),
        "wind_speed_ms": float(data.get("wind", {}).get("speed", 0.0) or 0.0),
        "wind_deg": float(data.get("wind", {}).get("deg", np.nan)),
        "cloud_pct": float(data.get("clouds", {}).get("all", np.nan)),
        "rain_1h_mm": rain_1h,
        "description": (data.get("weather") or [{}])[0].get("description", ""),
        "raw": data,
    }


def fetch_openweather_forecast(latitude: float, longitude: float):
    """
    OpenWeather 5 day / 3 hour forecast.
    """
    api_key = _get_openweather_key()

    params = {
        "lat": float(latitude),
        "lon": float(longitude),
        "appid": api_key,
        "units": "metric",
    }

    r = requests.get(OPENWEATHER_FORECAST_URL, params=params, timeout=25)

    if r.status_code == 401:
        raise RuntimeError("OpenWeather rejected the API key (401).")
    if r.status_code == 429:
        raise RuntimeError("OpenWeather request limit reached (429).")

    r.raise_for_status()
    data = r.json()

    tz_offset = int((data.get("city") or {}).get("timezone", 0) or 0)

    rows = []
    for item in data.get("list", []):
        local_dt = datetime.fromtimestamp(item["dt"] + tz_offset, tz=timezone.utc).replace(tzinfo=None)

        rain_3h = float((item.get("rain") or {}).get("3h", 0.0) or 0.0)

        rows.append({
            "time": pd.to_datetime(local_dt),
            "temperature_2m": float(item["main"]["temp"]),
            "temperature_min": float(item["main"].get("temp_min", item["main"]["temp"])),
            "temperature_max": float(item["main"].get("temp_max", item["main"]["temp"])),
            "relative_humidity_2m": float(item["main"]["humidity"]),
            "pressure_hpa": float(item["main"]["pressure"]),
            "wind_speed_10m": float(item.get("wind", {}).get("speed", 0.0) or 0.0),
            "wind_deg": float(item.get("wind", {}).get("deg", np.nan)),
            "cloud_cover": float(item.get("clouds", {}).get("all", np.nan)),
            "precipitation": rain_3h,
            "weather_description": (item.get("weather") or [{}])[0].get("description", ""),
        })

    hourly = pd.DataFrame(rows)
    if hourly.empty:
        raise RuntimeError("OpenWeather returned no 5-day forecast data.")

    return hourly, data


def aggregate_openweather_daily(hourly: pd.DataFrame, latitude: float):
    """
    Aggregate 3-hour forecast records into daily weather values for ET0.
    Partial first/last days are retained but flagged.
    """
    h = hourly.copy()
    h["date"] = h["time"].dt.date

    rows = []
    for day, g in h.groupby("date"):
        dt = pd.Timestamp(day)
        tmin = float(g["temperature_min"].min())
        tmax = float(g["temperature_max"].max())
        tmean = float(g["temperature_2m"].mean())
        rh = float(g["relative_humidity_2m"].mean())
        wind_mean = float(g["wind_speed_10m"].mean())
        wind_max = float(g["wind_speed_10m"].max())
        rain = float(g["precipitation"].sum())
        pressure = float(g["pressure_hpa"].mean())
        cloud = float(g["cloud_cover"].mean())
        n_records = int(len(g))

        doy = dt.dayofyear
        rs = _estimated_solar_radiation(tmin, tmax, float(latitude), doy)
        et0 = _fao56_pm_et0(
            tmean=tmean,
            tmin=tmin,
            tmax=tmax,
            rh_mean=rh,
            wind_10m=wind_mean,
            rs=rs,
            latitude=float(latitude),
            day_of_year=doy,
            elevation_m=0.0,
        )

        rows.append({
            "time": dt,
            "temperature_2m_max": tmax,
            "temperature_2m_min": tmin,
            "temperature_2m_mean": tmean,
            "relative_humidity_2m_mean": rh,
            "pressure_hpa_mean": pressure,
            "precipitation_sum": rain,
            "wind_speed_10m_mean": wind_mean,
            "wind_speed_10m_max": wind_max,
            "cloud_cover_mean": cloud,
            "shortwave_radiation_sum": rs,
            "et0_fao_evapotranspiration": et0,
            "records_3h": n_records,
            "complete_day": n_records >= 8,
        })

    return pd.DataFrame(rows)


def fetch_openweather(latitude: float, longitude: float, forecast_days: int = 5):
    """
    Combined standard OpenWeather workflow:
      1) Current Weather Data API
      2) 5 Day / 3 Hour Forecast API
      3) Daily aggregation for irrigation/ET0 calculations

    Returns:
      daily, hourly, raw_bundle
    """
    current = fetch_openweather_current(latitude, longitude)
    hourly, raw_forecast = fetch_openweather_forecast(latitude, longitude)
    daily = aggregate_openweather_daily(hourly, latitude)

    if forecast_days:
        daily = daily.head(min(max(int(forecast_days), 1), 6))

    return daily, hourly, {
        "current": current["raw"],
        "forecast": raw_forecast,
        "current_summary": current,
    }


def fetch_openmeteo_soil(latitude: float, longitude: float, forecast_days: int = 7):
    """
    Soil-moisture source only: Open-Meteo.
    """
    params = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "hourly": ",".join(SOIL_HOURLY_VARS),
        "timezone": "auto",
        "forecast_days": min(max(int(forecast_days), 1), 16),
    }

    r = requests.get(OPENMETEO_URL, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()

    hourly = pd.DataFrame(data["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"])

    return hourly, data


def current_soil_moisture(hourly_soil: pd.DataFrame):
    if hourly_soil.empty:
        return {}

    row = hourly_soil.iloc[0]
    mapping = {
        "0-1 cm": "soil_moisture_0_to_1cm",
        "1-3 cm": "soil_moisture_1_to_3cm",
        "3-9 cm": "soil_moisture_3_to_9cm",
        "9-27 cm": "soil_moisture_9_to_27cm",
        "27-81 cm": "soil_moisture_27_to_81cm",
    }

    out = {}
    for label, col in mapping.items():
        if col in hourly_soil.columns and pd.notna(row.get(col)):
            out[label] = float(row[col])

    return out


def daily_root_zone_soil_moisture(hourly_soil: pd.DataFrame, root_depth_m: float):
    """
    Weighted root-zone soil moisture from Open-Meteo model layers.
    """
    layer_info = [
        ("soil_moisture_0_to_1cm", 0.00, 0.01),
        ("soil_moisture_1_to_3cm", 0.01, 0.03),
        ("soil_moisture_3_to_9cm", 0.03, 0.09),
        ("soil_moisture_9_to_27cm", 0.09, 0.27),
        ("soil_moisture_27_to_81cm", 0.27, 0.81),
    ]

    z = max(min(float(root_depth_m), 0.81), 0.01)

    h = hourly_soil.copy()
    h["date"] = h["time"].dt.date

    rows = []

    for day, g in h.groupby("date"):
        total_w = 0.0
        weighted = 0.0

        for col, top, bottom in layer_info:
            if col not in g.columns:
                continue

            overlap = max(0.0, min(z, bottom) - top)
            if overlap <= 0:
                continue

            vals = g[col].dropna()
            if vals.empty:
                continue

            weighted += float(vals.mean()) * overlap
            total_w += overlap

        rows.append({
            "date": pd.to_datetime(day),
            "root_zone_theta": weighted / total_w if total_w else np.nan,
        })

    return pd.DataFrame(rows)


SOIL_LAYER_LABELS = {
    "soil_moisture_0_to_1cm": "0–1 cm",
    "soil_moisture_1_to_3cm": "1–3 cm",
    "soil_moisture_3_to_9cm": "3–9 cm",
    "soil_moisture_9_to_27cm": "9–27 cm",
    "soil_moisture_27_to_81cm": "27–81 cm",
}


def daily_soil_moisture_by_depth(hourly_soil: pd.DataFrame):
    """
    Daily mean Open-Meteo soil moisture for each model layer.

    Returns columns:
      date, 0–1 cm, 1–3 cm, 3–9 cm, 9–27 cm, 27–81 cm
    """
    if hourly_soil is None or hourly_soil.empty:
        return pd.DataFrame()

    h = hourly_soil.copy()
    h["date"] = h["time"].dt.date

    available = [
        col for col in SOIL_LAYER_LABELS
        if col in h.columns
    ]

    if not available:
        return pd.DataFrame()

    daily = (
        h.groupby("date")[available]
        .mean()
        .reset_index()
    )

    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.rename(columns=SOIL_LAYER_LABELS)
    return daily


def soil_moisture_depletion_rate_by_depth(daily_depth: pd.DataFrame):
    """
    Day-to-day soil-moisture change by depth.

    Positive value = depletion/drying from previous day.
    Negative value = wetting/recharge from previous day.

    Unit: m³/m³ per day.
    """
    if daily_depth is None or daily_depth.empty:
        return pd.DataFrame()

    out = daily_depth.copy()
    depth_cols = [c for c in out.columns if c != "date"]

    for col in depth_cols:
        out[col] = -out[col].diff()

    return out


def volumetric_to_percent(theta):
    """
    Convert volumetric soil moisture from m³/m³ to volumetric percent.

    Example:
        0.25 m³/m³ = 25% volumetric soil moisture.
    """
    if theta is None:
        return None
    return float(theta) * 100.0


def add_percent_columns(daily_depth: pd.DataFrame):
    """
    Return a copy of a depth-wise soil-moisture table with percentage values.
    """
    if daily_depth is None or daily_depth.empty:
        return pd.DataFrame()

    out = daily_depth.copy()
    for col in [c for c in out.columns if c != "date"]:
        out[col] = out[col].astype(float) * 100.0
    return out
