# ☁️ AWS Cost Intelligence System

A real-world cloud cost intelligence platform that connects to a live AWS account, detects genuine cost anomalies using ML, and autonomously executes safe optimizations through AWS APIs — all visualized on a real-time dashboard.

---

## 🏗️ System Architecture

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
```

---

## 📁 Project Structure

```
Cloud_Cost_Intelligence_System/
│
├── .env.example                  ← Copy to .env and fill in values
├── .gitignore
├── requirements.txt
├── README.md
├── RUNBOOK.md                    ← Full operational guide
│
├── mock_data.py                  ← Phase 1: Mock Cost Explorer billing data
├── verify_phase1.py              ← Phase 1: Verify all AWS resources are live
│
├── collector.py                  ← Phase 2: Telemetry pipeline (3 metric streams)
│
├── generate_training_data.py     ← Phase 3: Synthetic historical data generator
├── anomaly_detector.py           ← Phase 3: Prophet + Isolation Forest ML models
│
├── optimization_engine.py        ← Phase 4: Autonomous optimization engine
├── rollback.py                   ← Phase 4: Undo all optimization actions
│
├── dashboard_api.py              ← Phase 5: Flask REST API (4 endpoints)
├── dashboard.html                ← Phase 5: React dashboard (single file)
├── run_pipeline.py               ← Phase 5: Runs full pipeline every 15 min
│
├── test_pipeline.py              ← Phase 6: 18 automated tests (pytest)
└── validate_savings.py           ← Phase 6: Cost attribution validator
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- AWS account (free tier works)
- Windows (PowerShell) or Linux/macOS

### 1. Clone the repo
```bash
git clone https://github.com/Hardik-Rawat/Cloud_Cost_Intelligence_System.git
cd Cloud_Cost_Intelligence_System
```

### 2. Create virtual environment
```powershell
# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your AWS credentials and resource details
```

### 5. Configure AWS CLI
```bash
aws configure
# Enter your Access Key ID, Secret, region (us-east-1), and output format (json)
```

---

## 📋 Phase-by-Phase Setup

### Phase 1 — Foundation & Cloud Provisioning
Provision AWS resources manually via AWS Console:
- IAM Role (`CostIntelligenceLambdaRole`) + IAM User (`cost-intelligence-local`)
- EC2 `t2.micro` instance
- S3 bucket
- RDS `db.t2.micro` PostgreSQL
- DynamoDB table (`CostTelemetry`)
- Lambda function (`cost-telemetry-collector`)

Verify everything is working:
```bash
python verify_phase1.py
```

### Phase 2 — Telemetry Pipeline
Collect 3 metric streams every 15 minutes into DynamoDB:
```bash
python collector.py
```

### Phase 3 — ML Anomaly Detection
Generate synthetic training data then run both ML models:
```bash
python generate_training_data.py
python anomaly_detector.py
```

### Phase 4 — Autonomous Optimization Engine
Execute safe, reversible actions on detected anomalies:
```bash
python optimization_engine.py

# To undo all actions:
python rollback.py
```

### Phase 5 — Real-Time Dashboard
Open two PowerShell/terminal windows:

**Window 1 — API:**
```bash
python dashboard_api.py
```

**Window 2 — Pipeline:**
```bash
python run_pipeline.py
```

Then open `dashboard.html` in your browser.

### Phase 6 — Validation & Testing
```bash
# Run full test suite (18 tests)
pytest test_pipeline.py -v --html=test_report.html

# Validate cost savings attribution
python validate_savings.py
```

---

## 🤖 ML Models

### Facebook Prophet
- Detects **seasonal time-series anomalies**
- Learns daily/weekly CPU usage patterns
- Flags points outside the 95% confidence interval
- Anomaly types: `idle_instance`, `cpu_spike`

### Isolation Forest (scikit-learn)
- Detects **multivariate point anomalies**
- Combines CPU utilization + billing cost simultaneously
- Catches runaway functions where both metrics spike together
- Anomaly types: `cost_spike`, `runaway_function`, `orphaned_volume`

### Confidence Threshold
Default: `0.85` — tune in `anomaly_detector.py`:
| Value | Effect |
|---|---|
| 0.70 | More detections, higher false-positive rate |
| 0.85 | Default balanced setting |
| 0.95 | Fewer detections, very high precision |

---

## ⚙️ Optimization Actions

| Anomaly Type | Action | Reversible? |
|---|---|---|
| `idle_instance` | Stop EC2 instance | ✅ Yes — `aws ec2 start-instances` |
| `cpu_spike` | Cap Lambda concurrency | ✅ Yes — `aws lambda delete-function-concurrency` |
| `runaway_function` | Cap Lambda concurrency | ✅ Yes |
| `cost_spike` | Tag resource for review | ✅ Yes — `aws ec2 delete-tags` |
| `orphaned_volume` | Tag resource for review | ✅ Yes |

**Circuit breaker:** Max 5 actions per engine run to prevent runaway automation.

---

## 📊 Dashboard Panels

| Panel | Data Source | Refresh |
|---|---|---|
| Cost Trend Chart | `CostTelemetry` DynamoDB | 60s |
| Anomaly Feed | `AnomalyEvents` DynamoDB | 60s |
| Optimization Log | `OptimizationAudit` DynamoDB | 60s |
| Savings Summary | `OptimizationAudit` DynamoDB | 60s |

---

## 🛠️ IAM Policy

The IAM user/role needs this policy (`CostIntelligencePolicy`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics",
        "ec2:DescribeInstances",
        "ec2:StopInstances",
        "ec2:StartInstances",
        "ec2:CreateTags",
        "ec2:DeleteTags",
        "lambda:ListFunctions",
        "lambda:PutFunctionConcurrency",
        "lambda:DeleteFunctionConcurrency",
        "lambda:GetFunctionConcurrency",
        "lambda:GetAccountSettings",
        "s3:ListAllMyBuckets",
        "rds:DescribeDBInstances",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "dynamodb:ListTables",
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:DescribeTable",
        "dynamodb:BatchWriteItem",
        "dynamodb:CreateTable"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 🔄 Swapping Mock → Real Cost Explorer

Once Cost Explorer activates (24hr after enabling in AWS Console),
replace the mock in `collector.py` — see `RUNBOOK.md` for the exact code swap.

---

## 🧪 Test Results

Run the full suite:
```bash
pytest test_pipeline.py -v
```

| Test Class | Tests | What It Covers |
|---|---|---|
| `TestCollector` | 5 | All 3 metric streams, field validation |
| `TestCPUSpikeDetection` | 2 | CPU spike injection + confidence threshold |
| `TestIdleInstanceDetection` | 2 | Idle instance injection + status check |
| `TestCostSpikeDetection` | 1 | Cost spike storage validation |
| `TestOptimizationEngine` | 4 | Audit records, rollback commands, circuit breaker |
| `TestDashboardAPI` | 3 | All API endpoints |
| `TestEndToEnd` | 1 | Full pipeline inject → detect → action → audit |

---

## 🔧 Troubleshooting

| Error | Fix |
|---|---|
| `AccessDeniedException` | Add the missing action to `CostIntelligencePolicy` in IAM |
| `ResourceNotFoundException` | DynamoDB table doesn't exist — check table names in `.env` |
| `TypeError: Unsupported type datetime` | Call `.isoformat()` on all datetime objects |
| `Cannot compare tz-naive and tz-aware` | Use `pd.to_datetime(ts, utc=True).tz_localize(None)` |
| `InvalidParameterValueException` (Lambda) | Free-tier concurrency limit hit — system falls back to tagging |
| Prophet needs more data | Run `generate_training_data.py` |
| Dashboard shows stale data | Click ⟳ Refresh or restart `run_pipeline.py` |

---

## 📖 Full Operational Guide

See [RUNBOOK.md](./RUNBOOK.md) for:
- How to tune the confidence threshold
- How to add a new AWS resource type
- How to roll back specific actions
- How to swap mock data for real Cost Explorer
- Architecture deep-dive

---

## 🏷️ Tech Stack

| Layer | Technology |
|---|---|
| Cloud | AWS (EC2, Lambda, S3, RDS, DynamoDB, CloudWatch, Cost Explorer) |
| SDK | boto3 (Python) |
| ML | Facebook Prophet, scikit-learn Isolation Forest |
| Backend | Flask, flask-cors |
| Frontend | React 18 (CDN), Chart.js |
| Testing | pytest, pytest-html |
| Data | pandas, numpy |

---

## ⚠️ Important Notes

- **Never commit `.env`** — it contains your AWS credentials. It is gitignored.
- The system only uses **free-tier AWS resources** — costs should be $0 or near $0.
- All optimization actions are **safe and reversible** — run `rollback.py` anytime.
- The circuit breaker limits actions to **5 per run** to prevent accidental over-automation.

---

## 📄 License

MIT License — free to use, modify, and distribute.