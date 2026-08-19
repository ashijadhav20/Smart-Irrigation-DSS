import streamlit as st
from core.ui import inject_css, hero, require_inputs
from core.crop import crop_stage_and_kc, ndvi_stage_relative_kc, linear_calibrated_kc, crop_specific_alpha
from core.gee_ndvi import get_sentinel2_ndvi, make_query_signature

st.set_page_config(page_title="Crop & ETc | Irrigation DSS",page_icon="🌿",layout="wide")
inject_css(); hero("Page 3 • Crop-specific Kc, Sentinel-2 NDVI and transparent calibration")
require_inputs()

crop=st.session_state.crop
stage,base_kc,dap=crop_stage_and_kc(crop,st.session_state.sowing_date,st.session_state.evaluation_date)
c1,c2,c3=st.columns(3); c1.metric("Days after sowing",dap); c2.metric("Growth stage",stage); c3.metric("FAO-style base Kc",f"{base_kc:.3f}")

st.warning("Scientific interpretation: NDVI itself can be used for many crops, but the NDVI→Kc relationship is NOT one fixed universal equation. Kc is crop- and stage-specific; direct NDVI–Kc equations should be calibrated/validated for the crop, site and management system.")

boundary=st.session_state.get("field_geometry")
sig=make_query_signature(st.session_state.latitude,st.session_state.longitude,st.session_state.evaluation_date,st.session_state.get("area_m2"),boundary)
gee=st.session_state.get("gee_result")
if gee and tuple(gee.get("query_signature",()))!=tuple(sig):
    st.session_state.pop("gee_result",None); gee=None

@st.cache_data(ttl=86400,show_spinner=False)
def cached_ndvi(lat,lon,date_iso,area,max_days,min_clear,boundary_json):
    import json
    geom=json.loads(boundary_json) if boundary_json else None
    return get_sentinel2_ndvi(lat,lon,date_iso,area_m2=area,max_days=max_days,min_clear_fraction=min_clear,field_geometry=geom)

ndvi_source=st.radio("NDVI source",["Automatic — Sentinel-2 / GEE","Manual NDVI","No NDVI"],horizontal=True)
ndvi=None
if ndvi_source=="Automatic — Sentinel-2 / GEE":
    a,b=st.columns(2)
    max_days=a.select_slider("Maximum satellite-date difference",options=[15,30,45,60],value=60)
    min_clear=b.slider("Minimum clear field pixels (%)",5,80,20,5)
    if st.button("🛰️ Fetch NDVI for actual field polygon",type="primary",use_container_width=True):
        try:
            import json
            with st.spinner("Screening Sentinel-2 over the saved field polygon..."):
                gee=cached_ndvi(st.session_state.latitude,st.session_state.longitude,st.session_state.evaluation_date.isoformat(),float(st.session_state.area_m2),int(max_days),min_clear/100.0,json.dumps(boundary) if boundary else "")
            st.session_state["gee_result"]=gee
        except Exception as exc:
            st.warning(str(exc)); gee=None
    if gee:
        ndvi=float(gee["ndvi"]); st.success(f"Field NDVI: {ndvi:.3f} • satellite date {gee['acquisition_date']} • footprint: {gee.get('footprint_method')}")
elif ndvi_source=="Manual NDVI":
    ndvi=st.slider("NDVI",-0.10,1.00,float(st.session_state.get("ndvi",0.60)),0.01)
else:
    st.session_state.pop("gee_result",None)

if ndvi is None:
    method="FAO stage Kc only"; kc_adj=base_kc; factor=1.0
else:
    method=st.radio("How should NDVI influence Kc?",[
        "Stage-relative crop mode — conservative research correction",
        "Direct crop/site calibrated equation — Kc = a × NDVI + b",
        "Do not modify Kc — display NDVI only",
    ])
    if method.startswith("Stage-relative"):
        default_alpha=crop_specific_alpha(crop)
        alpha=st.slider(f"{crop} NDVI sensitivity α (research setting)",0.0,0.8,float(st.session_state.get("ndvi_alpha",default_alpha)),0.05)
        kc_adj,factor,expected=ndvi_stage_relative_kc(crop,base_kc,ndvi,stage,alpha)
        st.caption(f"Formula: Kc_adj = Kc_stage × [1 + α × (NDVI − NDVI_stage_ref)]. Current stage reference NDVI={expected:.2f}. This is a bounded research correction, not a universal published Kc equation.")
        st.session_state["ndvi_alpha"]=alpha
    elif method.startswith("Direct"):
        st.info("Enter coefficients from a published study or your local lysimeter/field calibration for the selected crop. Do not reuse coefficients from another crop without validation.")
        a,b=st.columns(2)
        slope=a.number_input("a (slope)",value=float(st.session_state.get("ndvi_kc_a",1.0)),step=0.05)
        intercept=b.number_input("b (intercept)",value=float(st.session_state.get("ndvi_kc_b",0.0)),step=0.05)
        kc_adj,raw=linear_calibrated_kc(ndvi,slope,intercept); factor=kc_adj/base_kc if base_kc else 1.0
        st.caption(f"Raw calibrated result = {raw:.3f}; bounded dashboard Kc = {kc_adj:.3f}.")
        st.session_state["ndvi_kc_a"]=slope; st.session_state["ndvi_kc_b"]=intercept
    else:
        kc_adj=base_kc; factor=1.0

weather=st.session_state.get("weather_daily")
if weather is None: st.info("Open Weather once to fetch weather data."); st.stop()
et0=float(weather.iloc[0]["et0_fao_evapotranspiration"]); etc=et0*kc_adj
m1,m2,m3,m4,m5=st.columns(5)
m1.metric("NDVI","—" if ndvi is None else f"{ndvi:.3f}"); m2.metric("Base Kc",f"{base_kc:.3f}"); m3.metric("Final Kc",f"{kc_adj:.3f}"); m4.metric("ET₀",f"{et0:.2f} mm/day"); m5.metric("Potential ETc",f"{etc:.2f} mm/day")

st.session_state.update({"stage":stage,"base_kc":base_kc,"ndvi":ndvi,"kc_adj":kc_adj,"etc_potential_today":etc,"ndvi_mode":ndvi_source,"ndvi_kc_method":method})
