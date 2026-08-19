from datetime import date
import numpy as np
from .data import CROPS, NDVI_ALPHA_BY_CROP

def crop_stage_and_kc(crop: str, sowing_date: date, evaluation_date: date):
    d = CROPS[crop]
    L_ini, L_dev, L_mid, L_late = d["stage_days"]
    kc_ini, kc_mid, kc_end = d["kc"]
    dap = max(0, (evaluation_date - sowing_date).days)
    if dap <= L_ini: return "Initial", float(kc_ini), dap
    if dap <= L_ini + L_dev:
        f = (dap - L_ini) / max(L_dev, 1)
        return "Development", float(kc_ini + f*(kc_mid-kc_ini)), dap
    if dap <= L_ini + L_dev + L_mid: return "Mid-season", float(kc_mid), dap
    if dap <= L_ini + L_dev + L_mid + L_late:
        f = (dap-L_ini-L_dev-L_mid)/max(L_late,1)
        return "Late-season", float(kc_mid + f*(kc_end-kc_mid)), dap
    return "Beyond configured season", float(kc_end), dap

def expected_ndvi_for_stage(stage: str):
    # Generic stage reference used only for relative canopy correction, not a crop identity model.
    return {"Initial":0.25,"Development":0.50,"Mid-season":0.75,"Late-season":0.55,"Beyond configured season":0.35}.get(stage,0.50)

def crop_specific_alpha(crop: str):
    return float(NDVI_ALPHA_BY_CROP.get(crop, 0.30))

def ndvi_stage_relative_kc(crop: str, base_kc: float, ndvi: float, stage: str, alpha=None):
    """Research-mode correction; not a universal FAO equation or universal crop calibration."""
    if alpha is None: alpha = crop_specific_alpha(crop)
    expected = expected_ndvi_for_stage(stage)
    factor = float(np.clip(1.0 + float(alpha)*(float(ndvi)-expected), 0.75, 1.25))
    return float(np.clip(base_kc*factor, 0.15, 1.50)), factor, expected

def linear_calibrated_kc(ndvi: float, slope: float, intercept: float, minimum=0.15, maximum=1.50):
    """Direct Kc=a*NDVI+b for user/literature/local crop calibration."""
    raw = float(slope)*float(ndvi)+float(intercept)
    return float(np.clip(raw, minimum, maximum)), raw
