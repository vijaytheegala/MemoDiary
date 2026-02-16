import os
from dotenv import load_dotenv
from pathlib import Path

# Try to load .env from the same directory or parent
env_path = Path(".env")
if not env_path.exists():
    print("[WARN] .env file NOT found in current directory.")
else:
    print(f"[OK] .env file found at {env_path.absolute()}")
    load_dotenv(dotenv_path=env_path)

key = os.getenv("GEMINI_API_KEY")

print("\n--- Environment Check ---")
if key:
    print(f"[OK] GEMINI_API_KEY is set (Length: {len(key)})")
    if key.startswith("AIza"):
        print("   Key format check: Parsable (Starts with AIza)")
    else:
        print("   [WARN] Key format warning: Does not start with 'AIza'. Might be invalid.")
else:
    print("[FAIL] GEMINI_API_KEY is NOT set.")
    print("   Please create a .env file or export the variable.")
