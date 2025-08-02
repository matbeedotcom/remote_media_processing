#!/usr/bin/env python3
"""
Test the time-based conversation history logic without loading ML dependencies.
"""

from datetime import datetime, timedelta


def test_time_based_filtering():
    """Test the time-based history filtering logic."""
    
    print("=== Time-Based History Filtering Logic Test ===")
    
    # Configuration
    conversation_history_minutes = 5.0
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(minutes=conversation_history_minutes)
    
    print(f"History window: {conversation_history_minutes} minutes")
    print(f"Current time: {current_time.isoformat()}")
    print(f"Cutoff time: {cutoff_time.isoformat()}")
    
    # Create test conversation history with different timestamps
    test_history = [
        # Old messages (should be filtered out)
        {
            "role": "user",
            "content": "What's the weather like?",
            "timestamp": (current_time - timedelta(minutes=10)).isoformat()
        },
        {
            "role": "assistant", 
            "content": "I don't have access to weather data.",
            "timestamp": (current_time - timedelta(minutes=10)).isoformat()
        },
        # Messages from 6 minutes ago (should be filtered out)
        {
            "role": "user",
            "content": "Tell me a joke",
            "timestamp": (current_time - timedelta(minutes=6)).isoformat()
        },
        {
            "role": "assistant",
            "content": "Why did the chicken cross the road?", 
            "timestamp": (current_time - timedelta(minutes=6)).isoformat()
        },
        # Recent messages (should be kept)
        {
            "role": "user",
            "content": "My name is Alice",
            "timestamp": (current_time - timedelta(minutes=4)).isoformat()
        },
        {
            "role": "assistant",
            "content": "Nice to meet you, Alice!",
            "timestamp": (current_time - timedelta(minutes=4)).isoformat()
        },
        {
            "role": "user",
            "content": "I like cats",
            "timestamp": (current_time - timedelta(minutes=2)).isoformat()
        },
        {
            "role": "assistant",
            "content": "Cats are wonderful pets!",
            "timestamp": (current_time - timedelta(minutes=2)).isoformat()
        },
        {
            "role": "user",
            "content": "What's my name?",
            "timestamp": current_time.isoformat()
        }
    ]
    
    print(f"\nInitial history: {len(test_history)} messages")
    
    # Simulate the filtering logic
    print("\nFiltering messages:")
    filtered_history = []
    turns_for_model = [{"role": "system", "content": "You are a helpful assistant."}]
    
    for msg in test_history:
        if isinstance(msg, dict) and 'timestamp' in msg:
            msg_time = datetime.fromisoformat(msg['timestamp'])
            age_minutes = (current_time - msg_time).total_seconds() / 60
            
            if msg_time >= cutoff_time:
                # This message is within the time window
                filtered_history.append(msg)
                # Add to turns for the model (without timestamp)
                if msg.get("role") != "system":
                    turns_for_model.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
                print(f"  ✓ KEPT: [{msg['role']:9}] '{msg['content'][:30]}...' (age: {age_minutes:.1f} min)")
            else:
                print(f"  ✗ FILTERED: [{msg['role']:9}] '{msg['content'][:30]}...' (age: {age_minutes:.1f} min)")
    
    print(f"\nResults:")
    print(f"  Original messages: {len(test_history)}")
    print(f"  Filtered messages: {len(filtered_history)}")
    print(f"  Messages removed: {len(test_history) - len(filtered_history)}")
    print(f"  Turns for model: {len(turns_for_model)} (including system message)")
    
    # Show what the model would see
    print("\nConversation context the model would receive:")
    for i, turn in enumerate(turns_for_model):
        role = turn['role'].upper()
        content = turn['content'][:50] + "..." if len(turn['content']) > 50 else turn['content']
        print(f"  {i+1}. [{role:9}] {content}")
    
    # Demonstrate adding a new message with automatic filtering
    print("\n--- Adding new message and filtering ---")
    
    # Add response to the last question
    new_response = {
        "role": "assistant",
        "content": "Your name is Alice, as you told me 4 minutes ago.",
        "timestamp": current_time.isoformat()
    }
    
    # Combine and filter
    all_history = test_history + [new_response]
    final_filtered = []
    
    for msg in all_history:
        if isinstance(msg, dict) and 'timestamp' in msg:
            msg_time = datetime.fromisoformat(msg['timestamp'])
            if msg_time >= cutoff_time:
                final_filtered.append(msg)
    
    print(f"After adding new response:")
    print(f"  Total messages: {len(all_history)}")
    print(f"  Within time window: {len(final_filtered)}")
    
    # Show the benefit of time-based history
    print("\n--- Benefits of Time-Based History ---")
    print("1. Predictable memory usage: History is bounded by time, not message count")
    print("2. Natural conversation flow: Recent context is preserved regardless of message frequency")
    print("3. Automatic cleanup: Old messages are filtered out automatically")
    print("4. Better for long conversations: Doesn't arbitrarily cut off at N messages")
    print(f"5. In this example: The assistant remembers Alice's name from 4 minutes ago!")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_time_based_filtering()