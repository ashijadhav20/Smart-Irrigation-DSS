import json
from datetime import date, timedelta
import streamlit as st
from streamlit_folium import st_folium

from core.ui import inject_css, hero
from core.data import CROPS, SOILS
from core.geometry import (
    normalize_polygon_geojson, polygon_geodesic_area_m2, polygon_centroid_latlon,
    area_from_shape, regular_shape_geometry, irregular_template_geometry, local_offsets_geometry, polygon_side_lengths_m,
)
from core.map_tools import satellite_map
from core.soil_lookup import fetch_soil_texture, classify_usda_texture

st.set_page_config(page_title="Smart Irrigation DSS", page_icon="🌱", layout="wide")
inject_css(); hero("Page 1 • Field geometry, satellite boundary, crop and soil definition")

st.markdown("### 📍 Field location and geometry")
st.info(
    "Choose **Regular shape** when dimensions are known, or **Irregular / actual boundary** "
    "when the field does not follow a standard shape. In both cases the saved polygon is displayed "
    "at the real coordinates on satellite imagery and is used for Sentinel-2 NDVI clipping."
)

c1,c2=st.columns(2)
with c1:
    latitude=st.number_input("Field / map centre latitude", value=float(st.session_state.get("map_input_latitude", st.session_state.get("latitude",20.2961))), format="%.6f")
with c2:
    longitude=st.number_input("Field / map centre longitude", value=float(st.session_state.get("map_input_longitude", st.session_state.get("longitude",85.8245))), format="%.6f")

geometry_mode=st.radio(
    "Field geometry method",
    ["Regular shape — enter dimensions", "Irregular / actual boundary — draw or upload"],
    horizontal=True,
    index=0 if st.session_state.get("field_geometry_mode","").startswith("Regular") else 1,
)

boundary=None
formula_area=0.0
field_shape="Irregular polygon"
shape_params={}

if geometry_mode.startswith("Regular"):
    st.markdown("#### 📐 Select regular field shape and dimensions")
    field_shape=st.selectbox(
        "Regular shape",
        ["Rectangle","Square","Circle","Triangle","Trapezoid"],
        index=["Rectangle","Square","Circle","Triangle","Trapezoid"].index(st.session_state.get("field_shape","Rectangle")) if st.session_state.get("field_shape","Rectangle") in ["Rectangle","Square","Circle","Triangle","Trapezoid"] else 0,
    )
    bearing=st.slider("Field orientation / bearing (degrees clockwise)",0,359,int(st.session_state.get("field_bearing_deg",0)),1)
    if field_shape=="Rectangle":
        a,b=st.columns(2); length=a.number_input("Length (m)",1.0,10000.0,float(st.session_state.get("shape_length_m",100.0))); width=b.number_input("Width (m)",1.0,10000.0,float(st.session_state.get("shape_width_m",50.0)))
        shape_params={"length":length,"width":width}; formula_area=area_from_shape(field_shape,**shape_params)
    elif field_shape=="Square":
        side=st.number_input("Side (m)",1.0,10000.0,float(st.session_state.get("shape_side_m",70.0))); shape_params={"side":side}; formula_area=area_from_shape(field_shape,**shape_params)
    elif field_shape=="Circle":
        radius=st.number_input("Radius (m)",1.0,5000.0,float(st.session_state.get("shape_radius_m",40.0))); shape_params={"radius":radius}; formula_area=area_from_shape(field_shape,**shape_params)
    elif field_shape=="Triangle":
        a,b=st.columns(2); base=a.number_input("Base (m)",1.0,10000.0,float(st.session_state.get("shape_base_m",80.0))); height=b.number_input("Perpendicular height (m)",1.0,10000.0,float(st.session_state.get("shape_height_m",60.0)))
        shape_params={"base":base,"height":height}; formula_area=area_from_shape(field_shape,**shape_params)
    else:
        a,b,c=st.columns(3); side_a=a.number_input("Parallel side A (m)",1.0,10000.0,float(st.session_state.get("shape_a_m",60.0))); side_b=b.number_input("Parallel side B (m)",1.0,10000.0,float(st.session_state.get("shape_b_m",90.0))); height=c.number_input("Perpendicular height (m)",1.0,10000.0,float(st.session_state.get("shape_height_m",50.0)))
        shape_params={"a":side_a,"b":side_b,"height":height}; formula_area=area_from_shape(field_shape,**shape_params)
    boundary=regular_shape_geometry(field_shape,latitude,longitude,bearing_deg=bearing,**shape_params)
    mapped_area=polygon_geodesic_area_m2(boundary)
    x1,x2,x3=st.columns(3); x1.metric("Area from entered dimensions",f"{formula_area:,.1f} m²"); x2.metric("Area",f"{formula_area/10000:.4f} ha"); x3.metric("Mapped geodesic check",f"{mapped_area:,.1f} m²")
    st.caption("For regular fields, the mathematical area from the entered dimensions is used for irrigation-volume calculation. The generated WGS-84 polygon is used for map display and NDVI clipping.")
    m=satellite_map(latitude,longitude,zoom=18,boundary=boundary,editable=False)
    st_folium(m,width=None,height=520,key="regular_field_map")
else:
    st.markdown("#### 🛰️ Define the actual irregular field boundary")
    st.caption("An irregular field is stored as a true multi-vertex polygon. Choose free drawing, a dimension-based irregular template, custom corner dimensions, or GeoJSON upload.")

    irregular_method = st.radio(
        "Irregular field entry method",
        [
            "Draw free polygon on satellite map",
            "Enter dimensions — L-shape / T-shape",
            "Enter custom polygon corners (metres)",
            "Upload GeoJSON boundary",
        ],
        horizontal=False,
        index=0,
    )

    boundary = st.session_state.get("field_geometry") if st.session_state.get("field_geometry_mode", "").startswith("Irregular") else None
    field_shape = "Irregular polygon"

    if irregular_method.startswith("Draw free"):
        st.info("Select the **polygon tool** on the left side of the satellite map, click each real field corner, then click the first corner again to close the polygon. Rectangle drawing is disabled in this mode.")
        m = satellite_map(latitude, longitude, zoom=18, boundary=boundary, editable=True, allow_rectangle=False)
        map_data = st_folium(m, width=None, height=590, key="true_irregular_polygon_editor")
        drawings = (map_data or {}).get("all_drawings") or []
        new_geom = None
        for item in reversed(drawings):
            g = normalize_polygon_geojson(item)
            if g:
                new_geom = g
                break
        if new_geom:
            old = st.session_state.get("field_geometry")
            if old != new_geom:
                st.session_state["field_geometry"] = new_geom
                st.session_state["irregular_entry_method"] = irregular_method
                boundary = new_geom
                st.rerun()
        boundary = st.session_state.get("field_geometry")

    elif irregular_method.startswith("Enter dimensions"):
        field_shape = st.selectbox("Irregular dimension template", ["L-shape", "T-shape"], index=0)
        bearing = st.slider("Field orientation / bearing (degrees clockwise)", 0, 359, int(st.session_state.get("field_bearing_deg", 0)), 1, key="irregular_template_bearing")
        if field_shape == "L-shape":
            st.caption("Define the full outer rectangle, then subtract the rectangular cut-out from one corner.")
            a,b = st.columns(2)
            outer_length = a.number_input("Outer length (m)", 2.0, 10000.0, float(st.session_state.get("irr_outer_length_m", 120.0)))
            outer_width = b.number_input("Outer width (m)", 2.0, 10000.0, float(st.session_state.get("irr_outer_width_m", 90.0)))
            c,d = st.columns(2)
            cutout_length = c.number_input("Cut-out length (m)", 1.0, max(1.0, outer_length-0.1), min(float(st.session_state.get("irr_cutout_length_m", 45.0)), outer_length-0.1))
            cutout_width = d.number_input("Cut-out width (m)", 1.0, max(1.0, outer_width-0.1), min(float(st.session_state.get("irr_cutout_width_m", 35.0)), outer_width-0.1))
            boundary, formula_area = irregular_template_geometry(
                "L-shape", latitude, longitude, bearing_deg=bearing,
                outer_length=outer_length, outer_width=outer_width,
                cutout_length=cutout_length, cutout_width=cutout_width,
            )
            shape_params={"outer_length":outer_length,"outer_width":outer_width,"cutout_length":cutout_length,"cutout_width":cutout_width}
        else:
            st.caption("Define a T-shaped field using the top bar and the central stem dimensions.")
            a,b = st.columns(2)
            top_length = a.number_input("Top-bar depth/length (m)", 1.0, 10000.0, float(st.session_state.get("irr_top_length_m", 35.0)))
            top_width = b.number_input("Top-bar width (m)", 2.0, 10000.0, float(st.session_state.get("irr_top_width_m", 120.0)))
            c,d = st.columns(2)
            stem_length = c.number_input("Stem length (m)", 1.0, 10000.0, float(st.session_state.get("irr_stem_length_m", 85.0)))
            stem_width = d.number_input("Stem width (m)", 1.0, max(1.0, top_width), min(float(st.session_state.get("irr_stem_width_m", 40.0)), top_width))
            boundary, formula_area = irregular_template_geometry(
                "T-shape", latitude, longitude, bearing_deg=bearing,
                top_length=top_length, top_width=top_width, stem_length=stem_length, stem_width=stem_width,
            )
            shape_params={"top_length":top_length,"top_width":top_width,"stem_length":stem_length,"stem_width":stem_width}
        st.session_state["field_geometry"] = boundary
        st.session_state["irregular_entry_method"] = irregular_method
        mapped_area = polygon_geodesic_area_m2(boundary) if boundary else 0.0
        q1,q2,q3 = st.columns(3)
        q1.metric("Area from dimensions", f"{formula_area:,.1f} m²")
        q2.metric("Area", f"{formula_area/10000:.4f} ha")
        q3.metric("Mapped geodesic check", f"{mapped_area:,.1f} m²")
        m = satellite_map(latitude, longitude, zoom=18, boundary=boundary, editable=False)
        st_folium(m, width=None, height=560, key=f"irregular_template_map_{field_shape}")

    elif irregular_method.startswith("Enter custom"):
        st.info("Choose the number of corners and enter each corner as **East/West and North/South offset in metres from the map centre**. This creates a genuine irregular polygon and is useful when field dimensions or surveyed corner offsets are known.")
        n_vertices = st.slider("Number of polygon corners", 3, 12, int(st.session_state.get("custom_polygon_vertices", 5)), 1)
        bearing = st.slider("Rotate complete polygon / field bearing (degrees clockwise)", 0, 359, int(st.session_state.get("field_bearing_deg", 0)), 1, key="custom_polygon_bearing")
        defaults = [(-50,-40),(45,-35),(70,10),(20,55),(-55,35),(-75,0),(0,-70),(75,-10),(55,60),(-20,75),(-80,45),(-90,-20)]
        vertices=[]
        for i in range(n_vertices):
            x0,y0=defaults[i]
            c1,c2=st.columns(2)
            east=c1.number_input(f"Corner {i+1} — East offset (m)", -10000.0, 10000.0, float(st.session_state.get(f"custom_east_{i}", x0)), 1.0, key=f"custom_east_input_{i}")
            north=c2.number_input(f"Corner {i+1} — North offset (m)", -10000.0, 10000.0, float(st.session_state.get(f"custom_north_{i}", y0)), 1.0, key=f"custom_north_input_{i}")
            vertices.append((east,north))
        boundary = local_offsets_geometry(latitude, longitude, vertices, bearing_deg=bearing)
        formula_area = polygon_geodesic_area_m2(boundary)
        st.session_state["field_geometry"] = boundary
        st.session_state["irregular_entry_method"] = irregular_method
        st.session_state["custom_polygon_vertices"] = n_vertices
        side_lengths=polygon_side_lengths_m(boundary)
        q1,q2,q3=st.columns(3)
        q1.metric("Custom polygon area",f"{formula_area:,.1f} m²")
        q2.metric("Area",f"{formula_area/10000:.4f} ha")
        q3.metric("Corners",n_vertices)
        if side_lengths:
            st.caption("Calculated side lengths: " + " • ".join(f"S{i+1} {d:.1f} m" for i,d in enumerate(side_lengths)))
        m=satellite_map(latitude,longitude,zoom=18,boundary=boundary,editable=False)
        st_folium(m,width=None,height=560,key="custom_polygon_dimension_map")

    else:
        st.caption("Upload a Polygon or MultiPolygon GeoJSON from GPS/GIS/survey data. The uploaded boundary itself becomes the DSS field boundary.")
        uploaded=st.file_uploader("Upload GeoJSON field boundary", type=["geojson","json"], key="irregular_geojson_upload")
        if uploaded is not None:
            try:
                obj=json.load(uploaded); geom=normalize_polygon_geojson(obj)
                if not geom: raise ValueError("No Polygon geometry found in the uploaded file.")
                st.session_state["field_geometry"]=geom
                st.session_state["irregular_entry_method"]=irregular_method
                boundary=geom
                st.success("GeoJSON field boundary loaded.")
            except Exception as exc:
                st.error(f"Could not read field boundary: {exc}")
        boundary=st.session_state.get("field_geometry")
        if boundary:
            m=satellite_map(latitude,longitude,zoom=18,boundary=boundary,editable=False)
            st_folium(m,width=None,height=560,key="uploaded_irregular_boundary_map")

    if boundary:
        if not formula_area:
            formula_area=polygon_geodesic_area_m2(boundary)
        side_lengths=polygon_side_lengths_m(boundary)
        a,b,c=st.columns(3)
        a.metric("Actual irregular field area",f"{formula_area:,.1f} m²")
        b.metric("Field area",f"{formula_area/10000:.4f} ha")
        c.metric("Boundary vertices",max(0,len(boundary["coordinates"][0])-1))
        with st.expander("View polygon side dimensions"):
            if side_lengths:
                for i,d in enumerate(side_lengths, start=1):
                    st.write(f"Side {i}: {d:.2f} m")
        if st.button("🗑️ Clear saved irregular boundary"):
            st.session_state.pop("field_geometry",None); st.rerun()
    else:
        st.warning("Define the irregular boundary using one of the methods above before saving the field.")

centre=polygon_centroid_latlon(boundary) if boundary else None
field_lat,field_lon=(centre if centre else (latitude,longitude))
if boundary:
    st.caption(f"Saved field query centre: {field_lat:.6f}, {field_lon:.6f}.")

st.markdown("### 🌾 Crop and soil configuration")
crop_col,soil_col=st.columns([0.9,1.4])
with crop_col:
    crop=st.selectbox("Crop",list(CROPS.keys()),index=list(CROPS.keys()).index(st.session_state.get("crop","Rice")) if st.session_state.get("crop","Rice") in CROPS else 0)
    sowing_date=st.date_input("Sowing date",value=st.session_state.get("sowing_date",date.today()-timedelta(days=35)))
    evaluation_date=st.date_input("Evaluation date",value=st.session_state.get("evaluation_date",date.today()))
with soil_col:
    soil_method=st.radio(
        "Soil definition method",
        ["Automatic — SoilGrids texture estimate", "Manual — choose soil type", "Composition — enter sand/silt/clay %"],
        horizontal=False,
        index=0,
    )
    detected=st.session_state.get("detected_soil_data")
    sand_pct=silt_pct=clay_pct=None
    soil_source=""
    if soil_method.startswith("Automatic"):
        if st.button("🔎 Fetch soil texture for field centre",use_container_width=True,disabled=not bool(boundary)):
            try:
                with st.spinner("Fetching ISRIC SoilGrids sand, silt and clay prediction..."):
                    detected=fetch_soil_texture(field_lat,field_lon,depth="0-5cm")
                st.session_state["detected_soil_data"]=detected; st.success(f"Estimated USDA texture class: {detected['soil_type']}")
            except Exception as exc:
                st.warning("Automatic lookup is unavailable. Use composition from a soil test or choose the soil class manually."); st.code(str(exc))
        detected=st.session_state.get("detected_soil_data")
        if detected:
            soil=detected["soil_type"]; sand_pct=float(detected["sand_pct"]); silt_pct=float(detected["silt_pct"]); clay_pct=float(detected["clay_pct"]); soil_source=detected.get("source","ISRIC SoilGrids")
            q1,q2,q3,q4=st.columns(4); q1.metric("USDA class",soil); q2.metric("Sand",f"{sand_pct:.1f}%"); q3.metric("Silt",f"{silt_pct:.1f}%"); q4.metric("Clay",f"{clay_pct:.1f}%")
            st.caption(f"Source: {soil_source}. Global model prediction for screening; verify with field/laboratory texture data for plot-level decisions.")
        else:
            soil=st.session_state.get("soil_type","Loam"); st.info("Click Fetch soil texture, or select another soil-definition method.")
    elif soil_method.startswith("Manual"):
        soil=st.selectbox("Choose USDA textural class",list(SOILS.keys()),index=list(SOILS.keys()).index(st.session_state.get("soil_type","Loam")) if st.session_state.get("soil_type","Loam") in SOILS else 3)
        soil_source="Manual USDA textural class"
        st.caption("Use this when the field soil class is already known. Sand/silt/clay percentages are not assumed unless you enter them using the Composition option.")
    else:
        st.write("Enter the measured or known particle-size composition. The total must equal 100%.")
        p1,p2,p3=st.columns(3)
        sand_pct=p1.number_input("Sand (%)",0.0,100.0,float(st.session_state.get("sand_pct",40.0)),0.5)
        silt_pct=p2.number_input("Silt (%)",0.0,100.0,float(st.session_state.get("silt_pct",40.0)),0.5)
        clay_pct=p3.number_input("Clay (%)",0.0,100.0,float(st.session_state.get("clay_pct",20.0)),0.5)
        total=sand_pct+silt_pct+clay_pct
        st.metric("Composition total",f"{total:.1f}%")
        if abs(total-100.0)>0.5:
            st.error("Sand + silt + clay must total 100% (±0.5%).")
            soil=None
        else:
            soil=classify_usda_texture(sand_pct,silt_pct,clay_pct); soil_source="User-entered particle-size composition"
            st.success(f"USDA textural class from composition: **{soil}**")
    if soil in SOILS:
        v1,v2,v3=st.columns(3); v1.metric("Selected texture",soil); v2.metric("FC default",f"{SOILS[soil]['fc']*100:.1f}% VWC"); v3.metric("PWP default",f"{SOILS[soil]['pwp']*100:.1f}% VWC")
        st.caption("FC and PWP are database starting values tied to the selected texture class; measured field values should replace them when available.")

st.markdown("### ⚙️ Irrigation settings")
d1,d2,d3=st.columns(3)
efficiency=d1.slider("Application efficiency (%)",40,100,int(st.session_state.get("efficiency_pct",80)))
rain_eff=d2.slider("Effective rainfall fraction (%)",30,100,int(st.session_state.get("rain_eff_pct",80)))
forecast_days=d3.slider("Forecast horizon (days)",3,14,int(st.session_state.get("forecast_days",7)))

if evaluation_date<sowing_date: st.error("Evaluation date cannot be earlier than sowing date."); st.stop()

if st.button("✅ Save field inputs",type="primary",use_container_width=True):
    if not boundary or formula_area<=0: st.error("Please define a valid field geometry first."); st.stop()
    if soil is None or soil not in SOILS: st.error("Please complete a valid soil definition first."); st.stop()
    if soil_method.startswith("Automatic") and not st.session_state.get("detected_soil_data"): st.error("Fetch the automatic soil texture first, or use another soil method."); st.stop()
    update={
        "latitude":field_lat,"longitude":field_lon,"map_input_latitude":latitude,"map_input_longitude":longitude,
        "crop":crop,"soil_type":soil,"soil_mode":soil_method,"soil_source":soil_source,
        "sowing_date":sowing_date,"evaluation_date":evaluation_date,"field_shape":field_shape,"field_geometry_mode":geometry_mode,
        "field_geometry":boundary,"area_m2":float(formula_area),"efficiency_pct":efficiency,"rain_eff_pct":rain_eff,"forecast_days":forecast_days,
    }
    if sand_pct is not None: update.update({"sand_pct":float(sand_pct),"silt_pct":float(silt_pct),"clay_pct":float(clay_pct)})
    if geometry_mode.startswith("Regular"):
        update["field_bearing_deg"]=bearing
        name_map={"length":"shape_length_m","width":"shape_width_m","side":"shape_side_m","radius":"shape_radius_m","base":"shape_base_m","height":"shape_height_m","a":"shape_a_m","b":"shape_b_m"}
        for k,v in shape_params.items(): update[name_map[k]]=float(v)

    if geometry_mode.startswith("Irregular"):
        update["irregular_entry_method"] = irregular_method
        update["field_shape"] = field_shape
        if "bearing" in locals(): update["field_bearing_deg"] = bearing
        if field_shape == "L-shape":
            update.update({"irr_outer_length_m":outer_length,"irr_outer_width_m":outer_width,"irr_cutout_length_m":cutout_length,"irr_cutout_width_m":cutout_width})
        elif field_shape == "T-shape":
            update.update({"irr_top_length_m":top_length,"irr_top_width_m":top_width,"irr_stem_length_m":stem_length,"irr_stem_width_m":stem_width})
        if irregular_method.startswith("Enter custom"):
            update["custom_polygon_vertices"] = n_vertices
            for i,(east,north) in enumerate(vertices):
                update[f"custom_east_{i}"] = float(east); update[f"custom_north_{i}"] = float(north)
    st.session_state.update(update)
    st.success("Field geometry, soil definition and irrigation settings saved. Open Weather from the sidebar.")

st.caption("For irrigation volume, depth in mm is converted using horizontal plan area. Ground slope is visualized separately in the final 3D terrain page rather than inflating the irrigation area.")
