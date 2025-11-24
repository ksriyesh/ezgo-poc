# ezGO POC Backend

FastAPI backend with PostgreSQL, PostGIS, and H3 geospatial support for service area and zone management.

## 🚀 Quick Start

### 1. Database Setup
```bash
cd ../database
docker-compose up -d
```

### 2. Backend Setup
```bash
# Copy environment template
cp .env.example .env

# Install dependencies
uv sync

# Run migrations
uv run alembic upgrade head

# Seed database with initial data
uv run python -m app.scripts.seed
```

### 3. Run Server

**Simple way:**
```bash
python main.py
```

**Or with uv:**
```bash
uv run python main.py
```

**Or using uvicorn directly:**
```bash
uv run uvicorn app.main:app --reload
```

### 4. Access API
- **API Endpoint**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

## 📁 Project Structure

```
backend/
├── main.py                 # Server entry point (NEW)
├── .env.example           # Environment template
├── pyproject.toml         # Dependencies (uv compatible)
├── alembic.ini           # Alembic configuration
│
├── alembic/              # Database migrations
│   └── versions/
│       └── 001_initial_tables.py
│
├── app/                  # Main application
│   ├── main.py          # FastAPI app
│   ├── api/             # API routes
│   ├── core/            # Configuration
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   ├── crud/            # Database operations
│   └── scripts/         # Utility scripts
│
├── misc/                # Data files (CSV)
└── scripts/             # Setup scripts
```

## 🛠️ Common Commands

### Database Management
```bash
# Run migrations
uv run alembic upgrade head

# Rollback migration (cleans all schema and data)
uv run alembic downgrade -1

# Create new migration
uv run alembic revision --autogenerate -m "Description"

# Seed database
uv run python -m app.scripts.seed

# Test seeded data
uv run python -m app.scripts.test_seeded_data
```

### Development
```bash
# Run server with auto-reload
python main.py

# Install dependencies
uv sync

# Add new dependency
uv add package-name

# Add dev dependency
uv add --dev package-name
```

## 🌍 API Endpoints

### Service Areas
- `GET /api/v1/service-areas` - List all service areas
- `GET /api/v1/service-areas/{id}` - Get specific service area
- `POST /api/v1/service-areas` - Create service area
- `PUT /api/v1/service-areas/{id}` - Update service area
- `DELETE /api/v1/service-areas/{id}` - Delete service area

### Service Zones
- `GET /api/v1/service-zones` - List all service zones
- `GET /api/v1/service-zones/{id}` - Get specific service zone
- `POST /api/v1/service-zones` - Create service zone
- `PUT /api/v1/service-zones/{id}` - Update service zone
- `DELETE /api/v1/service-zones/{id}` - Delete service zone

### Query Parameters
- `include_h3=true` - Include H3 coverage in response
- `resolutions=7,8,9,10` - Specify H3 resolutions
- `skip=0` - Pagination offset
- `limit=100` - Results per page
- `active_only=true` - Filter active items only

## 🗺️ H3 Coverage

The backend automatically generates H3 hexagonal coverage at multiple resolutions:
- **Resolution 7**: ~5km hexagons (city/regional view)
- **Resolution 8**: ~1.2km hexagons (neighborhood view)
- **Resolution 9**: ~350m hexagons (street view / default)
- **Resolution 10**: ~90m hexagons (detailed view)

### Current Coverage Statistics
- **Service Areas**: 1 (Ottawa)
- **Service Zones**: 46 (FSA-based zones)
- **H3 Cells**: 106,572 (across all resolutions)
- **Compacted Sets**: 188
- **Coverage**: 100% (all zones have H3 coverage)

## 🔧 Environment Variables

Create a `.env` file from `.env.example`:

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ezgo-poc

# API
API_V1_STR=/api/v1
PROJECT_NAME=ezGO POC Backend
VERSION=0.1.0

# Security (change in production!)
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# CORS
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001"]
```

## 🧪 Testing

```bash
# Test seeded data integrity
uv run python -m app.scripts.test_seeded_data
```

## 📚 Tech Stack

- **Framework**: FastAPI 0.109.0
- **Database**: PostgreSQL with PostGIS + H3 extension
- **ORM**: SQLAlchemy 2.0.25
- **Migrations**: Alembic 1.13.1
- **Geospatial**: GeoAlchemy2 0.14.3, Shapely 2.0.2
- **H3**: H3 3.7.6 (Uber's hexagonal hierarchical geospatial indexing)
- **Validation**: Pydantic 2.5.3
- **Package Manager**: uv (fast Python package installer)

## 📝 Notes

- All geometries are stored in SRID 4326 (WGS84)
- H3 coverage is pre-computed during seeding for performance
- The seeding script handles complex geometries (MultiPolygons) with multiple fallback strategies
- Database migrations include both upgrade and full cleanup downgrade
- Windows console encoding is handled automatically for UTF-8 output

## 🐛 Troubleshooting

### Database connection issues
```bash
# Check if database is running
docker ps | grep ezgo-poc-db

# Restart database
cd ../database && docker-compose restart
```

### Migration issues
```bash
# Clean slate (WARNING: deletes all data)
uv run alembic downgrade base

# Re-run migrations
uv run alembic upgrade head
```

### Package installation issues
```bash
# Clean reinstall
rm -rf .venv uv.lock
uv sync
```

## 📖 Additional Documentation

- **API Usage Guide**: See `API_USAGE.md` for detailed endpoint documentation
- **Data Files**: See `misc/README.md` for CSV data format
- **Project Structure**: See `STRUCTURE.md` for detailed file organization











