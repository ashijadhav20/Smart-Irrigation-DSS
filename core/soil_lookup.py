from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sqlite3
from functools import lru_cache

import requests

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

TEXTURE_PROPERTIES = ("sand", "silt", "clay")
TEXTURE_SCALE = 0.1

STANDARD_DEPTHS = {
    "0-5cm": (0, 5),
    "5-15cm": (5, 15),
    "15-30cm": (15, 30),
    "30-60cm": (30, 60),
    "60-100cm": (60, 100),
    "100-200cm": (100, 200),
}

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"
CACHE_DB = CACHE_DIR / "soil_lookup.sqlite3"
CACHE_MAX_AGE_DAYS = 30


def _ensure_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(CACHE_DB) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS soil_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_utc TEXT NOT NULL
            )
            """
        )
        con.commit()


def _cache_get(cache_key: str):
    try:
        _ensure_cache()

        with sqlite3.connect(CACHE_DB) as con:
            row = con.execute(
                """
                SELECT payload, created_utc
                FROM soil_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()

        if not row:
            return None

        payload, created_utc = row
        created = datetime.fromisoformat(created_utc)

        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) - created > timedelta(
            days=CACHE_MAX_AGE_DAYS
        ):
            return None

        return json.loads(payload)

    except Exception:
        # Cache failure must never block the dashboard.
        return None


def _cache_put(cache_key: str, payload: dict):
    try:
        _ensure_cache()

        with sqlite3.connect(CACHE_DB) as con:
            con.execute(
                """
                INSERT INTO soil_cache(cache_key, payload, created_utc)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key)
                DO UPDATE SET
                    payload = excluded.payload,
                    created_utc = excluded.created_utc
                """,
                (
                    cache_key,
                    json.dumps(payload),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            con.commit()

    except Exception:
        pass


def classify_usda_texture(sand: float, silt: float, clay: float) -> str:
    sand = float(sand)
    silt = float(silt)
    clay = float(clay)

    total = sand + silt + clay

    if not math.isfinite(total) or total <= 0:
        raise ValueError("Invalid soil texture fractions.")

    sand = sand * 100.0 / total
    silt = silt * 100.0 / total
    clay = clay * 100.0 / total

    if (silt + 1.5 * clay) < 15:
        return "Sand"

    if (
        (silt + 1.5 * clay) >= 15
        and (silt + 2 * clay) < 30
    ):
        return "Loamy sand"

    if (
        (
            clay >= 7
            and clay < 20
            and sand > 52
            and (silt + 2 * clay) >= 30
        )
        or (
            clay < 7
            and silt < 50
            and (silt + 2 * clay) >= 30
        )
    ):
        return "Sandy loam"

    if (
        clay >= 7
        and clay < 27
        and silt >= 28
        and silt < 50
        and sand <= 52
    ):
        return "Loam"

    if (
        (silt >= 50 and clay >= 12 and clay < 27)
        or (silt >= 50 and silt < 80 and clay < 12)
    ):
        return "Silt loam"

    if silt >= 80 and clay < 12:
        return "Silt"

    if clay >= 20 and clay < 35 and silt < 28 and sand > 45:
        return "Sandy clay loam"

    if clay >= 27 and clay < 40 and sand > 20 and sand <= 45:
        return "Clay loam"

    if clay >= 27 and clay < 40 and sand <= 20:
        return "Silty clay loam"

    if clay >= 35 and sand > 45:
        return "Sandy clay"

    if clay >= 40 and silt >= 40:
        return "Silty clay"

    if clay >= 40 and sand <= 45 and silt < 40:
        return "Clay"

    if clay >= 40:
        return "Clay"
    if clay >= 27:
        return "Clay loam"
    if silt >= 80:
        return "Silt"
    if silt >= 50:
        return "Silt loam"
    if sand >= 85:
        return "Sand"
    if sand >= 70:
        return "Loamy sand"
    if sand >= 52:
        return "Sandy loam"

    return "Loam"


def _clean_depth_label(label: str) -> str:
    return str(label or "").replace(" ", "").lower()


def _extract_layer_value(layer: dict, depth_label: str):
    wanted = _clean_depth_label(depth_label)

    for depth in layer.get("depths", []) or []:
        label = _clean_depth_label(
            depth.get("label", "")
        )

        if label == wanted:
            mean = (depth.get("values") or {}).get("mean")
            if mean is not None:
                return float(mean)

        rng = depth.get("range") or {}
        target = STANDARD_DEPTHS.get(wanted)

        if target:
            top, bottom = target
            rtop = rng.get(
                "top_depth",
                rng.get("top"),
            )
            rbottom = rng.get(
                "bottom_depth",
                rng.get("bottom"),
            )

            if rtop is not None and rbottom is not None:
                try:
                    if (
                        float(rtop) == float(top)
                        and float(rbottom) == float(bottom)
                    ):
                        mean = (
                            depth.get("values") or {}
                        ).get("mean")

                        if mean is not None:
                            return float(mean)
                except Exception:
                    pass

    return None


def _parse_texture_response(data: dict, depth: str):
    props = data.get("properties") or {}
    layers = props.get("layers") or []

    if not isinstance(layers, list):
        raise RuntimeError(
            "Unexpected SoilGrids response format."
        )

    mapped = {}

    for layer in layers:
        if not isinstance(layer, dict):
            continue

        name = str(
            layer.get("name", "")
        ).strip().lower()

        if name in TEXTURE_PROPERTIES:
            value = _extract_layer_value(
                layer,
                depth,
            )

            if value is not None:
                mapped[name] = value

    missing = [
        p
        for p in TEXTURE_PROPERTIES
        if p not in mapped
    ]

    if missing:
        raise RuntimeError(
            "SoilGrids did not return usable "
            + ", ".join(missing)
            + f" values at {depth}."
        )

    sand = mapped["sand"] * TEXTURE_SCALE
    silt = mapped["silt"] * TEXTURE_SCALE
    clay = mapped["clay"] * TEXTURE_SCALE

    total = sand + silt + clay

    if total <= 0:
        raise RuntimeError(
            "SoilGrids returned invalid texture fractions."
        )

    sand = sand * 100.0 / total
    silt = silt * 100.0 / total
    clay = clay * 100.0 / total

    return {
        "sand_pct": float(sand),
        "silt_pct": float(silt),
        "clay_pct": float(clay),
    }


@lru_cache(maxsize=256)
def _network_query_cached(
    lat_rounded: float,
    lon_rounded: float,
    timeout: int,
):
    """
    In-process cache around the actual SoilGrids network request.
    """
    params = {
        "lat": float(lat_rounded),
        "lon": float(lon_rounded),
    }

    headers = {
        "User-Agent": "Smart-Irrigation-DSS/1.2",
        "Accept": "application/json",
    }

    response = requests.get(
        SOILGRIDS_URL,
        params=params,
        headers=headers,
        timeout=int(timeout),
    )

    if response.status_code == 429:
        raise RuntimeError(
            "SoilGrids rate limit reached."
        )

    if response.status_code >= 500:
        raise RuntimeError(
            f"SoilGrids server error "
            f"(HTTP {response.status_code})."
        )

    response.raise_for_status()

    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(
            "SoilGrids returned a non-JSON response."
        ) from exc


def _make_cache_key(lat, lon, depth):
    # ~0.001 degree ≈ 111 m latitude.
    # SoilGrids itself is much coarser than this.
    return f"{round(lat, 3):.3f}|{round(lon, 3):.3f}|{depth}"


def _build_result(
    texture,
    requested_lat,
    requested_lon,
    used_lat,
    used_lon,
    depth,
    nearby_fallback_used,
    source_mode,
):
    soil_type = classify_usda_texture(
        texture["sand_pct"],
        texture["silt_pct"],
        texture["clay_pct"],
    )

    return {
        "soil_type": soil_type,
        "sand_pct": texture["sand_pct"],
        "silt_pct": texture["silt_pct"],
        "clay_pct": texture["clay_pct"],
        "depth": depth,
        "source": "ISRIC SoilGrids model prediction",
        "requested_latitude": requested_lat,
        "requested_longitude": requested_lon,
        "used_latitude": used_lat,
        "used_longitude": used_lon,
        "nearby_fallback_used": nearby_fallback_used,
        "source_mode": source_mode,
    }


def fetch_soil_texture(
    latitude: float,
    longitude: float,
    depth: str = "0-5cm",
    allow_nearby_fallback: bool = True,
    timeout: int = 8,
):
    """
    Fast automatic SoilGrids lookup.

    Speed strategy:
      1. Persistent SQLite cache (survives app restart)
      2. In-process LRU cache
      3. Only then contact SoilGrids
      4. 8-second network timeout
      5. Nearby fallback only for no-data/parse failures
         — not after a network timeout
    """
    lat = float(latitude)
    lon = float(longitude)

    if not (
        -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        raise ValueError(
            "Latitude/longitude are outside valid ranges."
        )

    cache_key = _make_cache_key(
        lat,
        lon,
        depth,
    )

    saved = _cache_get(cache_key)

    if saved:
        saved["source_mode"] = "persistent_cache"
        return saved

    lat_key = round(lat, 3)
    lon_key = round(lon, 3)

    try:
        data = _network_query_cached(
            lat_key,
            lon_key,
            int(timeout),
        )

        texture = _parse_texture_response(
            data,
            depth,
        )

        result = _build_result(
            texture,
            requested_lat=lat,
            requested_lon=lon,
            used_lat=lat_key,
            used_lon=lon_key,
            depth=depth,
            nearby_fallback_used=False,
            source_mode="live_soilgrids",
        )

        _cache_put(
            cache_key,
            result,
        )

        return result

    except requests.Timeout as exc:
        # Do not double the waiting time with a second network request.
        raise RuntimeError(
            "SoilGrids did not respond within about 8 seconds. "
            "Choose the soil type manually and continue."
        ) from exc

    except requests.RequestException as exc:
        raise RuntimeError(
            "SoilGrids network request failed. "
            "Choose the soil type manually and continue."
        ) from exc

    except Exception as first_error:
        if not allow_nearby_fallback:
            raise

        # Nearby fallback only for no-data/response-content problems.
        nearby_lat = round(
            max(
                -89.999,
                min(
                    89.999,
                    lat_key + 0.002,
                ),
            ),
            3,
        )

        nearby_lon = lon_key

        try:
            nearby_data = _network_query_cached(
                nearby_lat,
                nearby_lon,
                int(timeout),
            )

            texture = _parse_texture_response(
                nearby_data,
                depth,
            )

            result = _build_result(
                texture,
                requested_lat=lat,
                requested_lon=lon,
                used_lat=nearby_lat,
                used_lon=nearby_lon,
                depth=depth,
                nearby_fallback_used=True,
                source_mode="nearby_soilgrids",
            )

            _cache_put(
                cache_key,
                result,
            )

            return result

        except requests.Timeout as exc:
            raise RuntimeError(
                "The selected SoilGrids point had no usable texture and "
                "the one nearby fallback timed out. "
                "Choose the soil type manually."
            ) from exc

        except Exception as second_error:
            raise RuntimeError(
                "Automatic SoilGrids lookup could not return a usable "
                "soil texture quickly. "
                f"Selected point: {first_error}. "
                f"Nearby point: {second_error}. "
                "Choose the soil type manually."
            ) from second_error
