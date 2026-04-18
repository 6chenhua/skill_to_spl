"""Checkpoint management for pipeline steps."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Type alias for serializer function
DefaultSerializer = Callable[[Any], str]


class DataclassEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles dataclasses, sets, and other special types."""
    
    def default(self, o: Any) -> Any:
        """Convert special types to JSON-serializable formats."""
        # Handle dataclass instances
        if is_dataclass(o):
            return asdict(o)  # type: ignore
        
        # Handle sets - convert to sorted list for reproducibility
        if isinstance(o, set):
            return sorted(list(o))
        
        # Handle frozenset - convert to sorted list
        if isinstance(o, frozenset):
            return sorted(list(o))
        
        # Handle tuples - convert to list
        if isinstance(o, tuple):
            return list(o)
        
        # Handle Enum - get value
        if isinstance(o, Enum):
            return o.value
        
        # Handle Path - convert to string
        if isinstance(o, Path):
            return str(o)
        
        # Handle bytes - convert to base64 string
        if isinstance(o, bytes):
            import base64
            return base64.b64encode(o).decode('utf-8')
        
        # Handle any object with __dict__ as a last resort
        if hasattr(o, '__dict__'):
            return o.__dict__
        
        # Let the base class handle it or raise TypeError
        return super().default(o)


def _default_serializer(obj: Any) -> str:
    """Default JSON serializer that handles dataclasses and nested structures.
    
    Args:
        obj: Object to serialize
        
    Returns:
        JSON string
    """
    return json.dumps(obj, cls=DataclassEncoder, indent=2, ensure_ascii=False)


def _default_deserializer(json_str: str) -> Any:
    """Default JSON deserializer.
    
    Args:
        json_str: JSON string to deserialize
        
    Returns:
        Python object
    """
    return json.loads(json_str)


class CheckpointManager:
    """Checkpoint manager for saving and loading step results.

    Saves intermediate results to disk to enable pipeline resumption
    from any stage. Supports custom serialization.

    Example:
        manager = CheckpointManager()
        manager.save("step1", result, Path("output/"))
        loaded = manager.load("step1", Path("output/"))
    """

    def __init__(
        self,
        serializer: Optional[DefaultSerializer] = None,
        deserializer: Optional[Callable[[str], Any]] = None,
    ):
        """Initialize checkpoint manager.

        Args:
            serializer: Custom serializer function (default: dataclass-aware JSON)
            deserializer: Custom deserializer function (default: json.loads)
        """
        self.serializer = serializer or _default_serializer
        self.deserializer = deserializer or _default_deserializer

    def save(self, step_name: str, data: Any, output_dir: Path) -> Path:
        """Save checkpoint for a step.

        Args:
            step_name: Name of the step
            data: Data to checkpoint (must be serializable)
            output_dir: Output directory

        Returns:
            Path to saved checkpoint file

        Raises:
            Exception: If serialization or write fails (logged as warning)
        """
        checkpoint_path = output_dir / f"{step_name}.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            content = self.serializer(data)
            checkpoint_path.write_text(content, encoding="utf-8")
            logger.debug("Checkpoint saved: %s", checkpoint_path)
            return checkpoint_path
        except Exception as e:
            logger.warning("Failed to save checkpoint for %s: %s", step_name, e)
            raise

    def load(self, step_name: str, output_dir: Path) -> Optional[Any]:
        """Load checkpoint for a step.

        Args:
            step_name: Name of the step
            output_dir: Output directory

        Returns:
            Checkpointed data, or None if not found or load failed
        """
        checkpoint_path = output_dir / f"{step_name}.json"

        if not checkpoint_path.exists():
            return None

        try:
            content = checkpoint_path.read_text(encoding="utf-8")
            return self.deserializer(content)
        except Exception as e:
            logger.warning("Failed to load checkpoint for %s: %s", step_name, e)
            return None

    def exists(self, step_name: str, output_dir: Path) -> bool:
        """Check if checkpoint exists for a step.

        Args:
            step_name: Name of the step
            output_dir: Output directory

        Returns:
            True if checkpoint exists
        """
        checkpoint_path = output_dir / f"{step_name}.json"
        return checkpoint_path.exists()

    def clear(self, output_dir: Path) -> None:
        """Clear all checkpoints in output directory.

        Args:
            output_dir: Output directory containing checkpoints
        """
        import shutil

        if output_dir.exists():
            shutil.rmtree(output_dir)
            logger.info("Cleared checkpoints: %s", output_dir)

    def list_checkpoints(self, output_dir: Path) -> list[str]:
        """List all checkpoints in output directory.

        Args:
            output_dir: Output directory

        Returns:
            List of step names with checkpoints
        """
        if not output_dir.exists():
            return []

        checkpoints = []
        for path in output_dir.glob("*.json"):
            checkpoints.append(path.stem)
        return sorted(checkpoints)

    def delete(self, step_name: str, output_dir: Path) -> bool:
        """Delete checkpoint for a step.

        Args:
            step_name: Name of the step
            output_dir: Output directory

        Returns:
            True if checkpoint was deleted, False if not found
        """
        checkpoint_path = output_dir / f"{step_name}.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.debug("Deleted checkpoint: %s", checkpoint_path)
            return True
        return False
