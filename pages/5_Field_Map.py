import math

import folium
import streamlit as st
from streamlit_folium import st_folium

from core.ui import inject_css, hero, require_inputs

st.set_page_config(
    page_title="Field Map | Irrigation DSS",
    page_icon="🗺️",
    layout="wide",
)

inject_css()
hero("Page 6 • Field location, footprint and satellite-status map")
require_inputs()

lat = st.session_state.latitude
lon = st.session_state.longitude
area = float(st.session_state.area_m2)

radius = max(5.0, math.sqrt(area / math.pi))

m = folium.Map(
    location=[lat, lon],
    zoom_start=16,
    control_scale=True,
)

folium.Marker(
    [lat, lon],
    tooltip="Selected field centre",
    popup=(
        f"Crop: {st.session_state.crop}<br>"
        f"Soil: {st.session_state.soil_type}<br>"
        f"Area: {area:,.0f} m²"
    ),
    icon=folium.Icon(icon="leaf", prefix="fa"),
).add_to(m)

gee_result = st.session_state.get("gee_result")
ndvi_text = "NDVI not fetched"

if gee_result:
    ndvi_text = (
        f"Sentinel-2 NDVI: {gee_result['ndvi']:.3f}<br>"
        f"Satellite date: {gee_result['acquisition_date']}<br>"
        f"Clear field pixels: {gee_result['clear_fraction'] * 100:.0f}%"
    )

folium.Circle(
    [lat, lon],
    radius=radius,
    tooltip=(
        f"Equivalent-area field footprint • "
        f"{area:,.0f} m²"
    ),
    popup=ndvi_text,
    fill=True,
    fill_opacity=0.16,
).add_to(m)

st_folium(
    m,
    width=None,
    height=580,
)

if gee_result:
    st.success(
        f"Latest dashboard Sentinel-2 result: NDVI {gee_result['ndvi']:.3f} "
        f"from {gee_result['acquisition_date']}."
    )
else:
    st.info(
        "No Sentinel-2 NDVI result is stored yet. Open **Crop ET** and fetch "
        "automatic NDVI first."
    )

st.caption(
    "This page deliberately does not request Earth Engine map tiles. "
    "It displays the field location and the numerical Sentinel-2 NDVI already "
    "calculated on the Crop ET page, avoiding the unnecessary "
    "`earthengine.maps.create` permission."
)
