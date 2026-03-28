import boto3
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from dotenv import load_dotenv
from sklearn.ensemble import IsolationForest
from prophet import Prophet
import warnings
warnings.filterwarnings("ignore")

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = os.getenv("DYNAMODB_TABLE", "CostTelemetry")
CONFIDENCE_THRESHOLD = 0.85  # Anomalies above this score get escalated

dynamo = boto3.resource('dynamodb', region_name=REGION)
table = dynamo.Table(TABLE_NAME)


# ─────────────────────────────────────────
# STEP 1: Fetch Data from DynamoDB
# ─────────────────────────────────────────
def fetch_metrics(metric_type="utilization", resource_id=None):
    """Fetch all records of a given metric type from DynamoDB."""
    print(f"  Fetching {metric_type} records from DynamoDB...")
    
    filter_expr = boto3.dynamodb.conditions.Attr("metric_type").eq(metric_type)
    
    if resource_id:
        filter_expr = filter_expr & boto3.dynamodb.conditions.Attr("resource_id").eq(resource_id)
    
    response = table.scan(FilterExpression=filter_expr)
    items = response["Items"]
    
    # Handle pagination
    while "LastEvaluatedKey" in response:
        response = table.scan(
            FilterExpression=filter_expr,
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response["Items"])
    
    print(f"     ✅ Fetched {len(items)} records")
    return items


# ─────────────────────────────────────────
# STEP 2: Prophet — Seasonal Anomaly Detection
# ─────────────────────────────────────────
def detect_with_prophet(items):
    """
    Detects time-series anomalies using Facebook Prophet.
    Flags points that fall outside the uncertainty interval.
    """
    print("\n  [MODEL 1] Running Prophet seasonal detection...")
    
    if len(items) < 10:
        print("     ⚠️  Not enough data for Prophet (need 10+ points) — skipping")
        return []

    # Build dataframe
    df = pd.DataFrame([{
        "ds": pd.to_datetime(item["timestamp"], utc=True).tz_localize(None),
        "y": float(item.get("cpu_utilization", 0))
    } for item in items])

    df = df.sort_values("ds").drop_duplicates("ds").reset_index(drop=True)

    # Train Prophet
    model = Prophet(
        interval_width=0.95,        # 95% confidence interval
        daily_seasonality=True,
        weekly_seasonality=True
    )
    model.fit(df)

    # Predict on same timeframe
    forecast = model.predict(df[["ds"]])

    # Find anomalies: actual value outside predicted interval
    df["yhat"] = forecast["yhat"]
    df["yhat_lower"] = forecast["yhat_lower"]
    df["yhat_upper"] = forecast["yhat_upper"]

    anomalies = df[
        (df["y"] < df["yhat_lower"]) | (df["y"] > df["yhat_upper"])
    ]

    results = []
    for _, row in anomalies.iterrows():
        deviation = abs(row["y"] - row["yhat"])
        range_size = max(row["yhat_upper"] - row["yhat_lower"], 0.001)
        confidence = min(0.99, 0.85 + (deviation / range_size) * 0.1)

        anomaly_type = "idle_instance" if row["y"] < row["yhat_lower"] else "cpu_spike"

        results.append({
            "timestamp": row["ds"].isoformat(),
            "model": "prophet",
            "anomaly_type": anomaly_type,
            "actual_value": round(float(row["y"]), 4),
            "expected_value": round(float(row["yhat"]), 4),
            "confidence": round(confidence, 4)
        })

    print(f"     ✅ Prophet found {len(results)} anomalies")
    return results


# ─────────────────────────────────────────
# STEP 3: Isolation Forest — Multivariate Detection
# ─────────────────────────────────────────
def detect_with_isolation_forest(utilization_items, billing_items):
    """
    Detects multivariate anomalies using Isolation Forest.
    Catches cases where BOTH cost and CPU spike together.
    """
    print("\n  [MODEL 2] Running Isolation Forest multivariate detection...")

    # Build utilization lookup by timestamp (hourly bucketed)
    util_lookup = {}
    for item in utilization_items:
        ts = pd.to_datetime(item["timestamp"], utc=True).tz_localize(None).floor("h")
        util_lookup[ts] = float(item.get("cpu_utilization", 0))

    bill_lookup = {}
    for item in billing_items:
        ts = pd.to_datetime(item["timestamp"], utc=True).tz_localize(None).floor("6h")
        bill_lookup[ts] = float(item.get("cost_usd", 0))

    # Also re-bucket utilization to 6h to match billing frequency
    util_lookup_6h = {}
    for ts, cpu in util_lookup.items():
        bucketed = ts.floor("6h")
        # Average CPU values within the same 6h bucket
        if bucketed not in util_lookup_6h:
            util_lookup_6h[bucketed] = []
        util_lookup_6h[bucketed].append(cpu)
    util_lookup = {ts: sum(vals)/len(vals) for ts, vals in util_lookup_6h.items()}

    # Join on common timestamps
    common_timestamps = set(util_lookup.keys()) & set(bill_lookup.keys())

    if len(common_timestamps) < 5:
        print("     ⚠️  Not enough overlapping data points — skipping")
        return []

    rows = []
    for ts in sorted(common_timestamps):
        rows.append({
            "timestamp": ts,
            "cpu": util_lookup[ts],
            "cost": bill_lookup[ts]
        })

    df = pd.DataFrame(rows)
    features = df[["cpu", "cost"]].values

    # Train Isolation Forest
    model = IsolationForest(
        contamination=0.1,   # Expect ~10% anomalies
        random_state=42
    )
    df["anomaly_score"] = model.fit_predict(features)
    df["raw_score"] = model.score_samples(features)

    # -1 means anomaly in Isolation Forest
    anomalies = df[df["anomaly_score"] == -1]

    results = []
    for _, row in anomalies.iterrows():
        # Normalize score to 0-1 confidence
        confidence = min(0.99, 0.85 + abs(float(row["raw_score"])) * 0.5)

        # Classify anomaly type
        if row["cpu"] > 70 and row["cost"] > 0.5:
            anomaly_type = "runaway_function"
        elif row["cpu"] < 2 and row["cost"] > 0.1:
            anomaly_type = "orphaned_volume"
        elif row["cost"] > 1.0:
            anomaly_type = "cost_spike"
        else:
            anomaly_type = "idle_instance"

        results.append({
            "timestamp": row["timestamp"].isoformat(),
            "model": "isolation_forest",
            "anomaly_type": anomaly_type,
            "cpu_value": round(float(row["cpu"]), 4),
            "cost_value": round(float(row["cost"]), 4),
            "confidence": round(confidence, 4)
        })

    print(f"     ✅ Isolation Forest found {len(results)} anomalies")
    return results


# ─────────────────────────────────────────
# STEP 4: Write Anomalies to DynamoDB
# ─────────────────────────────────────────
def save_anomalies(anomalies):
    """Saves detected anomalies to DynamoDB for Phase 4 to consume."""
    
    dynamo_client = boto3.resource('dynamodb', region_name=REGION)
    
    # Create AnomalyEvents table if it doesn't exist
    existing = [t.name for t in dynamo_client.tables.all()]
    
    if "AnomalyEvents" not in existing:
        print("\n  Creating AnomalyEvents table...")
        new_table = dynamo_client.create_table(
            TableName="AnomalyEvents",
            KeySchema=[
                {"AttributeName": "anomaly_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "anomaly_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST"
        )
        # Wait until table is fully active before writing
        print("     ⏳ Waiting for table to become active...")
        new_table.wait_until_exists()
        print("     ✅ AnomalyEvents table ready")
    anomaly_table = dynamo_client.Table("AnomalyEvents")

    saved = 0
    for i, anomaly in enumerate(anomalies):
        if anomaly["confidence"] >= CONFIDENCE_THRESHOLD:
            anomaly_table.put_item(Item={
                "anomaly_id": f"anomaly-{i}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "timestamp": anomaly["timestamp"],
                "model": anomaly["model"],
                "anomaly_type": anomaly["anomaly_type"],
                "confidence": str(anomaly["confidence"]),
                "status": "pending",   # Phase 4 will update this
                "action_taken": "none"
            })
            saved += 1

    print(f"\n  ✅ Saved {saved} high-confidence anomalies to AnomalyEvents table")
    return saved


# ─────────────────────────────────────────
# MAIN DETECTION RUN
# ─────────────────────────────────────────
def run_detection():
    print(f"\n🔍 Anomaly detection started at {datetime.now(timezone.utc).isoformat()}")
    print(f"   Confidence threshold: {CONFIDENCE_THRESHOLD}\n")

    # Fetch data
    utilization_items = fetch_metrics("utilization")
    billing_items = fetch_metrics("billing")

    # Run both models
    prophet_anomalies = detect_with_prophet(utilization_items)
    iforest_anomalies = detect_with_isolation_forest(utilization_items, billing_items)

    # Combine results
    all_anomalies = prophet_anomalies + iforest_anomalies

    print(f"\n📊 Detection Summary:")
    print(f"   Prophet anomalies:          {len(prophet_anomalies)}")
    print(f"   Isolation Forest anomalies: {len(iforest_anomalies)}")
    print(f"   Total:                      {len(all_anomalies)}")

    if all_anomalies:
        print(f"\n   High-confidence anomalies (≥{CONFIDENCE_THRESHOLD}):")
        for a in all_anomalies:
            if a["confidence"] >= CONFIDENCE_THRESHOLD:
                print(f"   🚨 [{a['model']}] {a['anomaly_type']} at {a['timestamp']} — confidence: {a['confidence']}")

    # Save to DynamoDB
    save_anomalies(all_anomalies)

    print(f"\n✅ Detection run complete\n")

if __name__ == "__main__":
    run_detection()