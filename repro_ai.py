
import asyncio
import os
from unittest.mock import MagicMock, patch
from app.ai import get_ai_response

# Mock storage
mock_storage = MagicMock()
mock_storage.get_user.return_value = {"name": "User", "age": "25", "onboarding_complete": True}
mock_storage.add_entry.return_value = 1

# Mock query engine
mock_query_engine = MagicMock()
# Make it awaitable
f = asyncio.Future()
f.set_result({
    "intent": "personal_recall",
    "search_queries": ["project diary"],
    "date_range": None,
    "language_code": "en"
})
mock_query_engine.analyze_query.return_value = f
mock_query_engine.retrieve_context.return_value = "RELEVANT MEMODIARY ENTRIES:\n- [2024-01-01 10:00:00] I am working on a new project diary app using Python."

# Patch dependencies
@patch("app.ai.storage", mock_storage)
@patch("app.ai.query_engine", mock_query_engine)
async def run_test():
    print("Testing AI Response Logic...")
    
    test_cases = [
        {
            "input": "What did I eat yesterday?", 
            "intent": "personal_recall", 
            "context": "", 
            "desc": "Personal + Empty Context -> Should say 'I don't recall'"
        },
        {
            "input": "What happened in Vizag yesterday?", 
            "intent": "personal_recall",  # Intent might be flagged as personal if user says "what happened"
            "context": "", 
            "desc": "General/Personal Ambiguous + Empty Context -> Should Answer General Knowledge"
        },
        {
            "input": "What is 2+2?", 
            "intent": "general_info", 
            "context": "", 
            "desc": "General -> Should Answer 4"
        }
    ]

    for case in test_cases:
        print(f"\n--- Case: {case['desc']} ---")
        # Mock query engine response
        f = asyncio.Future()
        f.set_result({
            "intent": case['intent'],
            "search_queries": [],
            "date_range": None,
            "language_code": "en"
        })
        mock_query_engine.analyze_query.return_value = f
        
        # Mock retrieve_context to return empty or specific based on test?
        # For these tests, we assume empty context return from retrieval to test Fallback Logic
        mock_query_engine.retrieve_context.return_value = case['context']

        with patch("app.ai.client") as mock_client:
            mock_response = MagicMock()
            mock_response.text = "AI_RESPONSE_PLACEHOLDER"
            mock_client.aio.models.generate_content.return_value = mock_response
            
            await get_ai_response("session_123", [], case['input'])
            
            # Check prompt
            call_args = mock_client.aio.models.generate_content.call_args
            if call_args:
                kwargs = call_args.kwargs
                print(kwargs.get('config').system_instruction)

if __name__ == "__main__":
    asyncio.run(run_test())
