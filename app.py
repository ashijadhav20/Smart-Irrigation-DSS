import streamlit as st
from datetime import date, timedelta
from core.ui import inject_css, hero
from core.data import CROPS, SOILS
from core.geometry import area_from_shape
from core.soil_lookup import fetch_soil_texture

st.set_page_config(page_title="Smart Irrigation DSS", page_icon="🌱", layout="wide")
inject_css()
hero("Page 1 • Location, crop, soil and field input")

st.markdown("### 📍 Field and crop configuration")

c1, c2 = st.columns(2)
with c1:
    latitude = st.number_input("Latitude", value=float(st.session_state.get("latitude", 20.2961)), format="%.6f")
    longitude = st.number_input("Longitude", value=float(st.session_state.get("longitude", 85.8245)), format="%.6f")
    crop = st.selectbox(
        "Crop",
        list(CROPS.keys()),
        index=list(CROPS.keys()).index(st.session_state.get("crop","Rice"))
        if st.session_state.get("crop","Rice") in CROPS else 0
    )

    st.markdown("#### 🌍 Soil type")
    soil_mode = st.radio(
        "Soil selection method",
        ["Automatic from coordinates", "Choose manually"],
        index=0 if st.session_state.get("soil_mode","Automatic from coordinates") == "Automatic from coordinates" else 1,
        horizontal=True,
    )

    detected = st.session_state.get("detected_soil_data")

    if soil_mode == "Automatic from coordinates":
        st.caption("Automatic soil texture first checks a persistent local cache. Only new locations contact SoilGrids; repeated locations are normally returned immediately.")
        if st.button("🔎 Detect soil type from coordinates", use_container_width=True):
            try:
                with st.spinner("Checking saved soil data / contacting SoilGrids (maximum about 8 s for a network attempt)..."):
                    detected = fetch_soil_texture(latitude, longitude, depth="0-5cm")
                st.session_state["detected_soil_data"] = detected
                st.session_state["soil_detect_lat"] = latitude
                st.session_state["soil_detect_lon"] = longitude
                st.session_state["soil_type"] = detected["soil_type"]
                st.success(f"Detected soil type: {detected['soil_type']}")
            except Exception as e:
                st.warning("Automatic soil detection was unavailable or too slow. Choose the soil type manually and continue; the rest of the DSS is not blocked.")
                st.code(str(e))

        detected = st.session_state.get("detected_soil_data")
        if detected:
            st.info(
                f"Estimated soil texture: **{detected['soil_type']}**  |  "
                f"Sand {detected['sand_pct']:.1f}% • "
                f"Silt {detected['silt_pct']:.1f}% • "
                f"Clay {detected['clay_pct']:.1f}%"
            )
            source_mode = detected.get("source_mode", "")
            if source_mode == "persistent_cache":
                st.caption("⚡ Soil result loaded from the saved local cache.")
            elif source_mode == "live_soilgrids":
                st.caption("🌐 Soil result fetched from SoilGrids and saved for later reuse.")
            elif source_mode == "nearby_soilgrids":
                st.caption("🌐 Soil result obtained from one nearby SoilGrids point and saved.")

            if detected.get("nearby_fallback_used"):
                st.warning(
                    "The exact coordinate did not return a usable SoilGrids texture, so one nearby "
                    "grid-scale point was used. Verify with a local soil map or field/laboratory "
                    "texture data when higher local accuracy is required."
                )
            soil = detected["soil_type"]
            st.selectbox(
                "Automatically selected soil type",
                list(SOILS.keys()),
                index=list(SOILS.keys()).index(soil),
                disabled=True,
            )
        else:
            soil = st.session_state.get("soil_type", "Loam")
            st.selectbox(
                "Soil type (detect first)",
                list(SOILS.keys()),
                index=list(SOILS.keys()).index(soil) if soil in SOILS else 3,
                disabled=True,
            )
            st.caption("Press **Detect soil type from coordinates** after entering latitude and longitude.")
    else:
        soil = st.selectbox(
            "Choose soil type",
            list(SOILS.keys()),
            index=list(SOILS.keys()).index(st.session_state.get("soil_type","Loam"))
            if st.session_state.get("soil_type","Loam") in SOILS else 3
        )

with c2:
    sowing_date = st.date_input("Sowing date", value=st.session_state.get("sowing_date", date.today()-timedelta(days=35)))
    evaluation_date = st.date_input("Evaluation date", value=st.session_state.get("evaluation_date", date.today()))
    shape = st.selectbox("Field shape", ["Rectangle","Square","Circle","Triangle","Trapezoid"])

    if shape == "Rectangle":
        a, b = st.columns(2)
        length = a.number_input("Length (m)", min_value=0.1, value=100.0)
        width = b.number_input("Width (m)", min_value=0.1, value=50.0)
        area_m2 = area_from_shape(shape, length=length, width=width)
    elif shape == "Square":
        side = st.number_input("Side (m)", min_value=0.1, value=50.0)
        area_m2 = area_from_shape(shape, side=side)
    elif shape == "Circle":
        radius = st.number_input("Radius (m)", min_value=0.1, value=25.0)
        area_m2 = area_from_shape(shape, radius=radius)
    elif shape == "Triangle":
        a, b = st.columns(2)
        base = a.number_input("Base (m)", min_value=0.1, value=50.0)
        height = b.number_input("Height (m)", min_value=0.1, value=40.0)
        area_m2 = area_from_shape(shape, base=base, height=height)
    else:
        a, b, c = st.columns(3)
        side_a = a.number_input("Parallel side A (m)", min_value=0.1, value=40.0)
        side_b = b.number_input("Parallel side B (m)", min_value=0.1, value=60.0)
        height = c.number_input("Height (m)", min_value=0.1, value=30.0)
        area_m2 = area_from_shape(shape, a=side_a, b=side_b, height=height)

st.metric("Calculated field area", f"{area_m2:,.1f} m²", f"{area_m2/10000:.3f} ha")

st.markdown("### ⚙️ Irrigation settings")
d1, d2, d3 = st.columns(3)
with d1:
    efficiency = st.slider("Application efficiency (%)", 40, 100, int(st.session_state.get("efficiency_pct", 80)))
with d2:
    rain_eff = st.slider("Effective rainfall fraction (%)", 30, 100, int(st.session_state.get("rain_eff_pct", 80)))
with d3:
    forecast_days = st.slider("Forecast horizon (days)", 3, 14, int(st.session_state.get("forecast_days", 7)))

if soil_mode == "Automatic from coordinates" and st.session_state.get("detected_soil_data"):
    if (
        abs(latitude - st.session_state.get("soil_detect_lat", latitude)) > 1e-9
        or abs(longitude - st.session_state.get("soil_detect_lon", longitude)) > 1e-9
    ):
        st.warning("Coordinates have changed since the last soil lookup. Press **Detect soil type from coordinates** again before saving.")

if evaluation_date < sowing_date:
    st.error("Evaluation date cannot be earlier than sowing date.")
    st.stop()

if st.button("✅ Save field inputs", type="primary", use_container_width=True):
    if soil_mode == "Automatic from coordinates":
        detected_now = st.session_state.get("detected_soil_data")
        stale = (
            detected_now is None
            or abs(latitude - st.session_state.get("soil_detect_lat", latitude + 1)) > 1e-9
            or abs(longitude - st.session_state.get("soil_detect_lon", longitude + 1)) > 1e-9
        )
        if stale:
            st.error("Please detect the soil type for the current coordinates first, or select **Choose manually**.")
            st.stop()

    st.session_state.update({
        "latitude": latitude,
        "longitude": longitude,
        "crop": crop,
        "soil_type": soil,
        "soil_mode": soil_mode,
        "sowing_date": sowing_date,
        "evaluation_date": evaluation_date,
        "field_shape": shape,
        "area_m2": area_m2,
        "efficiency_pct": efficiency,
        "rain_eff_pct": rain_eff,
        "forecast_days": forecast_days,
    })
    st.success("Inputs saved. Open the Weather page from the sidebar.")

st.caption("Data note: soil texture and soil moisture obtained from external geospatial/model services are estimates; manual field values remain available where local observations are preferred.")
