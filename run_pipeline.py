import subprocess
import time
from datetime import datetime, timezone

scripts = [
    "collector.py",
    "anomaly_detector.py",
    "optimization_engine.py"
]

print("🔄 Pipeline runner started — runs every 15 minutes")
print("   Keep this running alongside dashboard_api.py\n")

while True:
    print(f"\n{'='*50}")
    print(f"Pipeline run at {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*50}")
    
    for script in scripts:
        print(f"\n▶ Running {script}...")
        result = subprocess.run(
            ["python", script],
            capture_output=False
        )
        if result.returncode != 0:
            print(f"  ⚠️  {script} exited with errors — continuing pipeline")

    print(f"\n✅ Pipeline complete — next run in 15 minutes")
    time.sleep(900)  # 15 minutes