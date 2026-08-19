import numpy as np
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from core.ui import inject_css, hero, require_inputs
from core.map_tools import satellite_map
from core.terrain import terrain_grid_for_boundary, boundary_elevations

st.set_page_config(page_title="3D Terrain | Irrigation DSS", page_icon="🏔️", layout="wide")
inject_css(); hero("Final Page • 3D terrain context and satellite field boundary")
require_inputs()

boundary=st.session_state.get("field_geometry")
if not boundary:
    st.error("No saved field geometry. Return to Page 1 and define the field first.")
    st.stop()

lat=float(st.session_state.latitude); lon=float(st.session_state.longitude)
area=float(st.session_state.area_m2)

st.info(
    "This page separates two useful views: the **actual field boundary on satellite imagery** "
    "and a **3D terrain/elevation view** of the same location. Elevation is sampled from the "
    "Open-Meteo Elevation API; it is terrain context, not a cadastral or precision-survey DEM."
)

left,right=st.columns([1.05,0.95])
with left:
    st.markdown("### 🛰️ Satellite map — saved field boundary")
    m=satellite_map(lat,lon,zoom=18,boundary=boundary,editable=False)
    st_folium(m,width=None,height=560,key="final_satellite_boundary")
with right:
    st.markdown("### 📋 Field geometry summary")
    st.metric("Field area",f"{area:,.1f} m²",f"{area/10000:.4f} ha")
    st.metric("Geometry mode",st.session_state.get("field_geometry_mode","Saved polygon"))
    st.metric("Shape",st.session_state.get("field_shape","Irregular polygon"))
    st.caption(f"Field query centre: {lat:.6f}, {lon:.6f}")
    st.caption("The green polygon shown on the satellite map is the same saved geometry used for NDVI clipping.")

st.markdown("### 🏔️ 3D terrain view around the field")
quality=st.select_slider("Terrain sampling density",options=[5,7,9,10],value=9,help="Higher values use more elevation sample points; 9×9 is a good balance.")

try:
    with st.spinner("Fetching terrain elevations for the field surroundings..."):
        lat_axis,lon_axis,z=terrain_grid_for_boundary(boundary,n=quality,padding_fraction=0.45)
        bdf=boundary_elevations(boundary)

    lon_grid,lat_grid=np.meshgrid(lon_axis,lat_axis)
    fig=go.Figure()
    fig.add_trace(go.Surface(
        x=lon_grid,
        y=lat_grid,
        z=z,
        colorscale="Earth",
        opacity=0.92,
        colorbar=dict(title="Elevation (m)"),
        name="Terrain elevation",
        showscale=True,
    ))
    if not bdf.empty:
        # Lift the line slightly so it stays visible over the surface.
        lift=max(float(np.nanmax(z)-np.nanmin(z))*0.02,1.0)
        fig.add_trace(go.Scatter3d(
            x=bdf["lon"],y=bdf["lat"],z=bdf["elevation"]+lift,
            mode="lines+markers",
            line=dict(width=8),
            marker=dict(size=3),
            name="Saved field boundary",
            hovertemplate="Lon %{x:.6f}<br>Lat %{y:.6f}<br>Elevation %{z:.1f} m<extra></extra>",
        ))
    fig.update_layout(
        height=680,
        margin=dict(l=0,r=0,t=45,b=0),
        title="3D terrain surrounding the saved field",
        scene=dict(
            xaxis_title="Longitude",
            yaxis_title="Latitude",
            zaxis_title="Elevation (m)",
            aspectmode="data",
        ),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig,use_container_width=True)
    zmin=float(np.nanmin(z)); zmax=float(np.nanmax(z))
    c1,c2,c3=st.columns(3)
    c1.metric("Minimum sampled elevation",f"{zmin:.1f} m")
    c2.metric("Maximum sampled elevation",f"{zmax:.1f} m")
    c3.metric("Local relief in view",f"{zmax-zmin:.1f} m")
    st.caption(
        "3D elevation is intended to show topographic context and relative relief. For engineering-grade slope, drainage design, land levelling or cadastral work, use a surveyed DEM/RTK-GNSS/total-station dataset."
    )
except Exception as exc:
    st.error(f"3D terrain data could not be loaded: {exc}")
    st.info("The satellite boundary map above remains available even if the elevation service is temporarily unavailable.")
