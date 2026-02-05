#!/bin/bash
# Initialize Butler schema in PostgreSQL
# This script is idempotent - safe to run multiple times
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-immich-postgres}"
POSTGRES_DB="${POSTGRES_DB:-immich}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
MAX_RETRIES="${MAX_RETRIES:-30}"
RETRY_INTERVAL="${RETRY_INTERVAL:-2}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION_FILE="${SCRIPT_DIR}/../nanobot/migrations/001_butler_schema.sql"

echo -e "${BLUE}==>${NC} Initializing Butler schema..."

# Check migration file exists
if [[ ! -f "$MIGRATION_FILE" ]]; then
    echo -e "${RED}✗${NC} Migration file not found: $MIGRATION_FILE"
    exit 1
fi

# Wait for PostgreSQL to be ready
echo -e "${BLUE}==>${NC} Waiting for PostgreSQL to be ready..."
retries=0
until docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" &>/dev/null; do
    retries=$((retries + 1))
    if [[ $retries -ge $MAX_RETRIES ]]; then
        echo -e "${RED}✗${NC} PostgreSQL not ready after $MAX_RETRIES attempts"
        exit 1
    fi
    echo -e "  ${YELLOW}⏳${NC} Waiting for PostgreSQL... (attempt $retries/$MAX_RETRIES)"
    sleep "$RETRY_INTERVAL"
done
echo -e "  ${GREEN}✓${NC} PostgreSQL is ready"

# Copy migration file to container and execute
echo -e "${BLUE}==>${NC} Running Butler schema migration..."
docker cp "$MIGRATION_FILE" "$POSTGRES_CONTAINER:/tmp/butler_schema.sql"
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/butler_schema.sql -q

# Verify schema was created
echo -e "${BLUE}==>${NC} Verifying schema..."
SCHEMA_EXISTS=$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'butler');")

if [[ "$SCHEMA_EXISTS" == "t" ]]; then
    echo -e "  ${GREEN}✓${NC} Butler schema created successfully"
else
    echo -e "${RED}✗${NC} Failed to verify Butler schema"
    exit 1
fi

# Count tables for confirmation
TABLE_COUNT=$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'butler';")
echo -e "  ${GREEN}✓${NC} Butler schema contains $TABLE_COUNT tables"

echo -e "${GREEN}✓${NC} Butler schema initialization complete"
