"""Conservative semantic phase classification from frozen GameState v1."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GamePhase(str, Enum):
    DISCONNECTED = "disconnected"
    MENU_OR_TRANSITION = "menu_or_transition"
    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"
    LEVEL_WON = "level_won"
    LEVEL_LOST = "level_lost"
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        return self in (GamePhase.LEVEL_WON, GamePhase.LEVEL_LOST)


@dataclass(frozen=True)
class PhaseEvidence:
    process_alive: bool
    reader_valid: bool
    state: Any | None
    terminal_hint: GamePhase | None = None


class GamePhaseDetector:
    """Classify only phases supported by current read-only evidence.

    GameState v1 has no authoritative menu/loading or win/loss discriminator.
    A missing Board is therefore ``MENU_OR_TRANSITION`` and natural terminal
    phases require an explicitly validated external hint. Missing-board phase
    changes are debounced for display stability; health still fails closed on
    the first missing state.
    """

    def __init__(self, *, transition_confirmations: int = 2) -> None:
        if transition_confirmations <= 0:
            raise ValueError("transition_confirmations must be positive")
        self.transition_confirmations = transition_confirmations
        self._stable = GamePhase.DISCONNECTED
        self._candidate: GamePhase | None = None
        self._candidate_count = 0

    @property
    def phase(self) -> GamePhase:
        return self._stable

    def reset(self) -> None:
        self._stable = GamePhase.DISCONNECTED
        self._candidate = None
        self._candidate_count = 0

    def detect(self, evidence: PhaseEvidence) -> GamePhase:
        observed = self._classify(evidence)
        if observed is not GamePhase.MENU_OR_TRANSITION:
            self._stable = observed
            self._candidate = None
            self._candidate_count = 0
            return self._stable
        if self._stable in (GamePhase.DISCONNECTED, GamePhase.UNKNOWN, GamePhase.MENU_OR_TRANSITION):
            self._stable = observed
            return self._stable
        if self._candidate is observed:
            self._candidate_count += 1
        else:
            self._candidate = observed
            self._candidate_count = 1
        if self._candidate_count >= self.transition_confirmations:
            self._stable = observed
            self._candidate = None
            self._candidate_count = 0
        return self._stable

    @staticmethod
    def _classify(evidence: PhaseEvidence) -> GamePhase:
        if not evidence.process_alive:
            return GamePhase.DISCONNECTED
        if not evidence.reader_valid:
            return GamePhase.UNKNOWN
        if evidence.terminal_hint is not None:
            if evidence.terminal_hint not in (GamePhase.LEVEL_WON, GamePhase.LEVEL_LOST):
                raise ValueError("terminal_hint must be LEVEL_WON or LEVEL_LOST")
            return evidence.terminal_hint
        state = evidence.state
        if state is None:
            return GamePhase.MENU_OR_TRANSITION
        try:
            if bool(state.paused):
                return GamePhase.PAUSED
            game_clock = int(state.game_clock)
            state.scene
            state.wave
        except (AttributeError, TypeError, ValueError):
            return GamePhase.UNKNOWN
        return GamePhase.READY if game_clock <= 0 else GamePhase.PLAYING
