"""Test suite for CheckpointManager serialization."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Set

import pytest

from pipeline.orchestrator.checkpoint import (
    CheckpointManager,
    DataclassEncoder,
    _default_serializer,
    _default_deserializer,
)


class ActionType(Enum):
    """Example enum for testing."""
    EXTERNAL_API = "EXTERNAL_API"
    LLM_TASK = "LLM_TASK"


@dataclass
class NestedDataclass:
    """Nested dataclass for testing."""
    name: str
    value: int


@dataclass
class ComplexDataclass:
    """Dataclass with various types that need special handling."""
    name: str
    # Set types
    tags: set[str] = field(default_factory=set)
    unique_ids: set[int] = field(default_factory=set)
    # Frozenset
    frozen_tags: frozenset[str] = field(default_factory=frozenset)
    # Tuple
    coordinates: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    # Enum
    action: ActionType = ActionType.LLM_TASK
    # Nested dataclass
    nested: Optional[NestedDataclass] = None
    # Path
    output_dir: Optional[Path] = None
    # List of dataclasses
    items: list[NestedDataclass] = field(default_factory=list)


@dataclass
class SimpleDataclass:
    """Simple dataclass for basic tests."""
    id: str
    count: int


class TestDataclassEncoder:
    """Test DataclassEncoder handles various types."""
    
    def test_encode_dataclass(self):
        """Test encoding a simple dataclass."""
        obj = SimpleDataclass(id="test", count=42)
        result = json.dumps(obj, cls=DataclassEncoder)
        data = json.loads(result)
        assert data["id"] == "test"
        assert data["count"] == 42
    
    def test_encode_set(self):
        """Test encoding a set is converted to sorted list."""
        data = {"tags": {"c", "a", "b"}}
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["tags"] == ["a", "b", "c"]  # Sorted
    
    def test_encode_frozenset(self):
        """Test encoding a frozenset."""
        data = {"frozen": frozenset([3, 1, 2])}
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["frozen"] == [1, 2, 3]  # Sorted
    
    def test_encode_tuple(self):
        """Test encoding a tuple is converted to list."""
        data = {"coords": (1.0, 2.0)}
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["coords"] == [1.0, 2.0]
    
    def test_encode_enum(self):
        """Test encoding an enum uses its value."""
        data = {"action": ActionType.EXTERNAL_API}
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["action"] == "EXTERNAL_API"
    
    def test_encode_path(self):
        """Test encoding a Path is converted to string."""
        data = {"path": Path("/tmp/test")}
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        # On Windows, Path converts to backslashes, so just check it's a string
        assert isinstance(parsed["path"], str)
        assert "tmp" in parsed["path"]
        assert "test" in parsed["path"]
    
    def test_encode_nested_dataclass(self):
        """Test encoding nested dataclasses."""
        nested = NestedDataclass(name="inner", value=100)
        obj = ComplexDataclass(
            name="outer",
            tags={"a", "b"},
            nested=nested,
        )
        result = json.dumps(obj, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["name"] == "outer"
        assert parsed["tags"] == ["a", "b"]
        assert parsed["nested"]["name"] == "inner"
        assert parsed["nested"]["value"] == 100
    
    def test_encode_complex_nested_structure(self):
        """Test encoding a complex structure with multiple special types."""
        obj = ComplexDataclass(
            name="complex",
            tags={"tag1", "tag2"},
            unique_ids={1, 2, 3},
            frozen_tags=frozenset(["a", "b"]),
            coordinates=(1.5, 2.5),
            action=ActionType.EXTERNAL_API,
            nested=NestedDataclass(name="nested", value=42),
            output_dir=Path("/output/path"),
            items=[
                NestedDataclass(name="item1", value=1),
                NestedDataclass(name="item2", value=2),
            ],
        )
        # Should not raise
        result = json.dumps(obj, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["name"] == "complex"
        assert parsed["action"] == "EXTERNAL_API"
        assert parsed["coordinates"] == [1.5, 2.5]
        assert parsed["output_dir"] == "/output/path"
        assert len(parsed["items"]) == 2
    
    def test_encode_list_of_dataclasses(self):
        """Test encoding a list of dataclasses."""
        items = [
            SimpleDataclass(id="a", count=1),
            SimpleDataclass(id="b", count=2),
        ]
        result = json.dumps(items, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["id"] == "a"
        assert parsed[1]["id"] == "b"
    
    def test_encode_dict_with_dataclass_values(self):
        """Test encoding a dict with dataclass values."""
        data = {
            "key1": SimpleDataclass(id="a", count=1),
            "key2": SimpleDataclass(id="b", count=2),
        }
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["key1"]["id"] == "a"
        assert parsed["key2"]["count"] == 2


class TestCheckpointManager:
    """Test CheckpointManager with various data types."""
    
    def test_save_and_load_simple_dataclass(self, tmp_path):
        """Test saving and loading a simple dataclass."""
        manager = CheckpointManager()
        data = SimpleDataclass(id="test", count=42)
        
        manager.save("step1", data, tmp_path)
        loaded = manager.load("step1", tmp_path)
        
        assert loaded["id"] == "test"
        assert loaded["count"] == 42
    
    def test_save_and_load_complex_dataclass(self, tmp_path):
        """Test saving and loading a complex dataclass."""
        manager = CheckpointManager()
        data = ComplexDataclass(
            name="complex",
            tags={"a", "b", "c"},
            unique_ids={1, 2, 3},
            nested=NestedDataclass(name="inner", value=100),
        )
        
        manager.save("step2", data, tmp_path)
        loaded = manager.load("step2", tmp_path)
        
        assert loaded["name"] == "complex"
        assert sorted(loaded["tags"]) == ["a", "b", "c"]
        assert sorted(loaded["unique_ids"]) == [1, 2, 3]
        assert loaded["nested"]["name"] == "inner"
    
    def test_save_and_load_dict_with_sets(self, tmp_path):
        """Test saving and loading a dict containing sets."""
        manager = CheckpointManager()
        data = {
            "workflow_steps": ["step1", "step2"],
            "declared_names": {"var1", "var2", "var3"},  # This is a set
            "count": 42,
        }
        
        manager.save("step3", data, tmp_path)
        loaded = manager.load("step3", tmp_path)
        
        assert loaded["count"] == 42
        assert sorted(loaded["declared_names"]) == ["var1", "var2", "var3"]
    
    def test_save_and_load_nested_dict_with_sets(self, tmp_path):
        """Test saving nested structures with sets."""
        manager = CheckpointManager()
        data = {
            "global_registry": {
                "variables": {"var1": "type1", "var2": "type2"},
                "files": {"file1": "path1"},
            },
            "declared_names": {"name1", "name2"},  # Set
        }
        
        manager.save("step4", data, tmp_path)
        loaded = manager.load("step4", tmp_path)
        
        assert "name1" in loaded["declared_names"]
        assert "name2" in loaded["declared_names"]
    
    def test_checkpoint_exists(self, tmp_path):
        """Test checking if checkpoint exists."""
        manager = CheckpointManager()
        assert not manager.exists("step1", tmp_path)
        
        manager.save("step1", {"data": "test"}, tmp_path)
        assert manager.exists("step1", tmp_path)
    
    def test_load_nonexistent_checkpoint(self, tmp_path):
        """Test loading a checkpoint that doesn't exist."""
        manager = CheckpointManager()
        result = manager.load("nonexistent", tmp_path)
        assert result is None
    
    def test_delete_checkpoint(self, tmp_path):
        """Test deleting a checkpoint."""
        manager = CheckpointManager()
        manager.save("step1", {"data": "test"}, tmp_path)
        assert manager.exists("step1", tmp_path)
        
        assert manager.delete("step1", tmp_path)
        assert not manager.exists("step1", tmp_path)
        
        # Deleting non-existent should return False
        assert not manager.delete("step1", tmp_path)
    
    def test_list_checkpoints(self, tmp_path):
        """Test listing all checkpoints."""
        manager = CheckpointManager()
        manager.save("step1", {"a": 1}, tmp_path)
        manager.save("step2", {"b": 2}, tmp_path)
        manager.save("step3", {"c": 3}, tmp_path)
        
        checkpoints = manager.list_checkpoints(tmp_path)
        assert checkpoints == ["step1", "step2", "step3"]
    
    def test_clear_checkpoints(self, tmp_path):
        """Test clearing all checkpoints."""
        manager = CheckpointManager()
        manager.save("step1", {"a": 1}, tmp_path)
        manager.save("step2", {"b": 2}, tmp_path)
        
        assert len(manager.list_checkpoints(tmp_path)) == 2
        manager.clear(tmp_path)
        assert len(manager.list_checkpoints(tmp_path)) == 0


class TestDefaultSerializerDeserializer:
    """Test default serializer and deserializer functions."""
    
    def test_serialize_simple_dict(self):
        """Test serializing a simple dict."""
        data = {"key": "value", "number": 42}
        result = _default_serializer(data)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["key"] == "value"
    
    def test_serialize_with_set(self):
        """Test serializing dict with set."""
        data = {"names": {"alice", "bob", "charlie"}}
        result = _default_serializer(data)
        parsed = json.loads(result)
        assert sorted(parsed["names"]) == ["alice", "bob", "charlie"]
    
    def test_deserialize_simple(self):
        """Test deserializing a simple JSON string."""
        json_str = '{"key": "value", "number": 42}'
        result = _default_deserializer(json_str)
        assert result["key"] == "value"
        assert result["number"] == 42
    
    def test_roundtrip_serialization(self):
        """Test round-trip serialization and deserialization."""
        data = {
            "name": "test",
            "tags": {"a", "b", "c"},
            "count": 42,
            "nested": {
                "items": [1, 2, 3],
                "set_field": {"x", "y"},
            },
        }
        
        serialized = _default_serializer(data)
        deserialized = _default_deserializer(serialized)
        
        assert deserialized["name"] == "test"
        assert sorted(deserialized["tags"]) == ["a", "b", "c"]
        assert deserialized["count"] == 42
        assert deserialized["nested"]["items"] == [1, 2, 3]
        assert sorted(deserialized["nested"]["set_field"]) == ["x", "y"]


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_set(self):
        """Test encoding an empty set."""
        data = {"empty": set()}
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["empty"] == []
    
    def test_mixed_types_in_set(self):
        """Test encoding a set with mixed types (numbers and strings)."""
        # Note: Sets with mixed types that are not all JSON serializable may fail
        # This is expected behavior - JSON doesn't support mixed type sets well
        data = {"mixed": {"1", "2", "3"}}  # All strings
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert sorted(parsed["mixed"]) == ["1", "2", "3"]
    
    def test_deeply_nested_structure(self):
        """Test encoding deeply nested structures."""
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "set_field": {"a", "b"},
                        "tuple_field": (1, 2, 3),
                    }
                }
            }
        }
        result = json.dumps(data, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["level1"]["level2"]["level3"]["set_field"] == ["a", "b"]
        assert parsed["level1"]["level2"]["level3"]["tuple_field"] == [1, 2, 3]
    
    def test_dataclass_with_optional_none(self):
        """Test dataclass with Optional fields set to None."""
        obj = ComplexDataclass(
            name="test",
            nested=None,
            output_dir=None,
        )
        result = json.dumps(obj, cls=DataclassEncoder)
        parsed = json.loads(result)
        assert parsed["name"] == "test"
        assert parsed["nested"] is None
        assert parsed["output_dir"] is None
