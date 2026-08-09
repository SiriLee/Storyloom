"""Task framework — Task, TaskGenerator, TaskPool (Phase 2)."""

from storyloom.tasks._types import Task, TaskTimeoutError, TaskType
from storyloom.tasks._pool import TaskPool
from storyloom.tasks._generator import TaskGenerator
from storyloom.tasks._llm_match import MatchProcessor
from storyloom.tasks._llm_generate import generate_asset_image, GenerateProcessor, select_forced
from storyloom.io.thinking import get_thinking_params  # canonical location: io/

__all__ = [
    "generate_asset_image",
    "GenerateProcessor",
    "MatchProcessor",
    "Task",
    "TaskGenerator",
    "TaskPool",
    "TaskTimeoutError",
    "TaskType",
    "get_thinking_params",
    "select_forced",
]
