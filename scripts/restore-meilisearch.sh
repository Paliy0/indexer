#!/bin/bash
# Meilisearch restore script for Site Search Platform
# Restores a Meilisearch index from a dump file

set -e

# Configuration
BACKUP_DIR="backups"
MEILI_HOST="http://localhost:7700"
MEILI_MASTER_KEY="${MEILI_MASTER_KEY:-masterKey}"  # Default from docker-compose

echo "Available Meilisearch dumps:"
ls "${BACKUP_DIR}"/meili_*.dump.gz 2>/dev/null || { echo "No dumps found in ${BACKUP_DIR}"; exit 1; }

# Prompt for dump file if not specified
if [ -z "$1" ]; then
    echo "Enter the dump filename to restore (or press Enter for latest):"
    read -r DUMP_FILE
    if [ -z "${DUMP_FILE}" ]; then
        DUMP_FILE=$(ls -t "${BACKUP_DIR}"/meili_*.dump.gz | head -1)
        echo "Using latest dump: ${DUMP_FILE}"
    fi
else
    DUMP_FILE="$1"
fi

# Validate dump file
if [ ! -f "${DUMP_FILE}" ]; then
    # Check if it's in backup directory
    if [ ! -f "${BACKUP_DIR}/${DUMP_FILE}" ]; then
        echo "Dump file not found: ${DUMP_FILE}"
        exit 1
    fi
    DUMP_FILE="${BACKUP_DIR}/${DUMP_FILE}"
fi

echo "Restoring ${DUMP_FILE} to Meilisearch..."

# Check if Meilisearch is running
if ! curl -s "${MEILI_HOST}/health" > /dev/null 2>&1; then
    echo "✗ Meilisearch is not running at ${MEILI_HOST}"
    echo "  Start it with: docker-compose start meilisearch"
    exit 1
fi

# Check if we're restoring to a production instance
read -p "This will overwrite all current Meilisearch data. Type 'YES' to confirm: " CONFIRM
if [ "${CONFIRM}" != "YES" ]; then
    echo "Restore cancelled."
    exit 0
fi

# Stop application services that use Meilisearch
echo "Stopping application services..."
docker-compose stop app worker 2>/dev/null || true

# Upload and restore the dump
echo "Uploading dump file..."
UPLOAD_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
    -F "dump=@${DUMP_FILE}" \
    "${MEILI_HOST}/dumps")

# Extract task UID from response
TASK_UID=$(echo "${UPLOAD_RESPONSE}" | grep -o '"taskUid":[0-9]*' | cut -d: -f2)
if [ -z "${TASK_UID}" ]; then
    echo "✗ Failed to upload dump. Response: ${UPLOAD_RESPONSE}"
    exit 1
fi

echo "✓ Dump uploaded. Task UID: ${TASK_UID}"

# Wait for restore to complete (poll every 5 seconds)
echo "Waiting for restore to complete..."
MAX_WAIT=600  # 10 minutes (restore can take longer than dump creation)
WAITED=0
while [ ${WAITED} -lt ${MAX_WAIT} ]; do
    TASK_RESPONSE=$(curl -s -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
        "${MEILI_HOST}/tasks/${TASK_UID}")
    
    STATUS=$(echo "${TASK_RESPONSE}" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [ "${STATUS}" = "succeeded" ]; then
        echo "✓ Restore completed successfully"
        break
    elif [ "${STATUS}" = "failed" ]; then
        ERROR=$(echo "${TASK_RESPONSE}" | grep -o '"error":"[^"]*"' | cut -d'"' -f4)
        echo "✗ Restore failed: ${ERROR}"
        exit 1
    fi
    
    echo "  Status: ${STATUS:-unknown} (${WAITED}s)"
    sleep 5
    WAITED=$((WAITED + 5))
done

if [ ${WAITED} -ge ${MAX_WAIT} ]; then
    echo "✗ Restore timed out after ${MAX_WAIT} seconds"
    exit 1
fi

# Verify indexes were restored
echo "Checking restored indexes..."
INDEX_RESPONSE=$(curl -s -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \
    "${MEILI_HOST}/indexes")

INDEX_COUNT=$(echo "${INDEX_RESPONSE}" | grep -o '"uid":"[^"]*"' | wc -l)
echo "✓ ${INDEX_COUNT} indexes restored"

# Restart services
echo "Restarting application services..."
docker-compose start app worker 2>/dev/null || true

echo "Meilisearch restore complete!"