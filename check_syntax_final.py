
import sys
import os

print("--- SYNTAX CHECKER ---")
errors = []

modules = [
    "app.storage",
    "app.memory",
    "app.query",
    "app.main",
    "app.session",
    "app.ai"
]

for mod in modules:
    try:
        print(f"Checking {mod}...", end="")
        __import__(mod)
        print(" OK")
    except Exception as e:
        print(f" FAIL: {e}")
        errors.append(f"{mod}: {e}")

if not errors:
    print("\n✅ All modules import successfully. Syntax is Valid.")
else:
    print(f"\n❌ FOUND {len(errors)} ERRORS.")
    sys.exit(1)
