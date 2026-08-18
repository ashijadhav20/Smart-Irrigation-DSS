import math

def area_from_shape(shape, **kwargs):
    if shape == "Rectangle":
        return kwargs["length"] * kwargs["width"]
    if shape == "Square":
        return kwargs["side"] ** 2
    if shape == "Circle":
        return math.pi * kwargs["radius"] ** 2
    if shape == "Triangle":
        return 0.5 * kwargs["base"] * kwargs["height"]
    if shape == "Trapezoid":
        return 0.5 * (kwargs["a"] + kwargs["b"]) * kwargs["height"]
    return 0.0

def water_litres(depth_mm, area_m2, application_efficiency_pct=100.0):
    # 1 mm over 1 m² = 1 litre.
    eff = max(application_efficiency_pct / 100.0, 0.01)
    return float(depth_mm * area_m2 / eff)
