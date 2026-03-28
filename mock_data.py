from datetime import datetime, timezone

def get_cost_data_mock():
    # .isoformat() converts datetime object to string — required for DynamoDB
    timestamp = datetime.now(timezone.utc).isoformat()
    
    return [
        {
            "timestamp": timestamp,
            "service": "Amazon EC2",
            "region": "us-east-1",
            "cost_usd": 0.023,
            "resource_id": "i-0abc123def456"
        },
        {
            "timestamp": timestamp,
            "service": "AWS Lambda",
            "region": "us-east-1",
            "cost_usd": 0.0,
            "resource_id": "cost-telemetry-collector"
        },
        {
            "timestamp": timestamp,
            "service": "Amazon RDS",
            "region": "us-east-1",
            "cost_usd": 0.017,
            "resource_id": "cost-intelligence-db"
        }
    ]