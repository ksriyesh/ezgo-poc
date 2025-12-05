#!/bin/bash
set -e

echo "=========================================="
echo "  ezGO Backend Starting..."
echo "=========================================="

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
until python -c "
from sqlalchemy import create_engine, text
from app.core.config import settings
engine = create_engine(settings.DATABASE_URL)
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
" 2>/dev/null; do
    echo "  PostgreSQL not ready, waiting..."
    sleep 2
done
echo "PostgreSQL is ready!"

# Run migrations
echo "Running migrations..."
alembic upgrade head
echo "Migrations complete!"

# Seed if empty
echo "Checking if seeding needed..."
python -c "
from sqlalchemy import create_engine, text
from app.core.config import settings
engine = create_engine(settings.DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(*) FROM service_areas'))
    if result.scalar() == 0:
        print('SEED_NEEDED')
" 2>/dev/null | grep -q "SEED_NEEDED" && {
    echo "Seeding database..."
    python -m app.scripts.seed
    echo "Seeding complete!"
} || echo "Database already has data."

# Start server
echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
