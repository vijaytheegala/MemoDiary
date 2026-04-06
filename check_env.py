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

key = os.getenv("GROQ_API_KEY")

print("\n--- Environment Check ---")
if key:
    print(f"[OK] GROQ_API_KEY is set (Length: {len(key)})")
    if key.startswith("gsk_"):
        print("   Key format check: Parsable (Starts with gsk_)")
    else:
        print("   [WARN] Key format warning: Does not start with 'gsk_'. Might be invalid.")
else:
    print("[FAIL] GROQ_API_KEY is NOT set.")
    print("   Please create a .env file or export the variable.")
