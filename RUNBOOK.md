# AWS Cost Intelligence System — Operational Runbook

## Quick Start
| Task | Command |
|---|---|
| Start dashboard API | `python dashboard_api.py` |
| Run full pipeline once | `python run_pipeline.py` (exits after 1 run) |
| Run pipeline continuously | Keep `run_pipeline.py` running |
| Roll back all actions | `python rollback.py` |
| Validate savings | `python validate_savings.py` |
| Run test suite | `pytest test_pipeline.py -v` |

---

## How to Tune the Confidence Threshold

**File:** `anomaly_detector.py`
**Variable:** `CONFIDENCE_THRESHOLD = 0.85`

| Value | Effect |
|---|---|
| 0.70 | More anomalies detected, more false positives |
| 0.85 | Default — good balance |
| 0.95 | Fewer detections, very high precision only |

Change and re-run `anomaly_detector.py` — no other files need updating.

---

## How to Add a New Resource Type

Example: Adding ElastiCache monitoring

1. **Add collector stream** in `collector.py`:
```python
elasticache = boto3.client('elasticache', region_name=REGION)
clusters = elasticache.describe_cache_clusters()
for cluster in clusters["CacheClusters"]:
    table.put_item(Item={
        "resource_id": cluster["CacheClusterId"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metric_type": "inventory",
        "service": "ElastiCache",
        "region": REGION,
        "state": cluster["CacheClusterStatus"],
        "instance_type": cluster["CacheNodeType"]
    })
```
2. **Add IAM permission:** `elasticache:DescribeCacheClusters`
3. **Add anomaly rule** in `optimization_engine.py` ACTION_RULES dict
4. **Add action function** following the same pattern as `stop_ec2_instance`

---

## How to Roll Back Any Optimization Action

Every action in `OptimizationAudit` has a `rollback_command` field.

**Option A — Roll back everything:**
```powershell
python rollback.py
```

**Option B — Roll back a specific action manually:**
```powershell
# Restart a specific EC2 instance
aws ec2 start-instances --instance-ids i-0aa9b48a77f3f6bd7

# Remove Lambda concurrency cap
aws lambda delete-function-concurrency --function-name cost-telemetry-collector

# Remove review tags
aws ec2 delete-tags --resources i-0aa9b48a77f3f6bd7 --tags Key=review-needed
```

---

## How to Swap Mock Cost Data for Real Cost Explorer

**Once Cost Explorer is activated (24hr after enabling):**

In `collector.py`, replace:
```python
from mock_data import get_cost_data_mock
records = get_cost_data_mock()
```

With:
```python
ce = boto3.client('ce', region_name='us-east-1')
response = ce.get_cost_and_usage(
    TimePeriod={
        "Start": (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"),
        "End": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    },
    Granularity="DAILY",
    Metrics=["BlendedCost"],
    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]
)
records = []
for result in response["ResultsByTime"]:
    for group in result["Groups"]:
        records.append({
            "resource_id": group["Keys"][0],
            "service": group["Keys"][0],
            "region": REGION,
            "cost_usd": float(group["Metrics"]["BlendedCost"]["Amount"]),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
```

---

## Troubleshooting Common Errors

| Error | Fix |
|---|---|
| `AccessDeniedException` | Add the missing action to `CostIntelligencePolicy` in IAM |
| `ResourceNotFoundException` | DynamoDB table doesn't exist — check table names in `.env` |
| `TypeError: Unsupported type datetime` | Call `.isoformat()` on all datetime objects before storing |
| `Cannot compare tz-naive and tz-aware` | Use `pd.to_datetime(ts, utc=True).tz_localize(None)` |
| Prophet needs more data | Run `generate_training_data.py` to add synthetic history |
| Isolation Forest skipping | Not enough overlapping billing+utilization timestamps |
| Dashboard shows stale data | Click ⟳ Refresh or restart `run_pipeline.py` |

---

## System Architecture Summary
```
Collector (every 15 min)
    ↓ writes to
CostTelemetry (DynamoDB)
    ↓ read by
Anomaly Detector
  ├── Prophet (seasonal time-series)
  └── Isolation Forest (multivariate)
    ↓ writes to
AnomalyEvents (DynamoDB)
    ↓ read by
Optimization Engine
  ├── stop_ec2_instance
  ├── cap_lambda_concurrency
  └── tag_resource_for_review
    ↓ writes to
OptimizationAudit (DynamoDB)
    ↓ read by
Dashboard API (Flask :5000)
    ↓ served to
dashboard.html (React, auto-refreshes 60s)
