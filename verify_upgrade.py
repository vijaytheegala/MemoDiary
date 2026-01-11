
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Mock storage to avoid messing with real DB if we can, 
# but integration test on real DB is better for "deployment readiness".
# We will use a TEST session ID.

from app.storage import storage
from app.query import query_engine

TEST_SESSION = "deployment_test_session"

def safe_print(text):
    try:
        print(text)
    except:
        print(text.encode('ascii', 'replace').decode('ascii'))

print("--- FUNCTIONAL TEST: AUDIT UPGRADES ---")

# 1. Test Storage: Daily Metrics
try:
    print("[1] Testing Storage: upsert_daily_metrics...")
    today = datetime.now().strftime("%Y-%m-%d")
    storage.upsert_daily_metrics(TEST_SESSION, today, energy=8, stress=2, sleep=7)
    
    # Retrieve
    metrics = storage.get_daily_metrics_range(TEST_SESSION, today, today)
    if metrics and metrics[0]['energy'] == 8:
        print("    [OK] Metrics saved and retrieved.")
    else:
        print(f"    [FAIL] Metrics mismatch: {metrics}")
        sys.exit(1)
except Exception as e:
    print(f"    [CRITICAL FAIL] Storage Error: {e}")
    sys.exit(1)

# 2. Test Query Logic: Trend Analysis Context
try:
    print("\n[2] Testing Query Engine: retrieve_context (Trend Analysis)...")
    analysis = {
        "intent": "trend_analysis",
        "metrics": ["energy"],
        "start_date": today,
        "end_date": today
    }
    context = query_engine.retrieve_context(TEST_SESSION, analysis)
    
    if "Date:" in context and "Energy: 8/10" in context:
        print("    [OK] Trend Context generated correctly.")
        safe_print(f"    Content Preview: {context.strip()}")
    else:
        print("    [FAIL] Context generation failed.")
        safe_print(f"    Actual: {context}")
        sys.exit(1)

except Exception as e:
    print(f"    [CRITICAL FAIL] Query Logic Error: {e}")
    sys.exit(1)

# 3. Test Query Logic: Data Review
try:
    print("\n[3] Testing Query Engine: retrieve_context (Data Review)...")
    analysis = {"intent": "data_review"}
    context = query_engine.retrieve_context(TEST_SESSION, analysis)
    
    if "CONFIDENTIAL USER DATA REPORT" in context:
        print("    [OK] Data Review context generated.")
    else:
        print("    [FAIL] Data Review header missing.")
        sys.exit(1)

except Exception as e:
    print(f"    [CRITICAL FAIL] Query Logic Error: {e}")
    sys.exit(1)

print("\n------------------------------------------------")
print("[SUCCESS] All Audit Compliance Upgrades Verified.")
print("------------------------------------------------")
