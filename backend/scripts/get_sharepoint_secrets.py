#!/usr/bin/env python3
"""
Script to fetch SharePoint secrets from DynamoDB and create the .app.secrets.json file
"""

import json
import boto3
import os
from pathlib import Path

def get_sharepoint_secrets_from_dynamodb():
    """Fetch SharePoint secrets from DynamoDB"""
    try:
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'aci-seeding-state')
        table = dynamodb.Table(table_name)

        # Get SharePoint secrets
        response = table.get_item(Key={'key_name': 'app_secrets_share_point'})

        if 'Item' in response:
            secrets = response['Item'].get('secrets', {})
            print(f"✅ Retrieved SharePoint secrets from DynamoDB")
            return secrets
        else:
            print("❌ No SharePoint secrets found in DynamoDB")
            return None

    except Exception as e:
        print(f"❌ Error retrieving secrets from DynamoDB: {str(e)}")
        return None

def create_secrets_file(secrets):
    """Create the .app.secrets.json file for SharePoint"""
    if not secrets:
        print("❌ No secrets to write")
        return False

    try:
        # Create the SharePoint app directory if it doesn't exist
        app_dir = Path(__file__).parent.parent / "apps" / "share_point"
        app_dir.mkdir(parents=True, exist_ok=True)

        # Create the secrets file
        secrets_file = app_dir / ".app.secrets.json"

        with open(secrets_file, 'w') as f:
            json.dump(secrets, f, indent=2)

        print(f"✅ Created secrets file: {secrets_file}")
        return True

    except Exception as e:
        print(f"❌ Error creating secrets file: {str(e)}")
        return False

def main():
    """Main function"""
    print("🔐 Fetching SharePoint secrets from DynamoDB...")

    # Get secrets from DynamoDB
    secrets = get_sharepoint_secrets_from_dynamodb()

    if secrets:
        # Create the secrets file
        if create_secrets_file(secrets):
            print("✅ SharePoint secrets setup complete!")
            print("\nNow you can run:")
            print("docker compose exec runner python -m aci.cli upsert-app --app-file ./apps/share_point/app.json --secrets-file ./apps/share_point/.app.secrets.json --skip-dry-run")
            print("docker compose exec runner python -m aci.cli upsert-functions --functions-file ./apps/share_point/functions.json --skip-dry-run")
        else:
            print("❌ Failed to create secrets file")
    else:
        print("❌ Failed to retrieve secrets from DynamoDB")
        print("\nMake sure you have:")
        print("1. Added SharePoint secrets to DynamoDB with key: 'app_secrets_share_point'")
        print("2. Configured AWS credentials")
        print("3. Set DYNAMODB_TABLE_NAME environment variable (default: 'aci-seeding-state')")

if __name__ == "__main__":
    main()