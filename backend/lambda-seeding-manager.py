import json
import boto3
from typing import Dict, Any, List
import os
from datetime import datetime

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'aci-seeding-state')
table = dynamodb.Table(table_name)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda function to manage ACI seeding state
    
    Endpoints:
    - GET /seeding-status -> Check if seeding is done
    - POST /seeding-status -> Update seeding status
    - GET /seeding-scripts -> Get list of seeding scripts
    - POST /seeding-scripts -> Update list of seeding scripts
    """
    
    try:
        # Parse the event
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '/seeding-status')
        body = event.get('body')
        
        if body:
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        else:
            body = {}
        
        # Route to appropriate handler
        if path == '/seeding-status':
            if http_method == 'GET':
                return get_seeding_status()
            elif http_method == 'POST':
                return update_seeding_status(body)
        elif path == '/seeding-scripts':
            if http_method == 'GET':
                return get_seeding_scripts()
            elif http_method == 'POST':
                return update_seeding_scripts(body)
        
        return {
            'statusCode': 404,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Endpoint not found'})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }


def get_seeding_status() -> Dict[str, Any]:
    """Check if seeding has been completed"""
    try:
        response = table.get_item(Key={'key_name': 'seeding_status'})
        
        if 'Item' in response:
            item = response['Item']
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'isSeeded': item.get('isSeeded', False),
                    'lastSeededAt': item.get('lastSeededAt'),
                    'seedingVersion': item.get('seedingVersion', '1.0'),
                    'environment': item.get('environment', 'unknown')
                })
            }
        else:
            # First time - no seeding done
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'isSeeded': False,
                    'lastSeededAt': None,
                    'seedingVersion': '1.0',
                    'environment': 'unknown'
                })
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': f'Error checking seeding status: {str(e)}'})
        }


def update_seeding_status(body: Dict[str, Any]) -> Dict[str, Any]:
    """Update seeding status"""
    try:
        is_seeded = body.get('isSeeded', False)
        environment = body.get('environment', 'unknown')
        seeding_version = body.get('seedingVersion', '1.0')
        
        table.put_item(
            Item={
                'key_name': 'seeding_status',
                'isSeeded': is_seeded,
                'lastSeededAt': datetime.utcnow().isoformat(),
                'seedingVersion': seeding_version,
                'environment': environment,
                'updatedAt': datetime.utcnow().isoformat()
            }
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Seeding status updated successfully',
                'isSeeded': is_seeded,
                'environment': environment
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': f'Error updating seeding status: {str(e)}'})
        }


def get_seeding_scripts() -> Dict[str, Any]:
    """Get list of seeding scripts to run"""
    try:
        response = table.get_item(Key={'key_name': 'seeding_scripts'})
        
        if 'Item' in response:
            item = response['Item']
            scripts = item.get('scripts', get_default_scripts())
        else:
            scripts = get_default_scripts()
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'scripts': scripts,
                'totalScripts': len(scripts)
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': f'Error getting seeding scripts: {str(e)}'})
        }


def update_seeding_scripts(body: Dict[str, Any]) -> Dict[str, Any]:
    """Update list of seeding scripts"""
    try:
        scripts = body.get('scripts', get_default_scripts())
        
        table.put_item(
            Item={
                'key_name': 'seeding_scripts',
                'scripts': scripts,
                'updatedAt': datetime.utcnow().isoformat()
            }
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Seeding scripts updated successfully',
                'totalScripts': len(scripts)
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': f'Error updating seeding scripts: {str(e)}'})
        }


def get_default_scripts() -> List[Dict[str, Any]]:
    """Default list of seeding scripts"""
    return [
        {
            'name': 'run_seed_db_sh',
            'description': 'Run the seed_db.sh script with --all --mock flags to seed all apps and functions',
            'order': 1,
            'enabled': True,
            'type': 'shell',
            'commands': [
                'bash scripts/seed_db.sh --all --mock'
            ]
        }
    ]
