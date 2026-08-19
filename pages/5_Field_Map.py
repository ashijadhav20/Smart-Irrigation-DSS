import folium
import streamlit as st
from streamlit_folium import st_folium
from core.ui import inject_css, hero, require_inputs
from core.map_tools import satellite_map

st.set_page_config(page_title="Satellite Field Map | Irrigation DSS",page_icon="🛰️",layout="wide")
inject_css(); hero("Page 6 • Satellite field map with the saved actual boundary")
require_inputs()
lat=float(st.session_state.latitude); lon=float(st.session_state.longitude)
area=float(st.session_state.area_m2); boundary=st.session_state.get("field_geometry")

if not boundary:
    st.error("No saved field boundary. Return to Page 1 and draw/upload the field polygon."); st.stop()

m=satellite_map(lat,lon,zoom=18,boundary=boundary,editable=False)
folium.Marker([lat,lon],tooltip="Field boundary centre",popup=f"Crop: {st.session_state.crop}<br>Area: {area:,.1f} m²").add_to(m)
gee=st.session_state.get("gee_result")
if gee:
    folium.GeoJson(boundary,tooltip=f"NDVI {gee['ndvi']:.3f} • Sentinel-2 {gee['acquisition_date']}").add_to(m)
st_folium(m,width=None,height=620,key="satellite_boundary_view")

c1,c2,c3=st.columns(3)
c1.metric("Saved field area",f"{area:,.1f} m²")
c2.metric("Area",f"{area/10000:.4f} ha")
c3.metric("Boundary vertices",max(0,len(boundary['coordinates'][0])-1))
if gee:
    st.success(f"Sentinel-2 NDVI {gee['ndvi']:.3f} from {gee['acquisition_date']} was calculated over: {gee.get('footprint_method','field region')}.")
st.info("To alter the geometry, return to Page 1. Regular fields can be regenerated from dimensions; irregular fields can be redrawn/uploaded. The saved polygon is also used for NDVI clipping.")
