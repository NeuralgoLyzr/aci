#!/bin/bash

set -euo pipefail

echo "🌱 Seeding essential apps only (to avoid timeout)..."

# Seed only essential apps (no OAuth, no CONNECTOR protocol)
python -m aci.cli upsert-app --app-file "./apps/brave_search/app.json" --skip-dry-run
python -m aci.cli upsert-app --app-file "./apps/hackernews/app.json" --skip-dry-run
python -m aci.cli upsert-app --app-file "./apps/arxiv/app.json" --skip-dry-run

echo "📄 Seeding functions for essential apps..."

python -m aci.cli upsert-functions --functions-file "./apps/brave_search/functions.json" --skip-dry-run
python -m aci.cli upsert-functions --functions-file "./apps/hackernews/functions.json" --skip-dry-run
python -m aci.cli upsert-functions --functions-file "./apps/arxiv/functions.json" --skip-dry-run

echo "📋 Creating subscription plans..."
python -m aci.cli populate-subscription-plans --skip-dry-run

echo "🔑 Creating default project and API key..."
python -m aci.cli create-random-api-key --visibility-access public --org-id 107e06da-e857-4864-bc1d-4adcba02ab76

echo "✅ Essential seeding completed!"
