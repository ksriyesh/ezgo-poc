# PostgreSQL + PostGIS + H3 Database Container

This directory contains the Docker setup for a PostgreSQL database with PostGIS and H3 extensions.

## Database Information

- **Database Name**: `ezgo-poc`
- **Username**: `postgres`
- **Password**: `postgres`
- **Port**: `5432`

## Setup

1. Build the Docker image:
   ```bash
   docker-compose build
   ```

2. Start the container:
   ```bash
   docker-compose up -d
   ```

3. Stop the container:
   ```bash
   docker-compose down
   ```

4. View logs:
   ```bash
   docker-compose logs -f
   ```

## Connect to the Database

### Using psql (from host):
```bash
psql -h localhost -p 5432 -U postgres -d ezgo-poc
```

### Using Docker exec:
```bash
docker exec -it ezgo-poc-db psql -U postgres -d ezgo-poc
```

## Verify Extensions

Once connected, verify that the extensions are installed:
```sql
\dx
```

You should see both `postgis` and `h3` listed.

## Data Persistence

The database data is stored in a Docker named volume `postgres_data`, which persists even if the container is stopped or removed.

## Security Note

⚠️ **Important**: The default password is `postgres`. Change it in production by updating the `POSTGRES_PASSWORD` environment variable in `docker-compose.yml`.

