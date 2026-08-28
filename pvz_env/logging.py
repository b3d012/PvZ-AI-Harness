"""Versioned, deterministic transition records and append-only JSONL storage."""

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Protocol

import numpy as np


TRANSITION_SCHEMA_VERSION = 1


class TransitionSink(Protocol):
    """Persistence seam for completed environment transition records."""

    def write(self, record: "TransitionRecord") -> None: ...


class TransitionLoggingError(RuntimeError):
    """A persistence failure that remains distinct from a gameplay outcome."""

    def __init__(self, message: str, step_result: Any) -> None:
        super().__init__(message)
        self.step_result = step_result


class TransitionLogFormatError(ValueError):
    """A malformed or unsupported JSONL transition record."""


@dataclass(frozen=True)
class ArrayPayload:
    """JSON-compatible array data that preserves reconstruction metadata."""

    dtype: str
    shape: tuple[int, ...]
    values: tuple[Any, ...]

    @classmethod
    def from_array(cls, array: np.ndarray) -> "ArrayPayload":
        contiguous = np.ascontiguousarray(array)
        return cls(
            dtype=contiguous.dtype.name,
            shape=tuple(contiguous.shape),
            values=tuple(contiguous.reshape(-1).tolist()),
        )

    def to_array(self) -> np.ndarray:
        try:
            return np.asarray(self.values, dtype=np.dtype(self.dtype)).reshape(self.shape)
        except (TypeError, ValueError) as error:
            raise TransitionLogFormatError(f"invalid array payload: {error}") from error

    def to_dict(self) -> dict[str, Any]:
        return {"dtype": self.dtype, "shape": list(self.shape), "values": list(self.values)}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ArrayPayload":
        if set(value) != {"dtype", "shape", "values"}:
            raise TransitionLogFormatError("array payload must contain dtype, shape, and values")
        if not isinstance(value["dtype"], str) or not isinstance(value["shape"], list) or not isinstance(value["values"], list):
            raise TransitionLogFormatError("array payload has invalid JSON types")
        return cls(value["dtype"], tuple(value["shape"]), tuple(value["values"]))


def _json_value(value: Any) -> Any:
    """Convert frozen reader/controller values into deterministic JSON values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return ArrayPayload.from_array(value).to_dict()
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(f"value is not transition-serializable: {type(value).__name__}")


def _snapshot_fields(snapshot: Any, prefix: str) -> dict[str, Any]:
    if snapshot is None:
        return {
            f"{prefix}_state": None,
            f"{prefix}_observation": None,
            f"{prefix}_action_mask": None,
        }
    return {
        f"{prefix}_state": _json_value(snapshot.state),
        f"{prefix}_observation": ArrayPayload.from_array(snapshot.observation),
        f"{prefix}_action_mask": ArrayPayload.from_array(snapshot.action_mask),
    }


@dataclass(frozen=True)
class TransitionRecord:
    """A deterministic, JSON-compatible record of exactly one ``step`` call.

    Raw states intentionally remain serialized dictionaries on load rather than
    reconstructed live ``GameState`` instances.  This keeps JSONL portable and
    avoids binding persisted logs to implementation-only dataclass constructors.
    """

    schema_version: int
    episode_id: str
    step_index: int
    action_index: int
    action: dict[str, Any] | None
    action_legal: bool
    rejection_reason: str | None
    before_state: dict[str, Any] | None
    before_observation: ArrayPayload | None
    before_action_mask: ArrayPayload | None
    controller_result: dict[str, Any] | None
    reconciliation: str
    timing: dict[str, Any]
    after_state: dict[str, Any] | None
    after_observation: ArrayPayload | None
    after_action_mask: ArrayPayload | None

    @classmethod
    def from_step_result(
        cls, step_result: Any, *, episode_id: str, step_index: int
    ) -> "TransitionRecord":
        action = step_result.action
        action_data = None if action is None else _json_value(action)
        fields = _snapshot_fields(step_result.before, "before")
        fields.update(_snapshot_fields(step_result.after, "after"))
        return cls(
            schema_version=TRANSITION_SCHEMA_VERSION,
            episode_id=episode_id,
            step_index=step_index,
            action_index=step_result.action_index,
            action=action_data,
            action_legal=step_result.action_legal,
            rejection_reason=_json_value(step_result.rejection_reason),
            before_state=fields["before_state"],
            before_observation=fields["before_observation"],
            before_action_mask=fields["before_action_mask"],
            controller_result=_json_value(step_result.controller_result),
            reconciliation=_json_value(step_result.reconciliation),
            timing=_json_value(step_result.timing),
            after_state=fields["after_state"],
            after_observation=fields["after_observation"],
            after_action_mask=fields["after_action_mask"],
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for name in ("before_observation", "before_action_mask", "after_observation", "after_action_mask"):
            payload = getattr(self, name)
            result[name] = None if payload is None else payload.to_dict()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TransitionRecord":
        required = {field.name for field in cls.__dataclass_fields__.values()}
        if set(value) != required:
            raise TransitionLogFormatError("transition record fields do not match schema v1")
        if value["schema_version"] != TRANSITION_SCHEMA_VERSION:
            raise TransitionLogFormatError(f"unsupported transition schema: {value['schema_version']!r}")
        payloads = {}
        for name in ("before_observation", "before_action_mask", "after_observation", "after_action_mask"):
            item = value[name]
            payloads[name] = None if item is None else ArrayPayload.from_dict(item)
        return cls(
            schema_version=value["schema_version"], episode_id=value["episode_id"],
            step_index=value["step_index"], action_index=value["action_index"],
            action=value["action"], action_legal=value["action_legal"],
            rejection_reason=value["rejection_reason"], before_state=value["before_state"],
            before_observation=payloads["before_observation"],
            before_action_mask=payloads["before_action_mask"],
            controller_result=value["controller_result"], reconciliation=value["reconciliation"],
            timing=value["timing"], after_state=value["after_state"],
            after_observation=payloads["after_observation"], after_action_mask=payloads["after_action_mask"],
        )


class JsonlTransitionSink:
    """Append-only UTF-8 JSONL transition storage with explicit flushing."""

    def __init__(self, path: str | Path, *, create_parents: bool = True, flush: bool = True) -> None:
        self.path = Path(path)
        if create_parents:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._flush = flush
        self._file = self.path.open("a", encoding="utf-8", newline="\n")

    def write(self, record: TransitionRecord) -> None:
        if self._file.closed:
            raise ValueError("transition sink is closed")
        self._file.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
        self._file.write("\n")
        if self._flush:
            self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "JsonlTransitionSink":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def read_transition_jsonl(path: str | Path) -> list[TransitionRecord]:
    """Load independent JSONL lines into serialized ``TransitionRecord`` data."""
    records = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise TransitionLogFormatError(f"malformed JSONL at line {line_number}: {error.msg}") from error
            if not isinstance(value, dict):
                raise TransitionLogFormatError(f"transition line {line_number} is not a JSON object")
            try:
                records.append(TransitionRecord.from_dict(value))
            except TransitionLogFormatError as error:
                raise TransitionLogFormatError(f"invalid transition at line {line_number}: {error}") from error
    return records
