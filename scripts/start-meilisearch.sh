#!/bin/bash

# Start Meilisearch with configuration from environment variables
# This script starts Meilisearch on port 7700 with a master key for authentication

# Set default values if not provided
MEILI_MASTER_KEY=${MEILI_MASTER_KEY:-"your-development-master-key"}
MEILI_HTTP_ADDR=${MEILI_HTTP_ADDR:-"127.0.0.1:7700"}
MEILI_DB_PATH=${MEILI_DB_PATH:-"./data/meili_data"}
MEILI_ENV=${MEILI_ENV:-"development"}

# Create data directory if it doesn't exist
mkdir -p "$MEILI_DB_PATH"

echo "Starting Meilisearch..."
echo "Master Key: ${MEILI_MASTER_KEY:0:10}..."
echo "Address: $MEILI_HTTP_ADDR"
echo "Database Path: $MEILI_DB_PATH"
echo "Environment: $MEILI_ENV"
echo ""

# Start Meilisearch
/usr/local/bin/meilisearch \
  --master-key "$MEILI_MASTER_KEY" \
  --http-addr "$MEILI_HTTP_ADDR" \
  --db-path "$MEILI_DB_PATH" \
  --env "$MEILI_ENV"
