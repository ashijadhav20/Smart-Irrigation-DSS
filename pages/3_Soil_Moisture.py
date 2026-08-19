import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.ui import inject_css, hero, require_inputs
from core.data import SOILS, CROPS
from core.weather import (
    fetch_openmeteo_soil,
    current_soil_moisture,
    daily_root_zone_soil_moisture,
    daily_soil_moisture_by_depth,
    soil_moisture_depletion_rate_by_depth,
    volumetric_to_percent,
    add_percent_columns,
)
from core.soil_water import water_balance_metrics, forecast_depletion

st.set_page_config(
    page_title="Soil Moisture | Irrigation DSS",
    page_icon="💧",
    layout="wide",
)

inject_css()
hero("Page 4 • Soil moisture by depth, crop root zone and irrigation-threshold forecast")
require_inputs()

soil = SOILS[st.session_state.soil_type]
crop = CROPS[st.session_state.crop]

# Crop database already contains crop-specific effective root depth.
database_root_depth = float(crop["root_depth_m"])

st.markdown("### 🌱 Crop root-zone information")

r1, r2, r3 = st.columns(3)
r1.metric("Selected crop", st.session_state.crop)
r2.metric("Database root depth", f"{database_root_depth:.2f} m")
r3.metric("Database root depth", f"{database_root_depth * 100:.0f} cm")

st.caption(
    "The crop database provides the initial effective root depth used for root-zone "
    "soil-water calculations. You may adjust it below when local crop stage, soil, "
    "cultivar or field observations justify a different effective rooting depth."
)

root_depth = st.slider(
    "Effective crop root depth used for irrigation calculation (m)",
    0.10,
    1.50,
    database_root_depth,
    0.05,
)

p = st.slider(
    "Management depletion fraction p",
    0.10,
    0.80,
    float(crop["p"]),
    0.05,
)

source = st.radio(
    "Soil-moisture source",
    ["Location-based model estimate", "Manual / field sensor value"],
    horizontal=True,
)

if "weather_daily" not in st.session_state:
    st.info("Open the Weather page first so OpenWeather forecast data are available.")
    st.stop()

daily_weather = st.session_state["weather_daily"]

try:
    soil_hourly, _ = fetch_openmeteo_soil(
        st.session_state.latitude,
        st.session_state.longitude,
        st.session_state.get("forecast_days", 7),
    )
    st.session_state["soil_hourly_openmeteo"] = soil_hourly
except Exception as exc:
    st.error(f"Open-Meteo soil-moisture service could not be reached: {exc}")
    st.stop()

# ---------------------------------------------------------
# Current profile: scientific unit + farmer-friendly %
# ---------------------------------------------------------
st.markdown("### 🌍 Current soil moisture at different depths")

current_layers = current_soil_moisture(soil_hourly)

if current_layers:
    profile_df = pd.DataFrame(
        {
            "Depth": list(current_layers.keys()),
            "Soil moisture (m³/m³)": list(current_layers.values()),
            "Soil moisture (%)": [
                volumetric_to_percent(v)
                for v in current_layers.values()
            ],
        }
    )

    # Format the table but keep the raw dataframe for plotting.
    st.dataframe(
        profile_df.style.format(
            {
                "Soil moisture (m³/m³)": "{:.3f}",
                "Soil moisture (%)": "{:.1f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "Farmer-friendly conversion: **soil moisture (%) = soil moisture (m³/m³) × 100**. "
        "For example, 0.25 m³/m³ = 25% volumetric soil moisture."
    )

    fig_profile = go.Figure()
    fig_profile.add_trace(
        go.Bar(
            x=profile_df["Depth"],
            y=profile_df["Soil moisture (%)"],
            name="Current soil moisture",
        )
    )
    fig_profile.update_layout(
        title="Current model-estimated soil-moisture profile",
        xaxis_title="Soil depth",
        yaxis_title="Volumetric soil moisture (%)",
    )
    st.plotly_chart(fig_profile, use_container_width=True)

st.caption(
    "The percentage shown above is volumetric water content expressed as percent. "
    "It is different from 'available water remaining (%)', which depends on field capacity, "
    "permanent wilting point and crop root depth."
)

# ---------------------------------------------------------
# Depth-wise daily trend in farmer-friendly %
# ---------------------------------------------------------
daily_depth = daily_soil_moisture_by_depth(soil_hourly)
daily_depth_pct = add_percent_columns(daily_depth)

if not daily_depth_pct.empty:
    st.markdown("### 📈 Soil-moisture trend at different depths")

    fig_depth = go.Figure()
    for col in [c for c in daily_depth_pct.columns if c != "date"]:
        fig_depth.add_trace(
            go.Scatter(
                x=daily_depth_pct["date"],
                y=daily_depth_pct[col],
                mode="lines+markers",
                name=col,
            )
        )

    fig_depth.update_layout(
        title="Daily Open-Meteo soil moisture by depth",
        xaxis_title="Date",
        yaxis_title="Volumetric soil moisture (%)",
        legend_title="Depth",
    )
    st.plotly_chart(fig_depth, use_container_width=True)

    # Depletion/recharge: convert m3/m3/day to percentage-points/day.
    depletion_depth = soil_moisture_depletion_rate_by_depth(daily_depth)
    depletion_pct = depletion_depth.copy()

    for col in [c for c in depletion_pct.columns if c != "date"]:
        depletion_pct[col] = depletion_pct[col].astype(float) * 100.0

    st.markdown("### 📉 Soil-moisture depletion / recharge rate by depth")

    fig_dep = go.Figure()
    for col in [c for c in depletion_pct.columns if c != "date"]:
        fig_dep.add_trace(
            go.Scatter(
                x=depletion_pct["date"],
                y=depletion_pct[col],
                mode="lines+markers",
                name=col,
            )
        )

    fig_dep.add_hline(
        y=0,
        line_dash="dash",
        annotation_text="0 = no daily change",
    )

    fig_dep.update_layout(
        title="Day-to-day soil-moisture change at different depths",
        xaxis_title="Date",
        yaxis_title="Change in volumetric soil moisture (percentage points/day)",
        legend_title="Depth",
    )
    st.plotly_chart(fig_dep, use_container_width=True)

    st.caption(
        "Positive values indicate drying/depletion from the previous day. "
        "Negative values indicate wetting/recharge, such as after rainfall."
    )

# ---------------------------------------------------------
# Root-zone moisture - crop/root depth explicitly used
# ---------------------------------------------------------
st.markdown("### 🌾 Root-zone soil moisture used for water-requirement calculation")

rz = daily_root_zone_soil_moisture(
    soil_hourly,
    root_depth,
)

api_theta = (
    float(rz.iloc[0]["root_zone_theta"])
    if len(rz) and pd.notna(rz.iloc[0]["root_zone_theta"])
    else soil["fc"]
)

if source == "Location-based model estimate":
    theta = api_theta
else:
    theta = st.number_input(
        "Current volumetric soil moisture (m³/m³)",
        min_value=0.01,
        max_value=0.70,
        value=float(min(max(api_theta, 0.01), 0.70)),
        step=0.01,
    )

theta_pct = volumetric_to_percent(theta)
fc_pct = volumetric_to_percent(soil["fc"])
pwp_pct = volumetric_to_percent(soil["pwp"])

metrics = water_balance_metrics(
    theta,
    soil["fc"],
    soil["pwp"],
    root_depth,
    p,
)

a1, a2, a3, a4 = st.columns(4)
a1.metric(
    "Root-zone soil moisture",
    f"{theta_pct:.1f}%",
    f"{theta:.3f} m³/m³",
)
a2.metric(
    "Field capacity",
    f"{fc_pct:.1f}%",
    f"{soil['fc']:.3f} m³/m³",
)
a3.metric(
    "Permanent wilting point",
    f"{pwp_pct:.1f}%",
    f"{soil['pwp']:.3f} m³/m³",
)
a4.metric(
    "Available water remaining",
    f"{metrics['available_water_pct']:.0f}%",
)

b1, b2, b3 = st.columns(3)
b1.metric("Current depletion Dr", f"{metrics['Dr_mm']:.1f} mm")
b2.metric("TAW", f"{metrics['TAW_mm']:.1f} mm")
b3.metric("RAW irrigation threshold", f"{metrics['RAW_mm']:.1f} mm")

st.caption(
    f"Water-requirement root zone used: **{root_depth:.2f} m ({root_depth*100:.0f} cm)**. "
    "The model combines the available Open-Meteo soil layers within this effective root zone."
)

if metrics["status"] == "Irrigation required":
    st.error(
        "🔴 Irrigation required: current root-zone depletion has reached/exceeded RAW."
    )
elif metrics["status"] == "Approaching irrigation threshold":
    st.warning(
        "🟡 Root-zone depletion is approaching the irrigation threshold."
    )
else:
    st.success(
        "🟢 Root-zone water is currently adequate. This root-zone moisture state is "
        "used directly in irrigation scheduling."
    )

# ---------------------------------------------------------
# Root-zone forecast
# ---------------------------------------------------------
kc_adj = float(
    st.session_state.get(
        "kc_adj",
        st.session_state.get("base_kc", 1.0),
    )
)

forecast = forecast_depletion(
    theta,
    soil["fc"],
    soil["pwp"],
    root_depth,
    p,
    daily_weather,
    kc_adj,
    effective_rain_fraction=st.session_state.get("rain_eff_pct", 80) / 100.0,
)

theta_raw = (
    soil["fc"]
    - metrics["RAW_mm"] / (1000.0 * root_depth)
)

fig = go.Figure()

fig.add_trace(
    go.Scatter(
        x=forecast["date"],
        y=forecast["soil_moisture"] * 100.0,
        mode="lines+markers",
        name="Root-zone soil moisture",
    )
)

fig.add_hline(
    y=soil["fc"] * 100.0,
    line_dash="dash",
    annotation_text="Field capacity",
)
fig.add_hline(
    y=theta_raw * 100.0,
    line_dash="dash",
    annotation_text="Irrigation threshold",
)
fig.add_hline(
    y=soil["pwp"] * 100.0,
    line_dash="dash",
    annotation_text="Permanent wilting point",
)

fig.update_layout(
    title="Forecast root-zone soil moisture used by irrigation DSS",
    xaxis_title="Date",
    yaxis_title="Volumetric soil moisture (%)",
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# Combined depletion decision graph: Dr + RAW + trigger point
# ---------------------------------------------------------
st.markdown("### 🚦 Root-zone depletion decision graph")

st.caption(
    "This graph combines the forecast root-zone depletion (Dr) with the crop/soil "
    "Readily Available Water (RAW) threshold. Irrigation becomes due when Dr reaches "
    "or exceeds RAW. TAW is also shown as the total available-water limit."
)

# Include today's/current depletion as the first point so the graph starts from the
# actual root-zone condition before moving through the weather forecast.
current_date = pd.Timestamp.now().normalize()
if len(forecast):
    try:
        first_forecast_date = pd.to_datetime(forecast.iloc[0]["date"])
        current_date = first_forecast_date.normalize() - pd.Timedelta(days=1)
    except Exception:
        pass

decision_df = pd.DataFrame(
    {
        "date": [current_date] + list(pd.to_datetime(forecast["date"])),
        "depletion_mm": [float(metrics["Dr_mm"])] + list(forecast["depletion_mm"].astype(float)),
    }
)

raw_mm = float(metrics["RAW_mm"])
taw_mm = float(metrics["TAW_mm"])

fig_decision = go.Figure()
fig_decision.add_trace(
    go.Scatter(
        x=decision_df["date"],
        y=decision_df["depletion_mm"],
        mode="lines+markers",
        name="Root-zone depletion (Dr)",
        line=dict(width=4),
        marker=dict(size=8),
        hovertemplate="%{x|%d %b %Y}<br>Dr = %{y:.1f} mm<extra></extra>",
    )
)

fig_decision.add_hline(
    y=raw_mm,
    line_dash="dash",
    line_width=3,
    annotation_text=f"RAW irrigation threshold = {raw_mm:.1f} mm",
    annotation_position="top left",
)
fig_decision.add_hline(
    y=taw_mm,
    line_dash="dot",
    line_width=2,
    annotation_text=f"TAW = {taw_mm:.1f} mm",
    annotation_position="bottom left",
)

# Highlight the first forecast point that reaches RAW.
trigger_rows = forecast.loc[forecast["threshold_crossed"]].copy()
if len(trigger_rows):
    trigger = trigger_rows.iloc[0]
    trigger_date = pd.to_datetime(trigger["date"])
    trigger_dr = float(trigger["depletion_mm"])
    fig_decision.add_trace(
        go.Scatter(
            x=[trigger_date],
            y=[trigger_dr],
            mode="markers+text",
            name="Irrigation trigger",
            marker=dict(size=16, symbol="diamond"),
            text=["IRRIGATE"],
            textposition="top center",
            hovertemplate=(
                "%{x|%d %b %Y}<br>Threshold crossed<br>Dr = %{y:.1f} mm"
                "<extra></extra>"
            ),
        )
    )

# Shade the management zones to make the decision visually immediate.
fig_decision.add_hrect(
    y0=0,
    y1=raw_mm,
    opacity=0.08,
    line_width=0,
    annotation_text="Within readily available water",
    annotation_position="inside bottom right",
)
if taw_mm > raw_mm:
    fig_decision.add_hrect(
        y0=raw_mm,
        y1=taw_mm,
        opacity=0.08,
        line_width=0,
        annotation_text="Irrigation / stress-risk zone",
        annotation_position="inside top right",
    )

fig_decision.update_layout(
    title="Root-zone depletion (Dr) versus RAW irrigation threshold",
    xaxis_title="Date",
    yaxis_title="Root-zone depletion, Dr (mm)",
    hovermode="x unified",
    legend_title="Decision layers",
)
fig_decision.update_yaxes(range=[0, max(taw_mm * 1.08, decision_df["depletion_mm"].max() * 1.12, 1.0)])

st.plotly_chart(fig_decision, use_container_width=True)

current_ratio = (metrics["Dr_mm"] / raw_mm * 100.0) if raw_mm > 0 else 0.0
d1, d2, d3 = st.columns(3)
d1.metric("Current Dr", f"{metrics['Dr_mm']:.1f} mm")
d2.metric("RAW trigger", f"{raw_mm:.1f} mm")
d3.metric("Dr / RAW", f"{current_ratio:.0f}%")

if metrics["Dr_mm"] >= raw_mm:
    st.error(
        "🔴 **IRRIGATION TRIGGERED NOW:** current root-zone depletion (Dr) is at or above RAW."
    )
elif len(trigger_rows):
    trigger = trigger_rows.iloc[0]
    st.warning(
        f"🟡 **Forecast trigger:** Dr is expected to reach RAW on "
        f"**{pd.to_datetime(trigger['date']).date()}** (forecast-based)."
    )
else:
    st.success(
        "🟢 **No RAW crossing in the current forecast horizon.** Root-zone depletion remains below the irrigation trigger."
    )

cross = forecast.loc[forecast["threshold_crossed"]]

if len(cross):
    first = cross.iloc[0]
    st.warning(
        f"Forecast irrigation threshold crossing: **{first['date'].date()}** "
        f"at approximately {first['soil_moisture']*100:.1f}% root-zone soil moisture."
    )
else:
    st.success(
        "The irrigation threshold is not crossed within the current forecast horizon."
    )

# Save all values for irrigation page and summary.
st.session_state.update(
    {
        "soil_theta": theta,
        "soil_theta_pct": theta_pct,
        "root_depth_m": root_depth,
        "root_depth_database_m": database_root_depth,
        "depletion_fraction": p,
        "soil_metrics": metrics,
        "soil_forecast": forecast,
        "soil_depth_daily": daily_depth,
        "soil_depth_daily_pct": daily_depth_pct,
        "soil_profile_current": current_layers,
    }
)
