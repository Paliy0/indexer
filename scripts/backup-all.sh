#!/bin/bash
# Complete backup script for Site Search Platform
# Backs up both PostgreSQL and Meilisearch

set -e

echo "=== Site Search Platform Backup ==="
echo "Starting full backup at $(date)"

# Run PostgreSQL backup
echo ""
echo "1. Backing up PostgreSQL database..."
./scripts/backup.sh

# Run Meilisearch backup  
echo ""
echo "2. Backing up Meilisearch indexes..."
./scripts/backup-meilisearch.sh

echo ""
echo "=== Backup Summary ==="
echo "Backup completed at $(date)"
echo ""
echo "Backup files created in 'backups/' directory:"
ls -lh backups/ 2>/dev/null || echo "No backups directory found"

echo ""
echo "To restore:"
echo "  PostgreSQL: ./scripts/restore.sh [backup_file.sql.gz]"
echo "  Meilisearch: ./scripts/restore-meilisearch.sh [dump_file.dump.gz]"
echo "  Full restore: Run both commands in order (PostgreSQL first)"