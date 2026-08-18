import streamlit as st

from core.ui import inject_css, hero, require_inputs
from core.crop import crop_stage_and_kc, ndvi_corrected_kc
from core.gee_ndvi import get_sentinel2_ndvi, make_query_signature

st.set_page_config(
    page_title="Crop & ETc | Irrigation DSS",
    page_icon="🌿",
    layout="wide",
)

inject_css()
hero("Page 3 • Growth stage, Kc, Sentinel-2 NDVI correction and ETc")
require_inputs()

stage, base_kc, dap = crop_stage_and_kc(
    st.session_state.crop,
    st.session_state.sowing_date,
    st.session_state.evaluation_date,
)

c1, c2, c3 = st.columns(3)
c1.metric("Days after sowing", dap)
c2.metric("Growth stage", stage)
c3.metric("Base Kc", f"{base_kc:.3f}")

st.markdown("### 🛰️ NDVI source")

mode = st.radio(
    "Choose NDVI method",
    [
        "Automatic — Sentinel-2 / GEE",
        "Manual NDVI",
        "No NDVI correction — use base Kc",
    ],
    index=0,
    horizontal=True,
)

current_signature = make_query_signature(
    st.session_state.latitude,
    st.session_state.longitude,
    st.session_state.evaluation_date,
    st.session_state.get("area_m2"),
)

gee_result = st.session_state.get("gee_result")

if gee_result and tuple(gee_result.get("query_signature", ())) != tuple(current_signature):
    st.session_state.pop("gee_result", None)
    gee_result = None

use_correction = False
ndvi = None
alpha = 0.0


@st.cache_data(ttl=86400, show_spinner=False)
def cached_ndvi(
    latitude,
    longitude,
    evaluation_date_iso,
    area_m2,
    max_days,
    min_clear_fraction,
):
    return get_sentinel2_ndvi(
        latitude,
        longitude,
        evaluation_date_iso,
        area_m2=area_m2,
        max_days=max_days,
        min_clear_fraction=min_clear_fraction,
    )


if mode == "Automatic — Sentinel-2 / GEE":
    st.caption(
        "The app now searches one date window only and evaluates candidate scenes "
        "in one Earth Engine server-side batch. This is faster than the earlier "
        "version, which repeatedly tested scenes one-by-one across overlapping "
        "±15/±30/±45/±60-day windows."
    )

    a, b = st.columns(2)

    max_days = a.select_slider(
        "Maximum satellite-date difference",
        options=[15, 30, 45, 60],
        value=60,
        help=(
            "A larger window improves the chance of finding a clear image, "
            "but may use an older satellite observation."
        ),
    )

    min_clear = b.slider(
        "Minimum clear field pixels (%)",
        5,
        80,
        20,
        5,
    )

    if st.button(
        "🛰️ Fetch best Sentinel-2 NDVI",
        type="primary",
        use_container_width=True,
    ):
        try:
            with st.spinner(
                "Earth Engine is screening Sentinel-2 scenes over the field..."
            ):
                gee_result = cached_ndvi(
                    st.session_state.latitude,
                    st.session_state.longitude,
                    st.session_state.evaluation_date.isoformat(),
                    float(st.session_state.get("area_m2", 0.0)),
                    int(max_days),
                    min_clear / 100.0,
                )

            st.session_state["gee_result"] = gee_result
            st.session_state["ndvi"] = float(gee_result["ndvi"])

        except Exception as exc:
            st.session_state.pop("gee_result", None)
            gee_result = None
            st.warning(str(exc))
            st.info(
                "Automatic NDVI was not applied. The calculation below therefore "
                "uses the base crop Kc unless Manual NDVI is selected."
            )

    if gee_result:
        ndvi = float(gee_result["ndvi"])
        use_correction = True

        st.success(
            f"Sentinel-2 field NDVI obtained: {ndvi:.3f} • "
            f"Satellite date: {gee_result['acquisition_date']}"
        )

        st.markdown(
            f"""
            <div style="
                padding: 0.95rem 1.1rem;
                border-radius: 14px;
                border: 1px solid rgba(15,118,110,.18);
                background: rgba(255,255,255,.88);
                margin: 0.35rem 0 0.75rem 0;
            ">
                <div style="font-size:0.82rem; opacity:.72;">
                    Satellite acquisition date
                </div>
                <div style="font-size:1.65rem; font-weight:700; line-height:1.2;">
                    {gee_result["acquisition_date"]}
                </div>
                <div style="font-size:0.92rem; margin-top:0.25rem;">
                    Evaluation-date difference:
                    <b>{gee_result["days_from_evaluation"]} days</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        x1, x2, x3 = st.columns(3)

        x1.metric(
            "Scene cloud",
            f"{gee_result['scene_cloud_pct']:.1f}%",
        )

        x2.metric(
            "Clear field pixels",
            f"{gee_result['clear_fraction'] * 100:.0f}%",
        )

        x3.metric(
            "Scenes in search window",
            int(gee_result.get("scene_count_searched", 0)),
        )

        st.caption(
            f"Search window: ±{gee_result['search_window_days']} days • "
            f"Sampling footprint: {gee_result['footprint_method']} • "
            f"Equivalent radius: {gee_result['sampling_radius_m']:.0f} m."
        )

    else:
        st.warning(
            "No automatic Sentinel-2 NDVI is currently active. "
            "Base Kc will be used."
        )

elif mode == "Manual NDVI":
    ndvi = st.slider(
        "NDVI",
        -0.10,
        1.00,
        float(st.session_state.get("ndvi", 0.60)),
        0.01,
    )
    use_correction = True
    st.session_state.pop("gee_result", None)

else:
    use_correction = False
    ndvi = None
    st.session_state.pop("gee_result", None)

if use_correction and ndvi is not None:
    alpha = st.slider(
        "NDVI correction strength (research calibration coefficient α)",
        0.00,
        0.80,
        float(st.session_state.get("ndvi_alpha", 0.35)),
        0.05,
    )

    kc_adj, factor = ndvi_corrected_kc(
        base_kc,
        ndvi,
        stage,
        alpha,
    )
else:
    alpha = 0.0
    kc_adj = float(base_kc)
    factor = 1.0

weather = st.session_state.get("weather_daily")

if weather is None:
    st.info("Open the Weather page once to fetch weather data.")
    st.stop()

et0_today = float(
    weather.iloc[0]["et0_fao_evapotranspiration"]
)

etc = et0_today * kc_adj

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric(
    "NDVI",
    f"{ndvi:.3f}" if use_correction and ndvi is not None else "Not applied",
)
m2.metric("Kc factor", f"{factor:.3f}")
m3.metric("Final Kc", f"{kc_adj:.3f}")
m4.metric("ET₀", f"{et0_today:.2f} mm/day")
m5.metric("Potential ETc", f"{etc:.2f} mm/day")

st.session_state.update(
    {
        "stage": stage,
        "base_kc": base_kc,
        "ndvi": ndvi,
        "kc_adj": kc_adj,
        "etc_potential_today": etc,
        "ndvi_alpha": alpha,
        "ndvi_mode": mode,
    }
)

st.caption(
    "Automatic NDVI is a Sentinel-2 satellite observation. "
    "The acquisition date is shown because it can differ from the evaluation date."
)
