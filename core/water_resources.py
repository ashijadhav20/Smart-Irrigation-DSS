from __future__ import annotations

from datetime import date, datetime, timedelta
import math

from .gee_ndvi import initialize_ee, S2_COLLECTION, _clear_mask


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _search_scale(radius_m: float) -> int:
    r = float(radius_m)
    if r <= 3000:
        return 10
    if r <= 7000:
        return 20
    if r <= 12000:
        return 30
    return 40


def detect_nearby_water_bodies(
    latitude,
    longitude,
    evaluation_date,
    radius_km=5.0,
    lookback_days=90,
    cloud_limit=70,
    method="Combined NDWI + MNDWI",
    mndwi_threshold=0.0,
    ndwi_threshold=0.0,
    ndvi_max=0.35,
    min_area_ha=0.05,
    max_results=25,
):
    """Detect open-water surfaces around a field using Sentinel-2 SR.

    Remote sensing returns water-surface extent/area. It does not measure water depth.
    Storage volume must therefore be calculated separately from measured/assumed mean depth.
    """
    ee = initialize_ee()
    lat = float(latitude); lon = float(longitude)
    radius_m = max(250.0, min(20000.0, float(radius_km) * 1000.0))
    scale = _search_scale(radius_m)
    end = _to_date(evaluation_date)
    start = end - timedelta(days=max(14, min(365, int(lookback_days))))
    roi = ee.Geometry.Point([lon, lat]).buffer(radius_m)

    collection = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(roi)
        .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", int(cloud_limit)))
    )
    scene_count = int(collection.size().getInfo())
    fallback_used = False
    if scene_count == 0:
        start = end - timedelta(days=180)
        collection = (
            ee.ImageCollection(S2_COLLECTION)
            .filterBounds(roi)
            .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", max(int(cloud_limit), 90)))
        )
        scene_count = int(collection.size().getInfo())
        fallback_used = True
    if scene_count == 0:
        raise RuntimeError("No Sentinel-2 surface-reflectance scenes were available for this search area/date window.")

    def prep(image):
        return image.updateMask(_clear_mask(image)).select(["B3", "B4", "B8", "B11"])

    composite = collection.map(prep).median().clip(roi)
    ndwi = composite.normalizedDifference(["B3", "B8"]).rename("NDWI")
    mndwi = composite.normalizedDifference(["B3", "B11"]).rename("MNDWI")
    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")

    method_l = str(method).lower()
    if method_l.startswith("mndwi"):
        water = mndwi.gt(float(mndwi_threshold)).And(ndvi.lt(float(ndvi_max)))
    elif method_l.startswith("ndwi"):
        water = ndwi.gt(float(ndwi_threshold)).And(ndvi.lt(float(ndvi_max)))
    else:
        # Conservative consensus mask: both water indices positive/above threshold,
        # while NDVI suppresses dense vegetation false positives.
        water = (
            mndwi.gt(float(mndwi_threshold))
            .And(ndwi.gt(float(ndwi_threshold)))
            .And(ndvi.lt(float(ndvi_max)))
        )

    # Add pixel area as the data band so reduceToVectors can sum true raster area
    # without connectedPixelCount segment-size limitations.
    label = water.selfMask().rename("water_label").toInt()
    vector_image = label.addBands(ee.Image.pixelArea().rename("pixel_area_m2"))
    vectors = vector_image.reduceToVectors(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale=scale,
        geometryType="polygon",
        eightConnected=True,
        labelProperty="water_class",
        bestEffort=True,
        maxPixels=1e8,
        tileScale=2,
    )

    min_area_m2 = max(100.0, float(min_area_ha) * 10000.0)
    center = ee.Geometry.Point([lon, lat])
    indices = ndwi.addBands(mndwi).addBands(ndvi)

    def enrich(feature):
        geom = feature.geometry()
        area = geom.area(maxError=10)
        centroid = geom.centroid(maxError=10)
        coords = centroid.coordinates()
        stats = indices.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=scale,
            bestEffort=True,
            maxPixels=1e7,
        )
        return feature.set({
            "area_m2": area,
            "area_ha": area.divide(10000),
            "distance_m": centroid.distance(center, maxError=10),
            "centroid_lon": coords.get(0),
            "centroid_lat": coords.get(1),
            "mean_ndwi": stats.get("NDWI"),
            "mean_mndwi": stats.get("MNDWI"),
            "mean_ndvi": stats.get("NDVI"),
        })

    enriched = (
        vectors.map(enrich)
        .filter(ee.Filter.gte("area_m2", min_area_m2))
        .sort("distance_m")
        .limit(max(1, min(50, int(max_results))))
    )
    info = enriched.getInfo()
    features = info.get("features", []) if info else []

    bodies = []
    for i, f in enumerate(features, start=1):
        p = f.get("properties", {}) or {}
        geom = f.get("geometry")
        if not geom:
            continue
        bodies.append({
            "id": i,
            "name": f"Water body {i}",
            "geometry": geom,
            "area_m2": float(p.get("area_m2", 0.0) or 0.0),
            "area_ha": float(p.get("area_ha", 0.0) or 0.0),
            "distance_km": float(p.get("distance_m", 0.0) or 0.0) / 1000.0,
            "centroid_lat": float(p.get("centroid_lat", lat) or lat),
            "centroid_lon": float(p.get("centroid_lon", lon) or lon),
            "mean_ndwi": None if p.get("mean_ndwi") is None else float(p.get("mean_ndwi")),
            "mean_mndwi": None if p.get("mean_mndwi") is None else float(p.get("mean_mndwi")),
            "mean_ndvi": None if p.get("mean_ndvi") is None else float(p.get("mean_ndvi")),
        })

    total_area_m2 = sum(x["area_m2"] for x in bodies)
    return {
        "water_bodies": bodies,
        "count": len(bodies),
        "total_area_m2": total_area_m2,
        "total_area_ha": total_area_m2 / 10000.0,
        "radius_km": radius_m / 1000.0,
        "scale_m": scale,
        "scene_count": scene_count,
        "date_start": start.isoformat(),
        "date_end": end.isoformat(),
        "method": method,
        "mndwi_threshold": float(mndwi_threshold),
        "ndwi_threshold": float(ndwi_threshold),
        "ndvi_max": float(ndvi_max),
        "min_area_ha": float(min_area_ha),
        "fallback_used": fallback_used,
    }
