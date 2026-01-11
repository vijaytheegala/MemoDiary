
import sys

try:
    from app import main
    print("Syntax OK. App imported successfully.")
except Exception as e:
    print(f"Syntax Error or Import Error: {e}")
    import traceback
    traceback.print_exc()
