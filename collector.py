import boto3
import os
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from mock_data import get_cost_data_mock

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = os.getenv("DYNAMODB_TABLE", "CostTelemetry")

# Initialize clients
dynamo = boto3.resource('dynamodb', region_name=REGION)
table = dynamo.Table(TABLE_NAME)
cloudwatch = boto3.client('cloudwatch', region_name=REGION)
ec2 = boto3.client('ec2', region_name=REGION)
lambda_client = boto3.client('lambda', region_name=REGION)
s3 = boto3.client('s3', region_name=REGION)


# ─────────────────────────────────────────
# STREAM 1: Billing Metrics (Cost Explorer)
# ─────────────────────────────────────────
def collect_billing_metrics():
    print("  [1/3] Collecting billing metrics...")
    records = get_cost_data_mock()  # Swap with real CE call later

    for record in records:
        table.put_item(Item={
            "resource_id": record["resource_id"],
            "timestamp": record["timestamp"],
            "metric_type": "billing",
            "service": record["service"],
            "region": record["region"],
            "cost_usd": str(record["cost_usd"])  # DynamoDB needs string/Decimal
        })
    print(f"     ✅ Written {len(records)} billing records to DynamoDB")


# ─────────────────────────────────────────
# STREAM 2: Utilization Metrics (CloudWatch)
# ─────────────────────────────────────────
def collect_utilization_metrics():
    print("  [2/3] Collecting utilization metrics...")
    
    # Get all running EC2 instances
    response = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
    
    instances = [
        i for r in response["Reservations"] for i in r["Instances"]
    ]
    
    if not instances:
        print("     ⚠️  No running EC2 instances found — skipping CloudWatch pull")
        return

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=15)

    for instance in instances:
        instance_id = instance["InstanceId"]
        
        # Pull CPU utilization
        cw_response = cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,
            Statistics=["Average"]
        )
        
        datapoints = cw_response.get("Datapoints", [])
        cpu_value = datapoints[-1]["Average"] if datapoints else 0.0

        table.put_item(Item={
            "resource_id": instance_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metric_type": "utilization",
            "service": "Amazon EC2",
            "region": REGION,
            "cpu_utilization": str(round(cpu_value, 4))
        })
        print(f"     ✅ EC2 {instance_id}: CPU {round(cpu_value, 2)}%")


# ─────────────────────────────────────────
# STREAM 3: Resource Inventory
# ─────────────────────────────────────────
def collect_resource_inventory():
    print("  [3/3] Collecting resource inventory...")
    timestamp = datetime.now(timezone.utc).isoformat()

    # EC2 instances
    ec2_resp = ec2.describe_instances()
    for reservation in ec2_resp["Reservations"]:
        for instance in reservation["Instances"]:
            table.put_item(Item={
                "resource_id": instance["InstanceId"],
                "timestamp": timestamp,
                "metric_type": "inventory",
                "service": "Amazon EC2",
                "region": REGION,
                "state": instance["State"]["Name"],
                "instance_type": instance["InstanceType"]
            })

    # Lambda functions
    lambda_resp = lambda_client.list_functions()
    for func in lambda_resp["Functions"]:
        table.put_item(Item={
            "resource_id": func["FunctionName"],
            "timestamp": timestamp,
            "metric_type": "inventory",
            "service": "AWS Lambda",
            "region": REGION,
            "state": "active",
            "instance_type": func["Runtime"]
        })

    # S3 buckets
    s3_resp = s3.list_buckets()
    for bucket in s3_resp["Buckets"]:
        table.put_item(Item={
            "resource_id": bucket["Name"],
            "timestamp": timestamp,
            "metric_type": "inventory",
            "service": "Amazon S3",
            "region": REGION,
            "state": "active",
            "instance_type": "bucket"
        })

    print(f"     ✅ Inventory snapshot written to DynamoDB")


# ─────────────────────────────────────────
# MAIN COLLECTOR RUN
# ─────────────────────────────────────────
def run_collector():
    print(f"\n🚀 Collector run started at {datetime.now(timezone.utc).isoformat()}")
    collect_billing_metrics()
    collect_utilization_metrics()
    collect_resource_inventory()
    print(f"✅ Collector run complete\n")

if __name__ == "__main__":
    run_collector()