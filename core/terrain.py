from __future__ import annotations
import numpy as np
import pandas as pd
import requests
from core.geometry import boundary_bbox, normalize_polygon_geojson

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"


def fetch_elevation_points(latitudes, longitudes, timeout=20):
    latitudes = [float(v) for v in latitudes]
    longitudes = [float(v) for v in longitudes]
    if len(latitudes) != len(longitudes):
        raise ValueError("Latitude and longitude arrays must have the same length.")
    if len(latitudes) > 100:
        raise ValueError("Open-Meteo elevation requests are limited here to 100 points per batch.")
    params = {
        "latitude": ",".join(f"{v:.7f}" for v in latitudes),
        "longitude": ",".join(f"{v:.7f}" for v in longitudes),
    }
    r = requests.get(ELEVATION_URL, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    elev = data.get("elevation")
    if elev is None:
        raise RuntimeError("Open-Meteo elevation response did not contain elevation values.")
    if not isinstance(elev, list):
        elev = [elev]
    if len(elev) != len(latitudes):
        raise RuntimeError("Unexpected elevation response length.")
    return [float(v) for v in elev]


def terrain_grid_for_boundary(boundary, n=9, padding_fraction=0.35):
    bbox = boundary_bbox(boundary)
    if not bbox:
        raise ValueError("A saved field boundary is required.")
    min_lat, min_lon, max_lat, max_lon = bbox
    dlat = max(max_lat-min_lat, 0.0005)
    dlon = max(max_lon-min_lon, 0.0005)
    min_lat -= dlat*padding_fraction; max_lat += dlat*padding_fraction
    min_lon -= dlon*padding_fraction; max_lon += dlon*padding_fraction
    n = max(5, min(10, int(n)))
    lat_axis = np.linspace(min_lat, max_lat, n)
    lon_axis = np.linspace(min_lon, max_lon, n)
    pairs = [(lat,lon) for lat in lat_axis for lon in lon_axis]
    zs = fetch_elevation_points([p[0] for p in pairs], [p[1] for p in pairs])
    z = np.array(zs, dtype=float).reshape((n,n))
    return lat_axis, lon_axis, z


def boundary_elevations(boundary):
    geom = normalize_polygon_geojson(boundary)
    if not geom:
        return pd.DataFrame(columns=["lon","lat","elevation"])
    ring = geom["coordinates"][0]
    # Keep requests under 100 points while preserving the complete ring visually.
    if len(ring) > 90:
        step = max(1, len(ring)//89)
        ring = ring[::step]
        if ring[-1] != ring[0]: ring.append(ring[0])
    lons = [float(p[0]) for p in ring]; lats = [float(p[1]) for p in ring]
    elev = fetch_elevation_points(lats,lons)
    return pd.DataFrame({"lon":lons,"lat":lats,"elevation":elev})


def terrain_grid_for_radius(latitude, longitude, radius_km=5.0, n=9):
    """Sample an elevation grid around a field centre for vicinity-scale 3D context."""
    lat=float(latitude); lon=float(longitude); r_km=max(0.25,min(20.0,float(radius_km)))
    # Approximate geographic span; adequate for locating API sample points.
    dlat=r_km/111.32
    coslat=max(0.2, abs(np.cos(np.deg2rad(lat))))
    dlon=r_km/(111.32*coslat)
    n=max(5,min(10,int(n)))
    lat_axis=np.linspace(lat-dlat,lat+dlat,n)
    lon_axis=np.linspace(lon-dlon,lon+dlon,n)
    pairs=[(la,lo) for la in lat_axis for lo in lon_axis]
    zs=fetch_elevation_points([p[0] for p in pairs],[p[1] for p in pairs])
    return lat_axis,lon_axis,np.array(zs,dtype=float).reshape((n,n))


def water_centroid_elevations(water_bodies):
    if not water_bodies:
        return []
    lats=[float(w["centroid_lat"]) for w in water_bodies]
    lons=[float(w["centroid_lon"]) for w in water_bodies]
    elev=fetch_elevation_points(lats,lons)
    return elev
