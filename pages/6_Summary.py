import streamlit as st
from core.ui import inject_css, hero, require_inputs

st.set_page_config(page_title="Summary | Irrigation DSS", page_icon="📋", layout="wide")
inject_css(); hero("Page 7 • Decision summary")
require_inputs()

stage = st.session_state.get("stage","Not calculated")
kc = st.session_state.get("kc_adj",0.0)
ndvi = st.session_state.get("ndvi",None)
theta = st.session_state.get("soil_theta",None)
metrics = st.session_state.get("soil_metrics",{})
litres = st.session_state.get("recommended_water_l",0.0)

c1,c2,c3 = st.columns(3)
c1.metric("Crop", st.session_state.crop)
c2.metric("Growth stage", stage)
c3.metric("Field area", f"{st.session_state.area_m2:,.0f} m²")

c4,c5,c6 = st.columns(3)
c4.metric("Adjusted Kc", f"{kc:.3f}")
c5.metric("NDVI", "—" if ndvi is None else f"{ndvi:.3f}")
c6.metric("Root-zone soil moisture", "—" if theta is None else f"{theta*100:.1f}%", "—" if theta is None else f"{theta:.3f} m³/m³")

st.markdown("### 🌱 Irrigation decision")
status = metrics.get("status","Complete the Soil Moisture page")
if litres > 0:
    st.error(f"Recommended water application: approximately **{litres:,.0f} litres**.")
else:
    st.success(f"Current soil-water status: **{status}**. No irrigation volume is presently triggered.")

st.markdown("""
#### Method chain
Coordinates → weather → FAO ET₀ → crop growth-stage Kc → optional NDVI correction → ETc →
root-zone soil moisture → TAW/RAW depletion logic → forecast soil-water balance → irrigation depth → litres.

**Research caution:** model-estimated soil moisture, crop coefficients and NDVI correction require local field validation before operational recommendations or publication.
""")


st.markdown("### 🧭 Field and soil provenance")
st.write(f"**Geometry:** {st.session_state.get('field_geometry_mode','Saved field geometry')} — {st.session_state.get('field_shape','Field polygon')}")
st.write(f"**Soil definition:** {st.session_state.get('soil_mode','Selected soil type')} — **{st.session_state.get('soil_type','')}**")
if all(k in st.session_state for k in ['sand_pct','silt_pct','clay_pct']):
    st.write(f"**Texture composition:** sand {st.session_state.sand_pct:.1f}% • silt {st.session_state.silt_pct:.1f}% • clay {st.session_state.clay_pct:.1f}%")
st.caption(f"Soil source: {st.session_state.get('soil_source','Not recorded')}")
