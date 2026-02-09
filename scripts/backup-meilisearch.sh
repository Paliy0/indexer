#!/bin/bash
# Meilisearch backup script for Site Search Platform
# Creates a dump of the Meilisearch index and saves it to the backups directory

set -e

# Configuration
BACKUP_DIR="backups"
MEILI_HOST="http://localhost:7700"
MEILI_MASTER_KEY="${MEILI_MASTER_KEY:-masterKey}"  # Default from docker-compose
KEEP_DAYS=30

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

echo "Starting Meilisearch backup..."

# Check if Meilisearch is running
if ! curl -s "${MEILI_HOST}/health" > /dev/null 2>&1; then
    echo "✗ Meilisearch is not running at ${MEILI_HOST}"
    echo "  Start it with: docker-compose start meilisearch"
    exit 1
fi

# Create a dump
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_UID="meili_dump_${TIMESTAMP}"

echo "Creating dump with UID: ${DUMP_UID}"
DUMP_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
    -H "Content-Type: application/json" \
    "${MEILI_HOST}/dumps" \
    -d "{}")

# Extract dump UID from response
DUMP_UID=$(echo "${DUMP_RESPONSE}" | grep -o '"uid":"[^"]*"' | cut -d'"' -f4)
if [ -z "${DUMP_UID}" ]; then
    echo "✗ Failed to create dump. Response: ${DUMP_RESPONSE}"
    exit 1
fi

echo "✓ Dump created with UID: ${DUMP_UID}"

# Wait for dump to be ready (poll every 5 seconds)
echo "Waiting for dump to be ready..."
MAX_WAIT=300  # 5 minutes
WAITED=0
while [ ${WAITED} -lt ${MAX_WAIT} ]; do
    STATUS_RESPONSE=$(curl -s -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
        "${MEILI_HOST}/dumps/${DUMP_UID}/status")
    
    STATUS=$(echo "${STATUS_RESPONSE}" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [ "${STATUS}" = "done" ]; then
        echo "✓ Dump is ready"
        break
    elif [ "${STATUS}" = "failed" ]; then
        echo "✗ Dump creation failed"
        exit 1
    fi
    
    echo "  Status: ${STATUS:-unknown} (${WAITED}s)"
    sleep 5
    WAITED=$((WAITED + 5))
done

if [ ${WAITED} -ge ${MAX_WAIT} ]; then
    echo "✗ Dump creation timed out after ${MAX_WAIT} seconds"
    exit 1
fi

# Download the dump file
DUMP_FILE="${BACKUP_DIR}/meili_${TIMESTAMP}.dump.gz"
echo "Downloading dump to ${DUMP_FILE}..."

curl -s -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
    "${MEILI_HOST}/dumps/${DUMP_UID}" \
    --output "${DUMP_FILE}"

# Verify download
if [ -f "${DUMP_FILE}" ] && [ -s "${DUMP_FILE}" ]; then
    FILE_SIZE=$(du -h "${DUMP_FILE}" | cut -f1)
    echo "✓ Dump downloaded: ${DUMP_FILE} (${FILE_SIZE})"
else
    echo "✗ Failed to download dump file"
    exit 1
fi

# Remove old Meilisearch dumps
echo "Cleaning up dumps older than ${KEEP_DAYS} days..."
find "${BACKUP_DIR}" -name "meili_*.dump.gz" -mtime +${KEEP_DAYS} -delete 2>/dev/null || true

# List remaining dumps
echo "Current Meilisearch dumps in ${BACKUP_DIR}:"
ls -lh "${BACKUP_DIR}"/meili_*.dump.gz 2>/dev/null || echo "No Meilisearch dumps found"

echo "Meilisearch backup completed successfully!"