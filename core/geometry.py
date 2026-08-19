import math
from copy import deepcopy
from pyproj import Geod

_GEOD = Geod(ellps="WGS84")


def area_from_shape(shape, **kwargs):
    if shape == "Rectangle": return float(kwargs["length"]) * float(kwargs["width"])
    if shape == "Square": return float(kwargs["side"]) ** 2
    if shape == "Circle": return math.pi * float(kwargs["radius"]) ** 2
    if shape == "Triangle": return 0.5 * float(kwargs["base"]) * float(kwargs["height"])
    if shape == "Trapezoid": return 0.5 * (float(kwargs["a"]) + float(kwargs["b"])) * float(kwargs["height"])
    return 0.0


def _offset_point(lon, lat, x_east_m, y_north_m, bearing_deg=0.0):
    """Convert a local x/y offset to lon/lat, optionally rotating clockwise from north."""
    # Rotate local coordinates around the centre. bearing=0 means shape's y-axis is north.
    th = math.radians(float(bearing_deg))
    xr = x_east_m * math.cos(th) + y_north_m * math.sin(th)
    yr = -x_east_m * math.sin(th) + y_north_m * math.cos(th)
    distance = math.hypot(xr, yr)
    if distance == 0:
        return [float(lon), float(lat)]
    azimuth = math.degrees(math.atan2(xr, yr))
    out_lon, out_lat, _ = _GEOD.fwd(float(lon), float(lat), azimuth, distance)
    return [out_lon, out_lat]


def regular_shape_geometry(shape, lat, lon, bearing_deg=0.0, **kwargs):
    """Build a WGS-84 GeoJSON polygon centred at lat/lon from entered metric dimensions."""
    shape = str(shape)
    lat = float(lat); lon = float(lon)
    pts = []
    if shape == "Rectangle":
        L = float(kwargs["length"]); W = float(kwargs["width"])
        pts = [(-W/2,-L/2),(W/2,-L/2),(W/2,L/2),(-W/2,L/2)]
    elif shape == "Square":
        s = float(kwargs["side"])
        pts = [(-s/2,-s/2),(s/2,-s/2),(s/2,s/2),(-s/2,s/2)]
    elif shape == "Circle":
        r = float(kwargs["radius"])
        ring = []
        for az in range(0, 360, 5):
            out_lon, out_lat, _ = _GEOD.fwd(lon, lat, az + float(bearing_deg), r)
            ring.append([out_lon, out_lat])
        ring.append(ring[0])
        return {"type":"Polygon", "coordinates":[ring]}
    elif shape == "Triangle":
        b = float(kwargs["base"]); h = float(kwargs["height"])
        # Centroid at local origin.
        pts = [(-b/2,-h/3),(b/2,-h/3),(0,2*h/3)]
    elif shape == "Trapezoid":
        a = float(kwargs["a"]); b = float(kwargs["b"]); h = float(kwargs["height"])
        pts = [(-a/2,-h/2),(a/2,-h/2),(b/2,h/2),(-b/2,h/2)]
    else:
        return None
    ring = [_offset_point(lon, lat, x, y, bearing_deg) for x,y in pts]
    ring.append(ring[0])
    return {"type":"Polygon", "coordinates":[ring]}


def normalize_polygon_geojson(obj):
    """Return a GeoJSON Polygon geometry from Feature/geometry/drawing output."""
    if not obj: return None
    if obj.get("type") == "Feature": obj = obj.get("geometry") or {}
    if obj.get("type") == "FeatureCollection":
        feats = obj.get("features") or []
        if not feats: return None
        obj = feats[0].get("geometry") or {}
    if obj.get("type") == "Polygon" and obj.get("coordinates"):
        return {"type":"Polygon", "coordinates": deepcopy(obj["coordinates"])}
    if obj.get("type") == "MultiPolygon" and obj.get("coordinates"):
        return {"type":"Polygon", "coordinates": deepcopy(obj["coordinates"][0])}
    return None


def polygon_geodesic_area_m2(geometry):
    geom = normalize_polygon_geojson(geometry)
    if not geom: return 0.0
    rings = geom["coordinates"]
    if not rings or len(rings[0]) < 4: return 0.0
    outer = rings[0]
    lons = [p[0] for p in outer]
    lats = [p[1] for p in outer]
    area, _ = _GEOD.polygon_area_perimeter(lons, lats)
    area = abs(area)
    for ring in rings[1:]:
        if len(ring) >= 4:
            a, _ = _GEOD.polygon_area_perimeter([p[0] for p in ring], [p[1] for p in ring])
            area -= abs(a)
    return max(0.0, float(area))


def polygon_centroid_latlon(geometry):
    geom = normalize_polygon_geojson(geometry)
    if not geom: return None
    pts = geom["coordinates"][0]
    if len(pts) > 1 and pts[0] == pts[-1]: pts = pts[:-1]
    if not pts: return None
    return (sum(p[1] for p in pts)/len(pts), sum(p[0] for p in pts)/len(pts))


def geometry_signature(geometry):
    geom = normalize_polygon_geojson(geometry)
    if not geom: return None
    return tuple((round(float(x),6), round(float(y),6)) for x,y,*_ in geom["coordinates"][0])


def boundary_bbox(geometry):
    geom = normalize_polygon_geojson(geometry)
    if not geom: return None
    ring = geom["coordinates"][0]
    lons = [float(p[0]) for p in ring]; lats = [float(p[1]) for p in ring]
    return min(lats), min(lons), max(lats), max(lons)


def water_litres(depth_mm, area_m2, application_efficiency_pct=100.0):
    eff = max(application_efficiency_pct / 100.0, 0.01)
    return float(depth_mm * area_m2 / eff)


def local_offsets_geometry(lat, lon, vertices_xy_m, bearing_deg=0.0):
    """Build a WGS-84 Polygon from ordered local (east, north) offsets in metres."""
    if not vertices_xy_m or len(vertices_xy_m) < 3:
        return None
    ring = [_offset_point(float(lon), float(lat), float(x), float(y), float(bearing_deg)) for x, y in vertices_xy_m]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def irregular_template_geometry(shape, lat, lon, bearing_deg=0.0, **kwargs):
    """Dimension-based non-rectangular field templates centred approximately at lat/lon."""
    shape = str(shape)
    if shape == "L-shape":
        L = float(kwargs["outer_length"])
        W = float(kwargs["outer_width"])
        cut_L = min(float(kwargs["cutout_length"]), L * 0.95)
        cut_W = min(float(kwargs["cutout_width"]), W * 0.95)
        # Start SW and proceed clockwise. Cut-out is from the NE corner.
        pts = [
            (-W/2, -L/2),
            ( W/2, -L/2),
            ( W/2,  L/2-cut_L),
            ( W/2-cut_W, L/2-cut_L),
            ( W/2-cut_W, L/2),
            (-W/2,  L/2),
        ]
        area = L * W - cut_L * cut_W
        return local_offsets_geometry(lat, lon, pts, bearing_deg), area

    if shape == "T-shape":
        top_L = float(kwargs["top_length"])
        top_W = float(kwargs["top_width"])
        stem_W = min(float(kwargs["stem_width"]), top_W)
        stem_L = float(kwargs["stem_length"])
        # T with top bar across east-west and stem extending south.
        y_top = stem_L / 2 + top_L
        y_join = stem_L / 2
        y_bottom = -stem_L / 2
        pts = [
            (-stem_W/2, y_bottom),
            ( stem_W/2, y_bottom),
            ( stem_W/2, y_join),
            ( top_W/2, y_join),
            ( top_W/2, y_top),
            (-top_W/2, y_top),
            (-top_W/2, y_join),
            (-stem_W/2, y_join),
        ]
        area = top_L * top_W + stem_L * stem_W
        return local_offsets_geometry(lat, lon, pts, bearing_deg), area

    return None, 0.0


def polygon_side_lengths_m(geometry):
    """Return geodesic side lengths for the exterior ring, excluding closing duplicate."""
    geom = normalize_polygon_geojson(geometry)
    if not geom:
        return []
    pts = geom["coordinates"][0]
    if len(pts) < 4:
        return []
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    out = []
    for p1, p2 in zip(pts[:-1], pts[1:]):
        _, _, dist = _GEOD.inv(float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1]))
        out.append(float(dist))
    return out
