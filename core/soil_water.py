from __future__ import annotations

import numpy as np
import pandas as pd


def water_balance_metrics(theta, fc, pwp, root_depth_m, depletion_fraction):
    theta = float(theta)
    fc = float(fc)
    pwp = float(pwp)
    zr = float(root_depth_m)
    p = float(depletion_fraction)

    taw = max(0.0, 1000.0 * (fc - pwp) * zr)
    raw = max(0.0, p * taw)

    # Soil wetter than FC is treated as zero depletion; soil drier than PWP is capped at TAW.
    dr = float(np.clip(1000.0 * (fc - theta) * zr, 0.0, taw))

    available_remaining = max(0.0, taw - dr)
    aw_pct = 100.0 * available_remaining / taw if taw > 0 else 0.0

    if dr <= raw:
        ks = 1.0
    else:
        ks = float(np.clip((taw - dr) / max(taw - raw, 1e-9), 0.0, 1.0))

    trigger_ratio = dr / raw if raw > 0 else 0.0

    if dr >= raw:
        status = "Irrigation required"
    elif trigger_ratio >= 0.80:
        status = "Approaching irrigation threshold"
    else:
        status = "Adequate"

    return {
        "TAW_mm": float(taw),
        "RAW_mm": float(raw),
        "Dr_mm": float(dr),
        "available_water_pct": float(aw_pct),
        "Ks": float(ks),
        "status": status,
        "trigger_ratio": float(trigger_ratio),
    }


def target_refill_depth_mm(theta, fc, root_depth_m, target_fraction_of_fc=1.0):
    target_theta = float(fc) * float(target_fraction_of_fc)
    return max(
        0.0,
        1000.0 * (target_theta - float(theta)) * float(root_depth_m),
    )


def forecast_depletion(
    start_theta,
    fc,
    pwp,
    root_depth_m,
    depletion_fraction,
    daily_weather: pd.DataFrame,
    kc_adjusted,
    effective_rain_fraction=0.80,
):
    """
    Daily soil-water balance forecast.

    Dr(t+1) = Dr(t) + ETc_actual - effective rainfall

    The current soil moisture determines initial depletion.
    ET0 + Kc determine crop use.
    Rainfall reduces depletion.
    Ks reduces ETc when the root zone is already water-stressed.

    Irrigation is not automatically inserted into the forecast; the first RAW
    threshold crossing is reported so the DSS can advise when irrigation is due.
    """
    metrics = water_balance_metrics(
        start_theta,
        fc,
        pwp,
        root_depth_m,
        depletion_fraction,
    )

    dr = metrics["Dr_mm"]
    taw = metrics["TAW_mm"]
    raw = metrics["RAW_mm"]

    rows = []

    for _, r in daily_weather.iterrows():
        et0 = float(r.get("et0_fao_evapotranspiration", 0.0) or 0.0)
        rain = float(r.get("precipitation_sum", 0.0) or 0.0)

        if dr <= raw:
            ks = 1.0
        else:
            ks = float(
                np.clip(
                    (taw - dr) / max(taw - raw, 1e-9),
                    0.0,
                    1.0,
                )
            )

        etc_potential = et0 * float(kc_adjusted)
        etc_actual = etc_potential * ks
        effective_rain = rain * float(effective_rain_fraction)

        dr = float(
            np.clip(
                dr + etc_actual - effective_rain,
                0.0,
                taw,
            )
        )

        theta = float(
            fc - dr / max(1000.0 * root_depth_m, 1e-9)
        )
        theta = float(np.clip(theta, pwp, fc))

        rows.append({
            "date": r["time"],
            "ET0_mm": et0,
            "ETc_potential_mm": etc_potential,
            "Ks": ks,
            "ETc_actual_mm": etc_actual,
            "rain_mm": rain,
            "effective_rain_mm": effective_rain,
            "depletion_mm": dr,
            "soil_moisture": theta,
            "threshold_crossed": bool(dr >= raw),
            "remaining_to_RAW_mm": max(0.0, raw - dr),
        })

    return pd.DataFrame(rows)


def irrigation_decision(
    theta,
    fc,
    pwp,
    root_depth_m,
    depletion_fraction,
    area_m2,
    application_efficiency_pct,
    target_fraction_of_fc=1.0,
):
    """
    Current irrigation decision explicitly driven by root-zone soil moisture.

    Trigger:
      current root-zone depletion Dr >= RAW.

    Amount:
      refill current root-zone soil deficit to the selected target fraction of FC,
      then correct for application efficiency.
    """
    metrics = water_balance_metrics(
        theta,
        fc,
        pwp,
        root_depth_m,
        depletion_fraction,
    )

    triggered = metrics["Dr_mm"] >= metrics["RAW_mm"]

    net_depth = (
        target_refill_depth_mm(
            theta,
            fc,
            root_depth_m,
            target_fraction_of_fc,
        )
        if triggered
        else 0.0
    )

    efficiency = max(float(application_efficiency_pct) / 100.0, 0.01)
    gross_depth = net_depth / efficiency
    litres = gross_depth * float(area_m2)  # 1 mm over 1 m2 = 1 L

    return {
        "triggered": bool(triggered),
        "net_depth_mm": float(net_depth),
        "gross_depth_mm": float(gross_depth),
        "water_litres": float(litres),
        **metrics,
    }
