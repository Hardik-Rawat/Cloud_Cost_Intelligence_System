import boto3
import os
from dotenv import load_dotenv

load_dotenv()
REGION = os.getenv("AWS_REGION", "us-east-1")

ec2_client = boto3.client('ec2', region_name=REGION)
lambda_client = boto3.client('lambda', region_name=REGION)

def rollback_all():
    print("\n↩️  Running rollback of all optimization actions...\n")

    # Restart any stopped EC2 instances
    response = ec2_client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )
    for r in response["Reservations"]:
        for instance in r["Instances"]:
            iid = instance["InstanceId"]
            ec2_client.start_instances(InstanceIds=[iid])
            print(f"  ✅ Restarted EC2 instance: {iid}")

    # Remove Lambda concurrency caps
    response = lambda_client.list_functions()
    for func in response["Functions"]:
        name = func["FunctionName"]
        lambda_client.delete_function_concurrency(FunctionName=name)
        print(f"  ✅ Removed concurrency cap from Lambda: {name}")

    print("\n✅ Rollback complete\n")

if __name__ == "__main__":
    rollback_all()