import json
import os
import logging
from datetime import datetime

MEMORIES_FILE = os.path.join("data", "memories.json")

def save_memory(author: str, content: str):
    """Save a memory to the JSON file."""
    memory = {
        "author": author,
        "content": content,
        "timestamp": datetime.now().isoformat()
    }
    
    memories = []
    if os.path.exists(MEMORIES_FILE):
        try:
            with open(MEMORIES_FILE, "r") as f:
                memories = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load memories: {e}")

    memories.append(memory)

    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(MEMORIES_FILE), exist_ok=True)
        with open(MEMORIES_FILE, "w") as f:
            json.dump(memories, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save memory: {e}")

def get_memories(limit: int = 5):
    """Retrieve the last N memories."""
    if not os.path.exists(MEMORIES_FILE):
        return []
    
    try:
        with open(MEMORIES_FILE, "r") as f:
            memories = json.load(f)
            # Return last N, but keep the chronological order for the output
            return memories[-limit:]
    except Exception as e:
        logging.error(f"Failed to retrieve memories: {e}")
        return []
