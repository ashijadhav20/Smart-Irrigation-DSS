from __future__ import annotations

import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from core.ui import inject_css, hero, require_inputs
from core.map_tools import water_resources_map
from core.water_resources import detect_nearby_water_bodies
from core.terrain import terrain_grid_for_radius, boundary_elevations, water_centroid_elevations

st.set_page_config(page_title="Nearby Water Resources | Irrigation DSS", page_icon="💧", layout="wide")
inject_css(); hero("Nearby water resources • Sentinel-2 NDWI/MNDWI • storage scenario • 3D terrain context")
require_inputs()

field_boundary = st.session_state.get("field_geometry")
if not field_boundary:
    st.error("No saved field geometry. Return to Field Input and define/save the field first.")
    st.stop()

lat=float(st.session_state.latitude); lon=float(st.session_state.longitude)
evaluation_date=st.session_state.evaluation_date

st.markdown("### 💧 Search for surface-water bodies near the field")
st.info(
    "The search uses Sentinel-2 surface reflectance. **NDWI** responds to green vs near-infrared reflectance, "
    "**MNDWI** uses green vs short-wave infrared, and **NDVI is used as a vegetation screen** to reduce false positives. "
    "The detected polygon area is a satellite-derived surface extent, not a direct measurement of water depth."
)

c1,c2,c3,c4=st.columns(4)
radius_km=c1.select_slider("Search radius from field", options=[1,2,3,5,7.5,10,15,20], value=float(st.session_state.get("water_radius_km",5)))
lookback=c2.selectbox("Satellite look-back period", [30,60,90,120,180], index=[30,60,90,120,180].index(int(st.session_state.get("water_lookback_days",90))))
cloud_limit=c3.slider("Maximum scene cloud (%)", 10, 95, int(st.session_state.get("water_cloud_limit",70)), 5)
min_area_ha=c4.select_slider("Minimum water-body area (ha)", options=[0.01,0.02,0.05,0.1,0.25,0.5,1.0], value=float(st.session_state.get("water_min_area_ha",0.05)))

method=st.radio(
    "Water detection method",
    ["Combined NDWI + MNDWI", "MNDWI only", "NDWI only"],
    index=0,
    horizontal=True,
    help="Combined is the conservative default. MNDWI is useful around built-up/bare surfaces; NDWI is a classic open-water index. NDVI is retained as a vegetation exclusion screen.",
)
with st.expander("Advanced spectral thresholds"):
    a,b,c=st.columns(3)
    mndwi_thr=a.slider("MNDWI threshold", -0.30, 0.50, float(st.session_state.get("water_mndwi_thr",0.00)), 0.01)
    ndwi_thr=b.slider("NDWI threshold", -0.30, 0.50, float(st.session_state.get("water_ndwi_thr",0.00)), 0.01)
    ndvi_max=c.slider("Maximum NDVI allowed for water", -0.10, 0.70, float(st.session_state.get("water_ndvi_max",0.35)), 0.01)
    st.caption("If genuine turbid/shallow water is missed, slightly lower the water-index threshold. If wet soil/vegetation is falsely detected, raise the water-index threshold or lower the NDVI ceiling.")

run=st.button("🔎 Detect nearby water bodies", type="primary", use_container_width=True)
if run:
    try:
        with st.spinner("Searching Sentinel-2 imagery and extracting water polygons..."):
            result=detect_nearby_water_bodies(
                lat,lon,evaluation_date,radius_km=radius_km,lookback_days=lookback,cloud_limit=cloud_limit,
                method=method,mndwi_threshold=mndwi_thr,ndwi_threshold=ndwi_thr,ndvi_max=ndvi_max,
                min_area_ha=min_area_ha,max_results=30,
            )
        st.session_state["water_resource_result"]=result
        st.session_state.update({
            "water_radius_km":float(radius_km),"water_lookback_days":int(lookback),"water_cloud_limit":int(cloud_limit),
            "water_min_area_ha":float(min_area_ha),"water_mndwi_thr":float(mndwi_thr),"water_ndwi_thr":float(ndwi_thr),"water_ndvi_max":float(ndvi_max),
        })
        if result["count"]:
            st.success(f"Detected {result['count']} water bodies meeting the selected criteria.")
        else:
            st.warning("No water polygons met the selected thresholds/minimum area. Try a larger radius, longer look-back, or slightly lower index threshold.")
    except Exception as exc:
        st.error(f"Water-body detection failed: {exc}")
        st.info("The rest of the irrigation DSS remains usable. Check Earth Engine credentials/network, or try a smaller search radius and longer date window.")

result=st.session_state.get("water_resource_result")
if not result:
    st.stop()

bodies=result.get("water_bodies",[])
if abs(float(result.get("radius_km",0))-float(radius_km))>0.01:
    st.warning("The displayed result was generated with a different radius. Click Detect nearby water bodies to refresh it.")

m1,m2,m3,m4=st.columns(4)
m1.metric("Detected water bodies",result.get("count",0))
m2.metric("Total detected surface area",f"{result.get('total_area_ha',0):,.3f} ha")
m3.metric("Search radius",f"{result.get('radius_km',radius_km):g} km")
m4.metric("Sentinel-2 scenes used",result.get("scene_count",0))
st.caption(f"Composite window: {result.get('date_start')} to {result.get('date_end')} • raster/vector scale ≈ {result.get('scale_m')} m • method: {result.get('method')}")
if result.get("fallback_used"):
    st.caption("Automatic fallback widened the Sentinel-2 date/cloud window because the original query returned no scene.")

st.markdown("### 🛰️ Satellite map — field, search radius and detected water")
zoom=15 if float(result.get("radius_km",5))<=3 else 13 if float(result.get("radius_km",5))<=10 else 11
wm=water_resources_map(lat,lon,result.get("radius_km",radius_km),field_boundary=field_boundary,water_bodies=bodies,zoom=zoom)
st_folium(wm,width=None,height=650,key="nearby_water_satellite_map")
st.caption("Green = saved agricultural field • dashed amber circle = selected search vicinity • blue polygons W1, W2… = Sentinel-2 water detections.")

if not bodies:
    st.stop()

st.markdown("### 📊 Water-body inventory and estimated available storage")
st.warning(
    "**Storage volume is not measured by NDWI/MNDWI.** Enter a measured or defensible assumed mean water depth for each water body. "
    "The dashboard then calculates an indicative storage volume = detected surface area × mean depth."
)

default_depth=st.number_input("Default mean water depth for volume scenario (m)",0.05,30.0,float(st.session_state.get("water_default_depth_m",1.5)),0.05)
st.session_state["water_default_depth_m"]=float(default_depth)

rows=[]
for w in bodies:
    rows.append({
        "ID":f"W{w['id']}","Distance from field (km)":round(w["distance_km"],3),"Surface area (ha)":round(w["area_ha"],4),
        "Mean NDWI":None if w["mean_ndwi"] is None else round(w["mean_ndwi"],3),
        "Mean MNDWI":None if w["mean_mndwi"] is None else round(w["mean_mndwi"],3),
        "Mean NDVI":None if w["mean_ndvi"] is None else round(w["mean_ndvi"],3),
        "Mean depth (m)":float(default_depth),
    })
df=pd.DataFrame(rows)
edited=st.data_editor(
    df,hide_index=True,use_container_width=True,key="water_depth_editor",
    disabled=["ID","Distance from field (km)","Surface area (ha)","Mean NDWI","Mean MNDWI","Mean NDVI"],
    column_config={"Mean depth (m)":st.column_config.NumberColumn("Mean depth (m)",min_value=0.0,max_value=100.0,step=0.05,help="Measured/assumed mean depth used only for storage estimation.")},
)
edited["Estimated storage (m³)"]=edited["Surface area (ha)"]*10000.0*edited["Mean depth (m)"]
edited["Estimated storage (million L)"]=edited["Estimated storage (m³)"]/1000.0
st.dataframe(edited,hide_index=True,use_container_width=True,column_config={
    "Estimated storage (m³)":st.column_config.NumberColumn(format="%.0f"),
    "Estimated storage (million L)":st.column_config.NumberColumn(format="%.3f"),
})
total_m3=float(edited["Estimated storage (m³)"].sum())
total_ml=total_m3/1000.0
x1,x2,x3=st.columns(3)
x1.metric("Indicative total storage",f"{total_m3:,.0f} m³")
x2.metric("Indicative total storage",f"{total_ml:,.3f} million L")
search_area_ha=math.pi*(float(result.get("radius_km",radius_km))*1000.0)**2/10000.0
x3.metric("Detected water cover in search area",f"{100*result.get('total_area_ha',0)/search_area_ha:.3f}%")
st.caption("For operational water-availability claims, replace assumed depth with surveyed bathymetry, gauge readings, reservoir stage-storage data, or measured mean depth. Also account for dead storage, seepage, environmental requirements and conveyance losses.")

st.markdown("### 🏔️ Descriptive 3D vicinity map — field + nearby water resources")
st.write(
    "This 3D view is intended for presentation and spatial understanding: the terrain surface shows the surrounding relief, the **field boundary is highlighted**, "
    "and each detected water body is drawn and labelled W1, W2… at its approximate terrain/water-surface elevation. It shows *where* water resources are relative to the field; it does not infer underwater bathymetry."
)
quality=st.select_slider("3D terrain sampling density",options=[7,8,9,10],value=9)
max_3d=st.slider("Maximum water bodies to draw in 3D",1,min(20,len(bodies)),min(10,len(bodies)))
try:
    with st.spinner("Building vicinity-scale terrain and water-resource 3D view..."):
        lat_axis,lon_axis,z=terrain_grid_for_radius(lat,lon,result.get("radius_km",radius_km),n=quality)
        field_df=boundary_elevations(field_boundary)
        water3=bodies[:max_3d]
        water_elev=water_centroid_elevations(water3)

    lon_grid,lat_grid=np.meshgrid(lon_axis,lat_axis)
    fig=go.Figure()
    fig.add_trace(go.Surface(x=lon_grid,y=lat_grid,z=z,colorscale="Earth",opacity=0.90,colorbar=dict(title="Elevation (m)"),name="Terrain",showscale=True))
    relief=max(float(np.nanmax(z)-np.nanmin(z)),1.0); lift=max(relief*0.025,1.5)
    if not field_df.empty:
        fig.add_trace(go.Scatter3d(x=field_df["lon"],y=field_df["lat"],z=field_df["elevation"]+lift,mode="lines+markers",line=dict(width=9),marker=dict(size=3),name="Agricultural field",hovertemplate="Field boundary<br>Elevation %{z:.1f} m<extra></extra>"))
    for w,elev in zip(water3,water_elev):
        geom=w.get("geometry",{}); coords=geom.get("coordinates",[])
        rings=[]
        if geom.get("type")=="Polygon" and coords: rings=[coords[0]]
        elif geom.get("type")=="MultiPolygon": rings=[poly[0] for poly in coords if poly]
        for j,ring in enumerate(rings):
            xs=[p[0] for p in ring]; ys=[p[1] for p in ring]; zs=[float(elev)+lift]*len(ring)
            fig.add_trace(go.Scatter3d(x=xs,y=ys,z=zs,mode="lines",line=dict(width=7),name=w["name"] if j==0 else None,showlegend=(j==0),hovertemplate=f"{w['name']}<br>Area {w['area_ha']:.3f} ha<br>Distance {w['distance_km']:.2f} km<extra></extra>"))
        fig.add_trace(go.Scatter3d(x=[w["centroid_lon"]],y=[w["centroid_lat"]],z=[float(elev)+2*lift],mode="markers+text",marker=dict(size=5,symbol="diamond"),text=[f"W{w['id']}"],textposition="top center",name=f"W{w['id']} label",showlegend=False,hovertemplate=f"W{w['id']} • {w['area_ha']:.3f} ha • {w['distance_km']:.2f} km<extra></extra>"))
    fig.add_trace(go.Scatter3d(x=[lon],y=[lat],z=[float(np.nanmean(z))+2.2*lift],mode="markers+text",marker=dict(size=7,symbol="circle"),text=["FIELD"],textposition="top center",name="Field centre"))
    fig.update_layout(
        height=760,margin=dict(l=0,r=0,t=55,b=0),title=f"3D water-resource context within {result.get('radius_km',radius_km):g} km of the field",
        scene=dict(xaxis_title="Longitude",yaxis_title="Latitude",zaxis_title="Elevation (m)",aspectmode="data",camera=dict(eye=dict(x=1.5,y=1.5,z=1.0))),
        legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="left",x=0),
    )
    st.plotly_chart(fig,use_container_width=True)
    zmin=float(np.nanmin(z)); zmax=float(np.nanmax(z))
    q1,q2,q3,q4=st.columns(4)
    q1.metric("Water bodies shown in 3D",len(water3))
    q2.metric("Nearest detected water",f"{min(w['distance_km'] for w in bodies):.2f} km")
    q3.metric("Terrain relief in search view",f"{zmax-zmin:.1f} m")
    q4.metric("Largest detected water surface",f"{max(w['area_ha'] for w in bodies):.3f} ha")
    st.caption("3D terrain elevation is contextual, not engineering-survey/bathymetric data. Water polygons come from Sentinel-2 spectral classification; their vertical placement uses local terrain/elevation context only.")
except Exception as exc:
    st.error(f"3D vicinity view could not be generated: {exc}")
    st.info("The satellite water-resource map and water inventory above remain available even if the elevation service is temporarily unavailable.")

with st.expander("How to explain this page in a presentation"):
    st.markdown(
        "1. **Select vicinity radius** around the saved field.\n"
        "2. Sentinel-2 imagery is screened for open water using **NDWI and MNDWI**, with **NDVI suppressing vegetated pixels**.\n"
        "3. Detected water polygons provide **surface area and distance from the field**.\n"
        "4. For water quantity, enter measured/assumed mean depth; the DSS calculates **indicative storage = area × mean depth**.\n"
        "5. The final 3D view communicates the field, surrounding terrain and spatial relationship to the detected water resources."
    )
