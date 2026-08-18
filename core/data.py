# Configurable research database.
# Crop coefficients are representative starting values based on common FAO-56 style staging.
# Validate and locally calibrate values before publication or operational recommendations.

SOILS = {
    "Sand": {"fc": 0.12, "pwp": 0.05, "infiltration_mm_h": 25.0},
    "Loamy sand": {"fc": 0.15, "pwp": 0.06, "infiltration_mm_h": 20.0},
    "Sandy loam": {"fc": 0.20, "pwp": 0.08, "infiltration_mm_h": 15.0},
    "Loam": {"fc": 0.28, "pwp": 0.12, "infiltration_mm_h": 10.0},
    "Silt loam": {"fc": 0.31, "pwp": 0.13, "infiltration_mm_h": 8.0},
    "Silt": {"fc": 0.30, "pwp": 0.11, "infiltration_mm_h": 8.0},
    "Sandy clay loam": {"fc": 0.27, "pwp": 0.15, "infiltration_mm_h": 6.0},
    "Clay loam": {"fc": 0.34, "pwp": 0.18, "infiltration_mm_h": 5.0},
    "Silty clay loam": {"fc": 0.36, "pwp": 0.20, "infiltration_mm_h": 4.0},
    "Sandy clay": {"fc": 0.33, "pwp": 0.20, "infiltration_mm_h": 3.5},
    "Silty clay": {"fc": 0.39, "pwp": 0.23, "infiltration_mm_h": 3.0},
    "Clay": {"fc": 0.40, "pwp": 0.24, "infiltration_mm_h": 2.5},
}

# stage_days = [initial, development, mid, late]
# kc = [initial, mid, end]; root_depth_m and depletion_fraction p are starting defaults.
CROPS = {
    "Rice":       {"stage_days":[30,30,60,30], "kc":[1.05,1.20,0.90], "root_depth_m":0.60, "p":0.20},
    "Wheat":      {"stage_days":[20,30,40,30], "kc":[0.40,1.15,0.35], "root_depth_m":1.00, "p":0.55},
    "Maize":      {"stage_days":[20,35,40,30], "kc":[0.30,1.20,0.60], "root_depth_m":1.00, "p":0.55},
    "Groundnut":  {"stage_days":[25,35,45,25], "kc":[0.40,1.15,0.60], "root_depth_m":0.70, "p":0.50},
    "Soybean":    {"stage_days":[20,30,60,25], "kc":[0.40,1.15,0.50], "root_depth_m":0.80, "p":0.50},
    "Mustard":    {"stage_days":[20,30,35,25], "kc":[0.35,1.10,0.35], "root_depth_m":0.90, "p":0.45},
    "Chickpea":   {"stage_days":[20,30,45,25], "kc":[0.40,1.00,0.35], "root_depth_m":0.90, "p":0.50},
    "Tomato":     {"stage_days":[30,40,45,30], "kc":[0.60,1.15,0.80], "root_depth_m":0.70, "p":0.40},
    "Potato":     {"stage_days":[25,30,45,30], "kc":[0.50,1.15,0.75], "root_depth_m":0.60, "p":0.35},
    "Onion":      {"stage_days":[20,35,55,30], "kc":[0.70,1.05,0.75], "root_depth_m":0.40, "p":0.30},
    "Cabbage":    {"stage_days":[20,30,40,15], "kc":[0.70,1.05,0.95], "root_depth_m":0.50, "p":0.45},
    "Cauliflower":{"stage_days":[20,30,40,20], "kc":[0.70,1.05,0.95], "root_depth_m":0.50, "p":0.45},
    "Brinjal":    {"stage_days":[30,40,60,30], "kc":[0.60,1.05,0.90], "root_depth_m":0.70, "p":0.45},
    "Chilli":     {"stage_days":[30,40,80,30], "kc":[0.60,1.05,0.90], "root_depth_m":0.70, "p":0.40},
    "Okra":       {"stage_days":[20,30,50,20], "kc":[0.50,1.00,0.80], "root_depth_m":0.70, "p":0.45},
    "Cucumber":   {"stage_days":[20,30,40,15], "kc":[0.60,1.00,0.75], "root_depth_m":0.50, "p":0.50},
    "Watermelon": {"stage_days":[20,30,30,30], "kc":[0.40,1.00,0.75], "root_depth_m":0.80, "p":0.40},
    "Banana":     {"stage_days":[120,90,120,60], "kc":[0.50,1.10,1.00], "root_depth_m":0.90, "p":0.35},
    "Sugarcane":  {"stage_days":[35,60,190,120], "kc":[0.40,1.25,0.75], "root_depth_m":1.20, "p":0.65},
    "Cotton":     {"stage_days":[30,50,60,55], "kc":[0.35,1.15,0.50], "root_depth_m":1.00, "p":0.65},
}
