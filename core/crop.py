from datetime import date
import numpy as np
from .data import CROPS

def crop_stage_and_kc(crop: str, sowing_date: date, evaluation_date: date):
    d = CROPS[crop]
    L_ini, L_dev, L_mid, L_late = d["stage_days"]
    kc_ini, kc_mid, kc_end = d["kc"]
    dap = max(0, (evaluation_date - sowing_date).days)

    if dap <= L_ini:
        return "Initial", float(kc_ini), dap
    if dap <= L_ini + L_dev:
        f = (dap - L_ini) / max(L_dev, 1)
        kc = kc_ini + f * (kc_mid - kc_ini)
        return "Development", float(kc), dap
    if dap <= L_ini + L_dev + L_mid:
        return "Mid-season", float(kc_mid), dap
    if dap <= L_ini + L_dev + L_mid + L_late:
        f = (dap - L_ini - L_dev - L_mid) / max(L_late, 1)
        kc = kc_mid + f * (kc_end - kc_mid)
        return "Late-season", float(kc), dap
    return "Beyond configured season", float(kc_end), dap

def expected_ndvi_for_stage(stage: str):
    return {
        "Initial": 0.25,
        "Development": 0.50,
        "Mid-season": 0.75,
        "Late-season": 0.55,
        "Beyond configured season": 0.35,
    }.get(stage, 0.50)

def ndvi_corrected_kc(base_kc: float, ndvi: float, stage: str, alpha: float = 0.35):
    """
    Empirical research correction, not a universal FAO equation.
    Kc_adj = Kc * [1 + alpha * (NDVI - expected_NDVI_stage)]
    """
    expected = expected_ndvi_for_stage(stage)
    factor = 1.0 + alpha * (ndvi - expected)
    factor = float(np.clip(factor, 0.75, 1.25))
    return float(np.clip(base_kc * factor, 0.15, 1.50)), factor
