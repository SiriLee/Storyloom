"""Storyloom — AI-powered real-time visual novel engine."""

__version__ = "2.2.0"

from storyloom.io.api_client import ApiClient, ApiError, ApiResult
from storyloom.config import WINDOW_SIZE, DEFAULT_MODEL
from storyloom.core.context_manager import ContextManager
from storyloom.core.game_loop import GameLoop, GameState, RoundResult, RoundRecord
from storyloom.core.prompt_builder import PromptBuilder
from storyloom.core.save_manager import SaveManager
from storyloom.core.session import GameSession
from storyloom.user_config import UserConfig

from storyloom.assets import Asset, AssetItem, AssetLibrary, AssetType, GameAssetRoster
from storyloom.parser import ParsedOutput, ParseError, Segment
from storyloom.tasks import Task, TaskGenerator, TaskPool, TaskType

__all__ = [
    "ApiClient",
    "ApiError",
    "ApiResult",
    "Asset",
    "AssetItem",
    "AssetLibrary",
    "AssetType",
    "ContextManager",
    "DEFAULT_MODEL",
    "GameAssetRoster",
    "GameLoop",
    "GameSession",
    "GameState",
    "ParsedOutput",
    "ParseError",
    "PromptBuilder",
    "RoundRecord",
    "RoundResult",
    "SaveManager",
    "Segment",
    "Task",
    "TaskGenerator",
    "TaskPool",
    "TaskType",
    "UserConfig",

    "WINDOW_SIZE",
]
