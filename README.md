# Smart Irrigation Decision Support System

A new multipage Streamlit dashboard for coordinate-based irrigation scheduling.

## Main functions

- Latitude/longitude field input.
- 20 selectable crops.
- 12 soil texture classes with two modes: automatic coordinate-based detection or manual selection.
- Automatic soil detection uses ISRIC SoilGrids sand/silt/clay predictions and classifies them into a USDA-style texture class.
- Rectangle, square, circle, triangle and trapezoid field-area calculation.
- OpenWeather One Call weather forecast.
- Open-Meteo used only for model-estimated soil moisture.
- Daily FAO-56 Penman-Monteith ET0 calculated in the app; solar radiation is estimated using the Hargreaves radiation approach when measured Rs is unavailable.
- Crop stage and Kc from sowing/evaluation dates.
- Optional Sentinel-2 NDVI through Google Earth Engine.
- Manual NDVI fallback.
- Model-estimated root-zone soil moisture.
- TAW, RAW, depletion, Ks and soil-water status.
- Multi-day soil-moisture decay/recovery forecast.
- Irrigation depth and field water requirement in litres.
- Interactive map.
- Mobile-friendly Streamlit layout.


## OpenWeather API key

Create `.streamlit/secrets.toml` and add:

```toml
OPENWEATHER_API_KEY = "YOUR_ACTUAL_OPENWEATHER_API_KEY"
```

Do not put the API key directly in Python files and do not upload `secrets.toml` to a public GitHub repository.

This version uses OpenWeather One Call 3.0 for weather. Make sure your OpenWeather account/API key has access to that endpoint.


## 1. Install on Windows

Open Command Prompt inside this folder and run:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Or, after installation, double-click `run_dashboard.bat`.

## 2. Recommended page sequence

1. Field Input
2. Weather
3. Crop & ETc
4. Soil Moisture
5. Irrigation
6. Field Map
7. Summary

The pages use Streamlit session state, so follow this order during the first test.

## 3. Google Earth Engine

The dashboard works without Earth Engine by using Manual NDVI.

For unattended/public deployment, configure an Earth Engine-enabled Google Cloud project and a service account. Put credentials in Streamlit secrets, not in GitHub.

Copy:

`.streamlit/secrets.toml.example`

to:

`.streamlit/secrets.toml`

and fill the required values.

Never upload the real `secrets.toml` or private key to a public repository.

## 4. Free web/mobile deployment

1. Create a GitHub repository.
2. Upload this project.
3. Create a Streamlit Community Cloud app from the repository.
4. Set `app.py` as the entry point.
5. Add Earth Engine credentials under Community Cloud app secrets if NDVI is required.
6. Share the generated `*.streamlit.app` address.
7. Android/iPhone users can open the URL in a browser and add it to their home screen.

## Scientific notes

- Open-Meteo soil moisture is model-estimated and must not be presented as a direct field sensor measurement.
- Crop Kc, root depth, depletion fraction and soil FC/PWP values in `core/data.py` are editable starting values. Validate locally.
- The NDVI correction in `core/crop.py` is deliberately labelled an empirical research calibration, not a universal FAO equation.
- The forecast is a simplified root-zone bucket model. Add runoff, irrigation events, deep percolation and calibrated effective rainfall if required for the final research model.
- Exact field polygons can later replace the equivalent-area circle on the map.


## Automatic soil-type selection

On the Field Input page choose either:

- **Automatic from coordinates** — enter latitude/longitude, press **Detect soil type from coordinates**, and the app retrieves predicted sand, silt and clay fractions from ISRIC SoilGrids before assigning a soil-texture class.
- **Choose manually** — directly select one of the 12 soil classes.

The automatically detected class is a 250 m model prediction, so the dashboard labels it as an estimate. For research validation, compare it with field/laboratory soil texture data where available.

The SoilGrids public REST API is currently a beta service and may occasionally be unavailable. The manual soil-selection option therefore remains available as a reliable fallback.


## SoilGrids parser correction

This build corrects the automatic soil-texture lookup in three ways:

1. The app now requests the complete SoilGrids point response using only latitude and longitude, then extracts sand, silt and clay from the returned layer structure.
2. SoilGrids mapped texture values are correctly converted from integer g/kg values to conventional percent by multiplying by 0.1 (equivalent to dividing by 10).
3. If the exact point is a SoilGrids no-data cell, the app tries one nearby point (~250 m) once and clearly warns the user if that fallback was used.

The public SoilGrids REST API is beta and has a fair-use limit, so do not repeatedly press the detection button in rapid succession.


## Weather API correction — standard OpenWeather endpoints

This build no longer uses One Call 3.0.

Weather is now obtained from:

- OpenWeather Current Weather Data: `/data/2.5/weather`
- OpenWeather 5 Day / 3 Hour Forecast: `/data/2.5/forecast`

The 3-hour forecast is aggregated into daily Tmin, Tmax, mean temperature, mean RH,
wind, pressure and rainfall. Daily FAO-56 Penman-Monteith ET0 is then calculated.

The first/last forecast date may be partial because the API is delivered every 3 hours.
The dashboard marks a daily row as complete only when it contains at least eight 3-hour records.

Open-Meteo remains used only for soil moisture.

The corrected SoilGrids automatic/manual soil-selection code remains included.


## Final GEE integration

This build removes interactive `ee.Authenticate()` from the dashboard workflow.

Local authentication uses the already-tested service account through:
- project: `ashijadhav20`
- service account: `irrigation-dss@ashijadhav20.iam.gserviceaccount.com`
- a protected local JSON key path supplied in `.streamlit/secrets.toml`

Automatic NDVI:
- Sentinel-2 SR Harmonized
- adaptive ±15 / ±30 / ±45 day search around evaluation date
- broad scene-cloud prefilter
- pixel-level cloud, cloud-shadow, cirrus and snow masking using SCL
- minimum clear-pixel requirement over the field footprint
- acquisition-date and cloud diagnostics displayed to the user
- manual NDVI and unadjusted Kc fallbacks

The dashboard currently uses an equivalent-area circular footprint because field
orientation/corner coordinates are not yet collected.


## Faster automatic soil lookup

This build reduces waiting time for coordinate-based SoilGrids detection:

- SoilGrids network timeout reduced to about 12 seconds.
- Coordinates are rounded to 4 decimal places before caching.
- Results are cached in memory for up to 256 coordinate cells.
- Repeated lookups for the same/nearby coordinate return immediately during the running app session.
- Only one nearby fallback lookup is attempted.
- If automatic lookup fails or times out, manual soil selection remains available so the DSS is not blocked.

The cache is in-memory and resets when the Streamlit/Python process is restarted.


## Corrected NDVI and persistent fast-soil build

### NDVI
This build removes all Earth Engine map-tile creation from the NDVI workflow.
Numerical Sentinel-2 NDVI therefore does not call `getMapId()` and does not need
`earthengine.maps.create`.

The Crop ET page now:
- searches ±15 / ±30 / ±45 days,
- uses a broad scene-cloud prefilter,
- applies pixel-level SCL cloud/shadow masking,
- shows acquisition date and clear-field fraction,
- rejects stale NDVI when field/date/area changes,
- automatically falls back to base Kc if automatic GEE NDVI fails.

### Soil type
Automatic SoilGrids lookup now uses two cache layers:
- in-process LRU cache,
- persistent SQLite cache valid for 30 days.

The persistent cache survives Streamlit restart. New network requests use a short
timeout and do not repeatedly retry after a network timeout. Manual soil selection
always remains available.


## Refined Sentinel-2 and soil-moisture scheduling

### Sentinel-2
The scene-level cloud percentage is no longer a hard rejection criterion.
The app searches ±15 / ±30 / ±45 / ±60 days and evaluates actual clear field
pixels using Sentinel-2 SCL masking. This avoids rejecting useful scenes merely
because the overall Sentinel-2 tile is cloudy.

### Irrigation
Current root-zone soil moisture is explicitly used to calculate root-zone
depletion (Dr). Irrigation is triggered when Dr reaches RAW. ETc and effective
rainfall then drive the forecast depletion and projected irrigation date.

## 19 Aug 2026 V2 refinement
The field-definition page now supports both regular dimension-based shapes and irregular drawn/uploaded boundaries. Soil can be selected by USDA class, obtained as a SoilGrids screening estimate, or derived from user-entered sand/silt/clay percentages. Open-Meteo depth-wise soil moisture is retained. A final 3D Terrain page uses Open-Meteo elevation samples and shows the same saved field boundary alongside the satellite boundary map.

## Nearby Water Resources (2026-08-19 refinement)
A new final page, `8_Nearby_Water_Resources.py`, searches a user-selected vicinity around the saved field for open surface water using Sentinel-2 SR in Google Earth Engine. The default conservative mask combines NDWI + MNDWI and uses NDVI as a vegetation screen. Results include detected water-body polygons, surface area, distance from the field, index summaries, satellite mapping, and a descriptive 3D terrain/water-resource view.

Water-surface area is satellite-derived. Water storage is **not** inferred directly from spectral indices; the user supplies a measured/assumed mean depth for each detected water body and the dashboard calculates indicative storage as `surface area × mean depth`.
