# API Usage Guide

## Service Areas & Zones with H3 Coverage

The API now includes H3 hexagonal coverage at multiple zoom levels for all service areas and zones.

## API Endpoints

### Get All Service Areas with H3 Coverage

```bash
GET /api/v1/service-areas?include_h3=true
```

**Query Parameters:**
- `include_h3` (boolean, default: true): Include H3 coverage in response
- `resolutions` (string, optional): Comma-separated H3 resolutions (e.g., "8,9,10")
- `skip` (int, default: 0): Number of records to skip
- `limit` (int, default: 100): Max records to return
- `active_only` (boolean, default: false): Only return active areas

**Example Response:**
```json
[
  {
    "id": "614bee7f-cedd-4bc2-85d8-bdf9d5e96054",
    "name": "Ottawa",
    "description": "Ottawa Region",
    "label_cell": "891e204d08fffff",
    "default_res": 9,
    "is_active": true,
    "created_at": "2025-11-08T23:04:00.007395Z",
    "updated_at": "2025-11-08T23:04:00.007418Z",
    "h3_coverage": {
      "7": {
        "resolution": 7,
        "cells": ["871e204d0ffffff", "871e204d1ffffff", ...],
        "cell_count": 45,
        "compacted_cells": ["871e204d0ffffff", ...]
      },
      "8": {
        "resolution": 8,
        "cells": ["881e204d08fffff", ...],
        "cell_count": 312,
        "compacted_cells": null
      },
      "9": {
        "resolution": 9,
        "cells": ["891e204d08fffff", ...],
        "cell_count": 2187,
        "compacted_cells": null
      },
      "10": {
        "resolution": 10,
        "cells": ["8a1e204d080ffff", ...],
        "cell_count": 15309,
        "compacted_cells": null
      }
    }
  }
]
```

### Get Service Area by ID

```bash
GET /api/v1/service-areas/{id}?include_h3=true&resolutions=8,9
```

### Get All Service Zones with H3 Coverage

```bash
GET /api/v1/service-zones?include_h3=true&service_area_id={area_id}
```

**Query Parameters:**
- `include_h3` (boolean, default: true): Include H3 coverage
- `resolutions` (string, optional): Filter specific resolutions
- `service_area_id` (UUID, optional): Filter by service area
- `skip` (int, default: 0): Pagination offset
- `limit` (int, default: 100): Page size
- `active_only` (boolean, default: false): Only active zones

### Get Service Zone by ID

```bash
GET /api/v1/service-zones/{id}?include_h3=true
```

## H3 Resolution Levels

The system generates coverage at 4 zoom levels:

| Resolution | Hex Size | Use Case |
|------------|----------|----------|
| 7 | ~5 km | City/Regional view |
| 8 | ~1.2 km | Neighborhood view |
| 9 | ~350 m | Street view (default) |
| 10 | ~90 m | Detailed view |

## Example Usage Scenarios

### Frontend Map Rendering

1. **Initial Load** - Get all service areas with resolution 7:
   ```bash
   GET /api/v1/service-areas?resolutions=7
   ```

2. **Zoom In** - Get higher resolution:
   ```bash
   GET /api/v1/service-areas/{id}?resolutions=8,9
   ```

3. **Detailed View** - Get specific zone with highest resolution:
   ```bash
   GET /api/v1/service-zones/{id}?resolutions=10
   ```

### Point-in-Polygon Checks

Use H3 cells for fast "is this point in this area?" checks:

1. Convert lat/lng to H3 cell at resolution 9
2. Check if that cell exists in the `cells` array
3. Much faster than traditional point-in-polygon!

### Optimization Tips

- **Use compacted cells** for transport/storage (smaller payload)
- **Request only needed resolutions** to reduce response size
- **Cache lower resolutions** (7, 8) as they change rarely
- **Use resolution 9** as default for most operations
- **Use resolution 10** only for detailed/zoomed views

## Data Verification

Run the test script to verify seeded data matches CSV sources:

```bash
uv run python -m app.scripts.test_seeded_data
```

This will:
- ✓ Verify all service areas from CSV exist in DB
- ✓ Check geometry matches
- ✓ Verify H3 coverage at all resolutions
- ✓ Test H3 compaction integrity
- ✓ Validate all service zones
- ✓ Check FSA codes match

## Response Format

### H3 Coverage Structure

```typescript
{
  h3_coverage: {
    [resolution: number]: {
      resolution: number;
      cells: string[];          // Array of H3 cell IDs
      cell_count: number;        // Number of cells
      compacted_cells: string[] | null;  // Compacted version
    }
  }
}
```

### Without H3 Coverage

To get responses without H3 coverage (smaller, faster):

```bash
GET /api/v1/service-areas?include_h3=false
```

## Performance Considerations

- **With H3 (resolution 9)**: ~2-10 KB per area/zone
- **Without H3**: ~500 bytes per area/zone
- **Compacted cells**: 60-80% smaller than full cell list
- **Database queries**: Single JOIN per resolution requested

## Integration Example (Frontend)

```typescript
// Fetch service areas with H3 coverage
const response = await fetch('/api/v1/service-areas?resolutions=8,9');
const areas = await response.json();

// Extract H3 cells for map rendering
areas.forEach(area => {
  const cells = area.h3_coverage[9].cells; // Use resolution 9
  
  // Render hexagons on map
  cells.forEach(cell => {
    const boundary = h3.cellToBoundary(cell);
    renderHexagon(boundary);
  });
});
```

