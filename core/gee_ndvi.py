from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import os

PROJECT_DEFAULT = "ashijadhav20"
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"


def _secret(name, default=None):
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except Exception:
        return default


def initialize_ee():
    import ee

    project = str(_secret("GEE_PROJECT", PROJECT_DEFAULT))
    service_account = _secret("GEE_SERVICE_ACCOUNT")
    json_path = _secret("GEE_JSON_PATH")

    if service_account and json_path:
        path = os.path.expandvars(os.path.expanduser(str(json_path)))
        if not os.path.isfile(path):
            raise RuntimeError(
                f"GEE_JSON_PATH is not a valid JSON file: {path}. "
                "Use the complete JSON filename."
            )
        credentials = ee.ServiceAccountCredentials(str(service_account), path)
        ee.Initialize(credentials=credentials, project=project)
        return ee

    private_key = _secret("GEE_PRIVATE_KEY")
    private_key_id = _secret("GEE_PRIVATE_KEY_ID")
    client_id = _secret("GEE_CLIENT_ID")
    client_x509 = _secret("GEE_CLIENT_X509_CERT_URL")

    if service_account and private_key:
        from google.oauth2 import service_account as gsa

        key_data = {
            "type": "service_account",
            "project_id": project,
            "private_key_id": str(private_key_id or ""),
            "private_key": str(private_key).replace("\\n", "\n"),
            "client_email": str(service_account),
            "client_id": str(client_id or ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": str(client_x509 or ""),
            "universe_domain": "googleapis.com",
        }
        credentials = gsa.Credentials.from_service_account_info(
            key_data,
            scopes=[
                "https://www.googleapis.com/auth/earthengine",
                "https://www.googleapis.com/auth/cloud-platform",
            ],
        )
        ee.Initialize(credentials=credentials, project=project)
        return ee

    try:
        ee.Initialize(project=project)
        return ee
    except Exception as exc:
        raise RuntimeError(
            "Earth Engine credentials are not configured. Add GEE_PROJECT, "
            "GEE_SERVICE_ACCOUNT and GEE_JSON_PATH to .streamlit/secrets.toml."
        ) from exc


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def make_query_signature(latitude, longitude, evaluation_date, area_m2, field_geometry=None):
    d = _to_date(evaluation_date).isoformat()
    from .geometry import geometry_signature
    return (
        round(float(latitude), 6),
        round(float(longitude), 6),
        d,
        round(float(area_m2 or 0.0), 2),
        geometry_signature(field_geometry),
    )


def _sampling_region(ee, latitude, longitude, area_m2=None, radius_m=100, field_geometry=None):
    if field_geometry and field_geometry.get("type") == "Polygon":
        coords = field_geometry.get("coordinates")
        if coords:
            region = ee.Geometry.Polygon(coords, proj=None, geodesic=True)
            return region, None, "Exact irregular field polygon"

    center = ee.Geometry.Point([float(longitude), float(latitude)])
    if area_m2 and float(area_m2) > 0:
        eq_radius = math.sqrt(float(area_m2) / math.pi)
        radius = max(20.0, min(eq_radius, 1500.0))
        method = "Equivalent-area circular fallback"
    else:
        radius = max(20.0, float(radius_m))
        method = "Circular sampling fallback"
    return center.buffer(radius), radius, method

def _clear_mask(image):
    scl = image.select("SCL")
    clear = (
        scl.neq(0)
        .And(scl.neq(1))
        .And(scl.neq(3))
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
        .And(scl.neq(11))
    )
    edge = image.select("B8A").mask().And(image.select("B9").mask())
    return clear.And(edge)


def get_sentinel2_ndvi(
    latitude,
    longitude,
    evaluation_date,
    area_m2=None,
    radius_m=100,
    max_days=60,
    min_clear_fraction=0.20,
    max_candidates=24,
    field_geometry=None,
):
    """
    Faster Sentinel-2 NDVI.

    Why this is faster than the previous build:
      - only one date-window query is made;
      - scenes are ranked by temporal distance on the Earth Engine server;
      - field NDVI and clear-pixel fraction are evaluated server-side;
      - one final getInfo() returns the best acceptable scene;
      - no per-scene Python getInfo() loop and no repeated ±15/±30/±45 scans.

    The closest acceptable clear scene within ±max_days is returned.
    """
    ee = initialize_ee()
    evaluation = _to_date(evaluation_date)
    evaluation_ee = ee.Date(evaluation.isoformat())

    region, used_radius, footprint_method = _sampling_region(
        ee, latitude, longitude, area_m2=area_m2, radius_m=radius_m, field_geometry=field_geometry
    )

    start = evaluation - timedelta(days=int(max_days))
    end_exclusive = evaluation + timedelta(days=int(max_days) + 1)

    collection = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(region)
        .filterDate(start.isoformat(), end_exclusive.isoformat())
    )

    scene_count = int(collection.size().getInfo())
    if scene_count == 0:
        raise RuntimeError(
            f"No Sentinel-2 scenes were found within ±{max_days} days of the evaluation date."
        )

    def add_distance(image):
        days = image.date().difference(evaluation_ee, "day").abs()
        return image.set("days_from_evaluation", days)

    # Keep the nearest scenes before doing field-level reductions.
    nearest = (
        collection
        .map(add_distance)
        .sort("days_from_evaluation")
        .limit(int(max_candidates))
    )

    def scene_to_feature(image):
        clear = _clear_mask(image)

        masked = image.updateMask(clear)
        ndvi = masked.normalizedDifference(["B8", "B4"]).rename("NDVI")
        clear_fraction_img = clear.rename("clear").unmask(0)

        ndvi_value = ndvi.reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=region,
            scale=10,
            bestEffort=True,
            maxPixels=1e7,
        ).get("NDVI")

        clear_fraction = clear_fraction_img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=20,
            bestEffort=True,
            maxPixels=1e7,
        ).get("clear")

        return ee.Feature(
            None,
            {
                "ndvi": ndvi_value,
                "clear_fraction": clear_fraction,
                "days_from_evaluation": image.get("days_from_evaluation"),
                "scene_cloud_pct": image.get("CLOUDY_PIXEL_PERCENTAGE"),
                "system_time_start": image.get("system:time_start"),
                "system_index": image.get("system:index"),
            },
        )

    features = ee.FeatureCollection(nearest.map(scene_to_feature))

    acceptable = (
        features
        .filter(ee.Filter.notNull(["ndvi", "clear_fraction"]))
        .filter(ee.Filter.gte("clear_fraction", float(min_clear_fraction)))
        .sort("days_from_evaluation")
    )

    accepted_count = int(acceptable.size().getInfo())

    if accepted_count == 0:
        # Return a concise diagnostic from the best clear scene if possible.
        best_clear = (
            features
            .filter(ee.Filter.notNull(["ndvi", "clear_fraction"]))
            .sort("clear_fraction", False)
            .first()
        )
        best_info = best_clear.getInfo() if best_clear else None
        if best_info and best_info.get("properties"):
            props = best_info["properties"]
            best_pct = 100.0 * float(props.get("clear_fraction", 0.0) or 0.0)
            raise RuntimeError(
                f"Sentinel-2 scenes were found, but none had at least "
                f"{min_clear_fraction*100:.0f}% clear pixels over the field. "
                f"Best clear-field fraction was about {best_pct:.0f}%."
            )
        raise RuntimeError(
            "Sentinel-2 scenes were found, but none produced a usable field NDVI."
        )

    best = acceptable.first().getInfo()
    props = best["properties"]

    acquired = datetime.utcfromtimestamp(
        float(props["system_time_start"]) / 1000.0
    ).date()

    days_from_eval = int(round(float(props["days_from_evaluation"])))

    return {
        "ndvi": float(props["ndvi"]),
        "acquisition_date": acquired.isoformat(),
        "days_from_evaluation": days_from_eval,
        "scene_cloud_pct": float(props.get("scene_cloud_pct", 100.0) or 100.0),
        "clear_fraction": float(props["clear_fraction"]),
        "search_window_days": int(max_days),
        "sampling_radius_m": None if used_radius is None else float(used_radius),
        "footprint_method": footprint_method,
        "query_signature": make_query_signature(
            latitude, longitude, evaluation, area_m2, field_geometry
        ),
        "status": "clear",
        "scene_count_searched": scene_count,
    }
