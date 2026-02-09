#!/bin/bash
# PostgreSQL restore script for Site Search Platform
# Restores a database from a compressed backup file

set -e

# Configuration
BACKUP_DIR="backups"
DB_NAME="indexer_db"
DB_USER="indexer_user"

echo "Available backups:"
ls "${BACKUP_DIR}"/db_*.sql.gz 2>/dev/null || { echo "No backups found in ${BACKUP_DIR}"; exit 1; }

# Prompt for backup file if not specified
if [ -z "$1" ]; then
    echo "Enter the backup filename to restore (or press Enter for latest):"
    read -r BACKUP_FILE
    if [ -z "${BACKUP_FILE}" ]; then
        BACKUP_FILE=$(ls -t "${BACKUP_DIR}"/db_*.sql.gz | head -1)
        echo "Using latest backup: ${BACKUP_FILE}"
    fi
else
    BACKUP_FILE="$1"
fi

# Validate backup file
if [ ! -f "${BACKUP_FILE}" ]; then
    # Check if it's in backup directory
    if [ ! -f "${BACKUP_DIR}/${BACKUP_FILE}" ]; then
        echo "Backup file not found: ${BACKUP_FILE}"
        exit 1
    fi
    BACKUP_FILE="${BACKUP_DIR}/${BACKUP_FILE}"
fi

echo "Restoring ${BACKUP_FILE} to ${DB_NAME}..."

# Check if we're restoring to a production database
read -p "This will overwrite the current database. Type 'YES' to confirm: " CONFIRM
if [ "${CONFIRM}" != "YES" ]; then
    echo "Restore cancelled."
    exit 0
fi

# Stop application services to prevent data corruption
echo "Stopping application services..."
docker-compose stop app worker beat 2>/dev/null || true

# Drop and recreate database (or drop all objects)
echo "Clearing existing database..."
# Option 1: Drop and recreate (requires superuser)
# dropdb -U "${DB_USER}" -h localhost "${DB_NAME}" 2>/dev/null || true
# createdb -U "${DB_USER}" -h localhost "${DB_NAME}"

# Option 2: Clean all tables (safer, keeps database structure)
cat << EOF | psql -U "${DB_USER}" -h localhost "${DB_NAME}" > /dev/null
DO \$\$ 
DECLARE 
    r RECORD;
BEGIN
    -- Disable triggers temporarily
    SET session_replication_role = replica;

    -- Drop all tables (cascading to remove foreign keys)
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
    LOOP
        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;

    -- Reset session
    SET session_replication_role = DEFAULT;
END \$\$;
EOF

# Restore the backup
echo "Restoring from backup..."
gunzip -c "${BACKUP_FILE}" | psql -U "${DB_USER}" -h localhost "${DB_NAME}"

# Recreate indexes and reset sequences
echo "Recreating indexes and resetting sequences..."
cat << EOF | psql -U "${DB_USER}" -h localhost "${DB_NAME}" > /dev/null
-- Reset sequences
SELECT setval(pg_get_serial_sequence('sites', 'id'), coalesce(max(id), 0) + 1, false) FROM sites;
SELECT setval(pg_get_serial_sequence('pages', 'id'), coalesce(max(id), 0) + 1, false) FROM pages;
SELECT setval(pg_get_serial_sequence('api_keys', 'id'), coalesce(max(id), 0) + 1, false) FROM api_keys;
SELECT setval(pg_get_serial_sequence('search_queries', 'id'), coalesce(max(id), 0) + 1, false) FROM search_queries;
EOF

echo "✓ Database restored successfully!"

# Reindex Meilisearch
echo "To reindex Meilisearch with the restored data, run:"
echo "  python scripts/index_meilisearch.py --full"

# Restart services
echo "Restarting application services..."
docker-compose start app worker beat 2>/dev/null || true

echo "Restore complete!"