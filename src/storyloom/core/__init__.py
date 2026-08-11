"""Core game logic — game loop, co-creation, context management, prompt building."""

from storyloom.core.game_loop import GameLoop, GameState, RoundResult, RoundRecord
from storyloom.core.co_create import CoCreateFlow, CoCreateError, CoCreateCancelled, CoCreateValidator
from storyloom.core.context_manager import ContextManager
from storyloom.core.prompt_builder import PromptBuilder
from storyloom.core.session import GameSession
from storyloom.core.state_manager import StateManager
from storyloom.core.event_dispatcher import EventDispatcher
from storyloom.core.prebuild import Prebuilder, EntitySpec, SelectionResult, PrebuildResult
from storyloom.core.update_manager import (
    VersionInfo,
    UpdateCheckResult,
    UpdateProgress,
    check_for_updates,
    download_and_extract,
)

__all__ = [
    "CoCreateFlow",
    "CoCreateError",
    "CoCreateCancelled",
    "CoCreateValidator",
    "ContextManager",
    "EntitySpec",
    "EventDispatcher",
    "GameLoop",
    "GameSession",
    "GameState",
    "Prebuilder",
    "PrebuildResult",
    "PromptBuilder",
    "RoundRecord",
    "RoundResult",
    "SelectionResult",
    "StateManager",
    "UpdateCheckResult",
    "UpdateProgress",
    "VersionInfo",
    "check_for_updates",
    "download_and_extract",
]
