import streamlit as st
import plotly.express as px

from core.ui import inject_css, hero, require_inputs
from core.weather import fetch_openweather

st.set_page_config(page_title="Weather | Irrigation DSS", page_icon="☀️", layout="wide")

inject_css()
hero("Page 2 • OpenWeather current conditions + 5-day / 3-hour forecast + FAO-56 ET₀")
require_inputs()

lat = st.session_state.latitude
lon = st.session_state.longitude
days = min(st.session_state.get("forecast_days", 5), 5)

try:
    daily, hourly, raw_bundle = fetch_openweather(lat, lon, days)
    st.session_state["weather_daily"] = daily
    st.session_state["weather_hourly"] = hourly
    st.session_state["weather_current"] = raw_bundle["current_summary"]
except Exception as e:
    st.error(f"OpenWeather could not be reached: {e}")
    st.info(
        'Check `.streamlit/secrets.toml` and make sure it contains:\n\n'
        '`OPENWEATHER_API_KEY = "YOUR_ACTUAL_KEY"`'
    )
    st.stop()

current = st.session_state["weather_current"]

st.markdown("### 🌤️ Current weather")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Temperature", f"{current['temperature_c']:.1f} °C")
m2.metric("Humidity", f"{current['humidity_pct']:.0f}%")
m3.metric("Wind speed", f"{current['wind_speed_ms']:.1f} m/s")
m4.metric("Pressure", f"{current['pressure_hpa']:.0f} hPa")

m5, m6, m7 = st.columns(3)
m5.metric("Cloud cover", f"{current['cloud_pct']:.0f}%")
m6.metric("Rain in last 1 h", f"{current['rain_1h_mm']:.1f} mm")
m7.metric("Condition", current["description"].title() if current["description"] else "—")

st.markdown("### 📈 5-day forecast")

fig = px.line(
    hourly,
    x="time",
    y="temperature_2m",
    markers=True,
    labels={"temperature_2m": "Temperature (°C)", "time": "Date/time"},
    title="OpenWeather 3-hour temperature forecast",
)
st.plotly_chart(fig, use_container_width=True)

fig2 = px.bar(
    hourly,
    x="time",
    y="precipitation",
    labels={"precipitation": "Rainfall per 3-hour step (mm)", "time": "Date/time"},
    title="OpenWeather 3-hour rainfall forecast",
)
st.plotly_chart(fig2, use_container_width=True)

st.markdown("### 🌱 Daily irrigation-weather summary")

show = daily[
    [
        "time",
        "temperature_2m_max",
        "temperature_2m_min",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
        "pressure_hpa_mean",
        "wind_speed_10m_mean",
        "precipitation_sum",
        "et0_fao_evapotranspiration",
        "complete_day",
    ]
].copy()

st.dataframe(show, use_container_width=True, hide_index=True)

fig3 = px.line(
    daily,
    x="time",
    y="et0_fao_evapotranspiration",
    markers=True,
    labels={
        "et0_fao_evapotranspiration": "ET₀ (mm/day)",
        "time": "Date",
    },
    title="Calculated FAO-56 Penman-Monteith ET₀",
)
st.plotly_chart(fig3, use_container_width=True)

st.info(
    "Weather source: OpenWeather Current Weather Data + 5 Day / 3 Hour Forecast. "
    "Soil moisture is fetched separately from Open-Meteo."
)

st.caption(
    "The first and last forecast dates may contain fewer than eight 3-hour records. "
    "Those days are marked as incomplete in the table. For research-grade ET₀, locally measured "
    "solar radiation is preferable; this prototype estimates solar radiation from daily temperature range."
)
