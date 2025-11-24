# Data Files for Seeding

This directory contains CSV files with service area and service zone data for seeding the database.

## Files

### service_area.csv

Top-level operating regions.

**Columns:**
- `region_code`: Short code for the region (e.g., "OTT")
- `name`: Full name of the service area (e.g., "Ottawa")
- `description`: Description of the service area
- `boundary`: GeoJSON string containing the polygon geometry (MULTIPOLYGON or POLYGON)
- `center_point`: GeoJSON string with the center point (Point)
- `is_active`: Boolean flag (True/False)
- `id`: UUID identifier
- `created_at`: ISO timestamp
- `updated_at`: ISO timestamp

**Example:**
```csv
region_code,name,description,boundary,center_point,is_active,id,created_at,updated_at
OTT,Ottawa,Ottawa Region,"{""type"":""Polygon"",""coordinates"":[[[...]]]}","{""type"":""Point"",""coordinates"":[-75.77,45.29]}",True,614bee7f-cedd-4bc2-85d8-bdf9d5e96054,2025-11-08T23:04:00.007395Z,2025-11-08T23:04:00.007418Z
```

### service_zones.csv

Sub-areas within service areas (e.g., FSAs, neighborhoods).

**Columns:**
- `name`: Name of the service zone (e.g., "South Leeds & Grenville United Counties (rural)")
- `code`: FSA code or internal code (e.g., "K0E")
- `boundary`: GeoJSON string containing the polygon geometry (MULTIPOLYGON or POLYGON)
- `center_point`: GeoJSON string with the center point (Point)

**Example:**
```csv
name,code,boundary,center_point
South Leeds & Grenville United Counties (rural),K0E,"{""type"":""Polygon"",""coordinates"":[[[...]]]}","{""type"":""Point"",""coordinates"":[-75.51,45.11]}"
```

## Geometry Format

All geometry data is stored as GeoJSON strings with the following structure:

**Polygon:**
```json
{
  "type": "Polygon",
  "coordinates": [[[lng1, lat1], [lng2, lat2], ...]]
}
```

**MultiPolygon:**
```json
{
  "type": "MultiPolygon",
  "coordinates": [[[[lng1, lat1], [lng2, lat2], ...]], [[[...]]]]
}
```

**Point:**
```json
{
  "type": "Point",
  "coordinates": [lng, lat]
}
```

## Notes

- Coordinates are in WGS84 (SRID 4326) format: `[longitude, latitude]`
- The seeding script will automatically:
  - Parse the GeoJSON strings
  - Generate H3 cell coverage at multiple resolutions (7, 8, 9, 10)
  - Create both normalized and compacted H3 representations
  - Calculate H3 label cells from centroids
- All service zones will be associated with the "Ottawa" service area
- If you need to add more service areas, update the seeding script accordingly

