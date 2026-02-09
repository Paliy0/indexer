#!/bin/bash
# PostgreSQL backup script for Site Search Platform
# Backs up the database to a compressed file and removes old backups

set -e

# Configuration
BACKUP_DIR="backups"
DB_NAME="indexer_db"
DB_USER="indexer_user"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"
KEEP_DAYS=30

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

echo "Starting database backup for ${DB_NAME}..."

# Perform the backup
pg_dump -U "${DB_USER}" -h localhost "${DB_NAME}" | gzip > "${BACKUP_FILE}"

# Verify backup was created
if [ -f "${BACKUP_FILE}" ]; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "✓ Backup created: ${BACKUP_FILE} (${FILE_SIZE})"
else
    echo "✗ Backup failed: ${BACKUP_FILE} not created"
    exit 1
fi

# Remove old backups
echo "Cleaning up backups older than ${KEEP_DAYS} days..."
find "${BACKUP_DIR}" -name "db_*.sql.gz" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true

# List remaining backups
echo "Current backups in ${BACKUP_DIR}:"
ls -lh "${BACKUP_DIR}"/db_*.sql.gz 2>/dev/null || echo "No backups found"

echo "Backup completed successfully!"