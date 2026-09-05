"""Versioned, memory-backed natural episode outcome evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum, IntEnum
from typing import Any

from pvz_reader.versions import OFFSETS, PVZ_VERSION


class GameOutcome(str, Enum):
    RUNNING = "running"
    WON = "won"
    LOST = "lost"
    UNKNOWN = "unknown"


class GameScene(IntEnum):
    LOADING = 0
    MENU = 1
    LEVEL_INTRO = 2
    PLAYING = 3
    ZOMBIES_WON = 4
    AWARD = 5
    CREDIT = 6
    CHALLENGE = 7


class BoardResult(IntEnum):
    NONE = 0
    WON = 1
    LOST = 2
    RESTART = 3
    QUIT = 4
    QUIT_APP = 5
    CHEAT = 6


@dataclass(frozen=True)
class OutcomeEvidence:
    """Raw lifecycle values retained for diagnosis and live validation."""

    outcome: GameOutcome
    reason: str
    lawn_address: int | None = None
    board_address: int | None = None
    game_scene: int | None = None
    board_result: int | None = None
    level_complete: bool | None = None
    level_award_spawned: bool | None = None
    board_fade_out_counter: int | None = None
    next_survival_stage_counter: int | None = None
    error: str | None = None
    loss_cutscene_time: int | None = None
    loss_screen_ready: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        return data


def read_outcome(memory: Any) -> OutcomeEvidence:
    """Read authoritative lifecycle evidence without changing GameState v1.

    A live Board takes precedence over the application result because
    ``mBoardResult`` can retain the preceding episode's value. Once the Board
    is gone, the application result is used to preserve a terminal result
    through the result-screen transition.
    """

    offsets = OFFSETS[PVZ_VERSION]
    try:
        lawn = int(memory.read_pointer(offsets["lawn"]))
        if lawn == 0:
            return OutcomeEvidence(GameOutcome.UNKNOWN, "lawn_unavailable")
        scene = int(memory.read_int(lawn + offsets["game_scene"]))
        result = int(memory.read_int(lawn + offsets["board_result"]))
        board = int(memory.read_pointer(lawn + offsets["board"]))

        if board != 0:
            complete = bool(memory.read_bool(board + offsets["level_complete"]))
            award_spawned = bool(memory.read_bool(board + offsets["level_award_spawned"]))
            fade_out_counter = int(memory.read_int(board + offsets["board_fade_out_counter"]))
            next_survival_stage_counter = int(
                memory.read_int(board + offsets["next_survival_stage_counter"])
            )
            if complete:
                return OutcomeEvidence(
                    GameOutcome.WON, "board_level_complete", lawn, board,
                    scene, result, complete, award_spawned, fade_out_counter,
                    next_survival_stage_counter,
                )
            if award_spawned:
                return OutcomeEvidence(
                    GameOutcome.WON, "board_level_award_spawned", lawn, board,
                    scene, result, complete, award_spawned, fade_out_counter,
                    next_survival_stage_counter,
                )
            if scene == GameScene.ZOMBIES_WON:
                cutscene_time = _read_loss_cutscene_time(memory, board, offsets)
                return OutcomeEvidence(
                    GameOutcome.LOST, "game_scene_zombies_won", lawn, board,
                    scene, result, complete, award_spawned, fade_out_counter,
                    next_survival_stage_counter, None, cutscene_time,
                    cutscene_time is not None and cutscene_time >= 11000,
                )
            if scene in (GameScene.PLAYING, GameScene.CHALLENGE):
                return OutcomeEvidence(
                    GameOutcome.RUNNING, "live_board_playing", lawn, board,
                    scene, result, complete, award_spawned, fade_out_counter,
                    next_survival_stage_counter,
                )
            return OutcomeEvidence(
                GameOutcome.UNKNOWN, "live_board_transition", lawn, board,
                scene, result, complete, award_spawned, fade_out_counter,
                next_survival_stage_counter,
            )

        if result == BoardResult.WON:
            return OutcomeEvidence(
                GameOutcome.WON, "application_board_result", lawn, board,
                scene, result,
            )
        if result == BoardResult.LOST or scene == GameScene.ZOMBIES_WON:
            return OutcomeEvidence(
                GameOutcome.LOST, "application_board_result", lawn, board,
                scene, result,
            )
        return OutcomeEvidence(
            GameOutcome.UNKNOWN, "board_unavailable_no_terminal_result", lawn,
            board, scene, result,
        )
    except Exception as error:
        return OutcomeEvidence(
            GameOutcome.UNKNOWN, "outcome_read_failed",
            error=f"{type(error).__name__}:{error}",
        )


def _read_loss_cutscene_time(memory: Any, board: int, offsets: dict[str, int]) -> int | None:
    """Read the native loss-cutscene timer without weakening outcome evidence."""
    try:
        cutscene = int(memory.read_pointer(board + offsets["cut_scene"]))
        if cutscene == 0:
            return None
        return int(memory.read_int(cutscene + offsets["cut_scene_time"]))
    except Exception:
        return None
