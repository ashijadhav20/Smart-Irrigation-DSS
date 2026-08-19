import folium
from folium.plugins import Draw, Fullscreen

ESRI_IMAGERY = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"

def satellite_map(lat, lon, zoom=18, boundary=None, editable=False, allow_rectangle=False):
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None, control_scale=True)
    folium.TileLayer(tiles=ESRI_IMAGERY, attr=ESRI_ATTR, name="Satellite imagery", overlay=False, control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map", overlay=False, control=True).add_to(m)
    Fullscreen(position="topright").add_to(m)
    if boundary:
        folium.GeoJson(
            boundary,
            name="Saved field boundary",
            style_function=lambda _: {"color":"#00ff88", "weight":4, "fillColor":"#00ff88", "fillOpacity":0.12},
            tooltip="Actual field boundary used by the DSS",
        ).add_to(m)
    if editable:
        Draw(
            export=False,
            position="topleft",
            draw_options={
                "polyline": False, "marker": False, "circlemarker": False, "circle": False,
                "polygon": {"allowIntersection": False, "showArea": True},
                "rectangle": {"showArea": True} if allow_rectangle else False,
            },
            edit_options={"edit": False, "remove": False},
        ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m



def water_resources_map(lat, lon, radius_km, field_boundary=None, water_bodies=None, zoom=14):
    """Satellite map showing field, search radius and detected water polygons."""
    m = folium.Map(location=[lat, lon], zoom_start=zoom, tiles=None, control_scale=True)
    folium.TileLayer(tiles=ESRI_IMAGERY, attr=ESRI_ATTR, name="Satellite imagery", overlay=False, control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map", overlay=False, control=True).add_to(m)
    Fullscreen(position="topright").add_to(m)
    folium.Circle(
        location=[lat, lon], radius=float(radius_km)*1000.0,
        color="#ffb000", weight=2, fill=False, dash_array="8,6",
        tooltip=f"Water-resource search radius: {float(radius_km):.1f} km",
    ).add_to(m)
    if field_boundary:
        folium.GeoJson(
            field_boundary, name="Field boundary",
            style_function=lambda _: {"color":"#00ff88", "weight":4, "fillColor":"#00ff88", "fillOpacity":0.12},
            tooltip="Saved agricultural field",
        ).add_to(m)
    for body in (water_bodies or []):
        name = body.get("name", "Detected water body")
        area = float(body.get("area_ha", 0.0) or 0.0)
        dist = float(body.get("distance_km", 0.0) or 0.0)
        ndwi = body.get("mean_ndwi"); mndwi = body.get("mean_mndwi"); ndvi = body.get("mean_ndvi")
        tooltip = f"{name} • {area:.3f} ha • {dist:.2f} km from field"
        index_html = ""
        if ndwi is not None: index_html += f"<br>Mean NDWI: {float(ndwi):.3f}"
        if mndwi is not None: index_html += f"<br>Mean MNDWI: {float(mndwi):.3f}"
        if ndvi is not None: index_html += f"<br>Mean NDVI: {float(ndvi):.3f}"
        popup_html = f"<b>{name}</b><br>Surface area: {area:.3f} ha<br>Distance: {dist:.2f} km{index_html}"
        folium.GeoJson(
            body["geometry"], name=name,
            style_function=lambda _, c="#22a7f0": {"color":c, "weight":3, "fillColor":c, "fillOpacity":0.38},
            tooltip=tooltip, popup=folium.Popup(popup_html, max_width=320),
        ).add_to(m)
        folium.Marker(
            [body.get("centroid_lat",lat), body.get("centroid_lon",lon)],
            tooltip=f"{name}: {area:.3f} ha",
            icon=folium.DivIcon(html=f'<div style="font-size:11px;font-weight:700;color:white;background:#146c94;padding:2px 5px;border-radius:5px;white-space:nowrap;">W{body.get("id","")}</div>'),
        ).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m
