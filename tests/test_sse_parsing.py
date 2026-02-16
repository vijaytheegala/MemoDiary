import json

def parse_sse_new(chunk_str: str) -> str:
    """
    Simulates the NEW logic in static/script.js
    """
    blocks = chunk_str.split('\n\n')
    
    aiFullText = ""
    
    for block in blocks:
        if not block.strip(): continue
        
        block_lines = block.split('\n')
        data_content = ""
        
        for row in block_lines:
            if row.startswith('event: '):
                pass
            elif row.startswith('data: '):
                data_content = row.replace('data: ', '')
        
        if data_content == '[DONE]': continue
        if not data_content: continue
        
        # NEW LOGIC: Try JSON parse
        text_chunk = data_content
        try:
            data = json.loads(data_content)
            if "text" in data:
                text_chunk = data["text"]
        except:
            pass
            
        aiFullText += text_chunk
        
    return aiFullText

def test_new_logic():
    print("--- Testing NEW Logic (JSON SSE) ---")
    
    # CASE 1: JSON Payload with Newline (The Fix)
    # Server sends: data: {"text": "tasks.\nYou're right"}\n\n
    payload = json.dumps({"text": "tasks.\nYou're right"})
    chunk_json = f"data: {payload}\n\n"
    
    res1 = parse_sse_new(chunk_json)
    expected = "tasks.\nYou're right"
    
    print(f"Case 1 (JSON+Newline): \nComputed: '{res1}'\nExpected: '{expected}'")
    if res1 == expected:
        print(f"{Colors.OKGREEN}[PASS]{Colors.ENDC}")
    else:
        print(f"{Colors.FAIL}[FAIL]{Colors.ENDC}")

    # CASE 2: Legacy Plain Text (Backward Compatibility)
    chunk2 = "data: Hello world\n\n"
    res2 = parse_sse_new(chunk2)
    print(f"Case 2 (Legacy): '{res2}' -> {'PASS' if res2 == 'Hello world' else 'FAIL'}")

# Colors for output
class Colors:
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

if __name__ == "__main__":
    test_new_logic()
