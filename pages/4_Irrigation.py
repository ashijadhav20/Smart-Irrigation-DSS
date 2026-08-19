import streamlit as st

from core.ui import inject_css, hero, require_inputs
from core.data import SOILS
from core.soil_water import irrigation_decision

st.set_page_config(
    page_title="Irrigation | Irrigation DSS",
    page_icon="🚿",
    layout="wide",
)

inject_css()
hero("Page 5 • Soil-moisture-aware irrigation decision and water requirement")
require_inputs()

required = ["soil_metrics", "soil_theta", "root_depth_m", "soil_forecast"]
missing = [x for x in required if x not in st.session_state]

if missing:
    st.info(
        "Open the **Soil Moisture** page first. "
        "Irrigation scheduling requires the current root-zone soil-moisture estimate."
    )
    st.stop()

soil = SOILS[st.session_state.soil_type]
theta = float(st.session_state["soil_theta"])
zr = float(st.session_state["root_depth_m"])
p = float(st.session_state["depletion_fraction"])
area = float(st.session_state["area_m2"])
eff = float(st.session_state.get("efficiency_pct", 80))

st.markdown("### 💧 Current root-zone water status")

target = st.slider(
    "Refill target (% of field capacity)",
    80,
    100,
    100,
    help="If irrigation is triggered, water is calculated to refill the current root-zone deficit to this target.",
)

decision = irrigation_decision(
    theta=theta,
    fc=soil["fc"],
    pwp=soil["pwp"],
    root_depth_m=zr,
    depletion_fraction=p,
    area_m2=area,
    application_efficiency_pct=eff,
    target_fraction_of_fc=target / 100.0,
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Current root-zone soil moisture", f"{theta*100:.1f}%", f"{theta:.3f} m³/m³")
m2.metric("Current depletion Dr", f"{decision['Dr_mm']:.1f} mm")
m3.metric("RAW trigger", f"{decision['RAW_mm']:.1f} mm")
m4.metric("Available water", f"{decision['available_water_pct']:.0f}%")

st.caption(
    f"Soil type: {st.session_state.soil_type} • "
    f"FC = {soil['fc']:.3f} m³/m³ • "
    f"PWP = {soil['pwp']:.3f} m³/m³ • "
    f"Root depth used = {zr:.2f} m ({zr*100:.0f} cm)"
)

st.info(
    f"Scheduling is crop-root-zone based: **{st.session_state.crop}** is currently "
    f"evaluated with an effective root depth of **{zr:.2f} m ({zr*100:.0f} cm)**. "
    "Current root-zone soil moisture is converted to depletion and compared with RAW."
)

if decision["triggered"]:
    st.error(
        f"🚿 Irrigation is required because current depletion "
        f"({decision['Dr_mm']:.1f} mm) has reached/exceeded RAW "
        f"({decision['RAW_mm']:.1f} mm)."
    )

    a, b, c = st.columns(3)
    a.metric("Net refill depth", f"{decision['net_depth_mm']:.1f} mm")
    b.metric("Gross depth after efficiency", f"{decision['gross_depth_mm']:.1f} mm")
    c.metric("Water to apply", f"{decision['water_litres']:,.0f} L")

else:
    remaining = max(0.0, decision["RAW_mm"] - decision["Dr_mm"])

    if decision["status"] == "Approaching irrigation threshold":
        st.warning(
            f"🟡 Irrigation is not required yet, but the root-zone depletion is close to RAW. "
            f"About {remaining:.1f} mm of additional depletion remains."
        )
    else:
        st.success(
            f"🟢 Irrigation is not required now. "
            f"About {remaining:.1f} mm of additional root-zone depletion remains before RAW."
        )

    st.metric("Water to apply now", "0 L")

st.markdown("### 📅 Forecast irrigation timing")

forecast = st.session_state["soil_forecast"].copy()
cross = forecast.loc[forecast["threshold_crossed"]]

if len(cross):
    first = cross.iloc[0]

    st.warning(
        f"Based on forecast ETc and effective rainfall, the soil-water threshold is "
        f"first projected to be crossed on **{first['date'].date()}**."
    )

    st.caption(
        f"Forecast depletion on that date: {first['depletion_mm']:.1f} mm • "
        f"Forecast soil moisture: {first['soil_moisture']:.3f} m³/m³ • "
        f"Forecast effective rain: {first['effective_rain_mm']:.1f} mm."
    )
else:
    st.success(
        "The RAW irrigation threshold is not projected to be crossed within the current forecast horizon."
    )

with st.expander("Show daily soil-water balance"):
    cols = [
        "date",
        "ET0_mm",
        "ETc_potential_mm",
        "ETc_actual_mm",
        "rain_mm",
        "effective_rain_mm",
        "depletion_mm",
        "soil_moisture",
        "remaining_to_RAW_mm",
        "threshold_crossed",
    ]
    st.dataframe(
        forecast[cols],
        use_container_width=True,
        hide_index=True,
    )

st.session_state["recommended_irrigation_mm"] = decision["gross_depth_mm"]
st.session_state["recommended_water_l"] = decision["water_litres"]
st.session_state["irrigation_decision"] = decision

st.caption(
    "Scheduling logic explicitly uses current root-zone soil moisture. "
    "ETc determines crop water use, rainfall reduces depletion, and irrigation is triggered when "
    "root-zone depletion reaches the management-allowable depletion (RAW) threshold."
)
