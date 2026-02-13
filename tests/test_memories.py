import os
import json
import pytest
from bot.memories import save_memory, get_memories, MEMORIES_FILE

@pytest.fixture
def temp_memories_file(tmp_path, monkeypatch):
    """Use a temporary file for memories during tests."""
    test_file = tmp_path / "memories.json"
    monkeypatch.setattr("bot.memories.MEMORIES_FILE", str(test_file))
    return test_file

def test_save_memory(temp_memories_file):
    author = "TestUser#1234"
    content = "This is a funny quote!"
    
    save_memory(author, content)
    
    assert temp_memories_file.exists()
    with open(temp_memories_file, "r") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["author"] == author
        assert data[0]["content"] == content
        assert "timestamp" in data[0]

def test_get_memories_limit(temp_memories_file):
    for i in range(10):
        save_memory(f"User{i}", f"Memory {i}")
    
    # Test default limit (5)
    memories = get_memories()
    assert len(memories) == 5
    assert memories[0]["content"] == "Memory 5"
    assert memories[-1]["content"] == "Memory 9"
    
    # Test custom limit
    memories_all = get_memories(limit=10)
    assert len(memories_all) == 10
    assert memories_all[0]["content"] == "Memory 0"

def test_get_memories_empty(temp_memories_file):
    assert get_memories() == []
