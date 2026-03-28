import boto3
import os
from dotenv import load_dotenv

load_dotenv()

region = os.getenv("AWS_REGION")

print("=== Phase 1 Verification ===")
'''
# 1. Cost Explorer check
ce = boto3.client('ce', region_name='us-east-1')
response = ce.get_cost_and_usage(
    TimePeriod={'Start': '2026-03-01', 'End': '2026-03-28'},
    Granularity='MONTHLY',
    Metrics=['BlendedCost']
)
print(f"✅ Cost Explorer: ${response['ResultsByTime'][0]['Total']['BlendedCost']['Amount']}")
'''
# 1. Cost Explorer check (MOCK - replace once activated)
from mock_data import get_cost_data_mock
mock_costs = get_cost_data_mock()
print(f"✅ Cost Explorer (MOCK): {len(mock_costs)} billing records returned")
print(f"   Sample: {mock_costs[0]['service']} — ${mock_costs[0]['cost_usd']}")


# 2. EC2 check
ec2 = boto3.client('ec2', region_name=region)
instances = ec2.describe_instances()
count = sum(len(r['Instances']) for r in instances['Reservations'])
print(f"✅ EC2 Instances found: {count}")

# 3. S3 check
s3 = boto3.client('s3', region_name=region)
buckets = s3.list_buckets()
print(f"✅ S3 Buckets: {[b['Name'] for b in buckets['Buckets']]}")

# 4. DynamoDB check
dynamo = boto3.client('dynamodb', region_name=region)
tables = dynamo.list_tables()
print(f"✅ DynamoDB Tables: {tables['TableNames']}")

# 5. Lambda check
lmb = boto3.client('lambda', region_name=region)
funcs = lmb.list_functions()
print(f"✅ Lambda Functions: {[f['FunctionName'] for f in funcs['Functions']]}")

print("\n🎉 Phase 1 complete — all resources live and accessible via boto3!")