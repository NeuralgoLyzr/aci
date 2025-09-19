#!/bin/bash

# Setup SharePoint integration by fetching secrets from DynamoDB
# and running the upsert commands

set -e

echo "🚀 Setting up SharePoint integration..."

# Check if we're in the right directory
if [ ! -f "apps/share_point/app.json" ]; then
    echo "❌ Please run this script from the backend directory"
    exit 1
fi

# Fetch secrets from DynamoDB and create .app.secrets.json
echo "📥 Fetching secrets from DynamoDB..."
python scripts/get_sharepoint_secrets.py

# Check if secrets file was created
if [ ! -f "apps/share_point/.app.secrets.json" ]; then
    echo "❌ Failed to create secrets file. Make sure secrets are stored in DynamoDB."
    exit 1
fi

echo "📦 Upserting SharePoint app..."
docker compose exec runner python -m aci.cli upsert-app \
    --app-file ./apps/share_point/app.json \
    --secrets-file ./apps/share_point/.app.secrets.json \
    --skip-dry-run

echo "🔧 Upserting SharePoint functions..."
docker compose exec runner python -m aci.cli upsert-functions \
    --functions-file ./apps/share_point/functions.json \
    --skip-dry-run

echo "✅ SharePoint integration setup complete!"
echo ""
echo "You can now test the SharePoint integration in the playground."