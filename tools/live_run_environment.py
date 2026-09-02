"""Manual live validation runner for frozen Environment v1.

Prepare an unpaused PvZ level yourself. Dry-run is the default and never
issues mouse input. Execute mode requires ``--execute`` and a bounded horizon.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvz_controller import PvZController
from pvz_env import (
    EpisodeConfig, JsonlTransitionSink, PvZEnvironment, RandomPolicyConfig,
    RandomValidActionPolicy, SimpleHeuristicPolicy, decode_action,
    environment_contract, run_episode,
)
from pvz_reader.game_state import PvZGameStateReader
from pvz_reader.memory import MemoryReader


PROCESS_NAME = "PlantsVsZombies.exe"


def _active_rows(value: str) -> tuple[bool, ...]:
    try:
        rows = {int(item.strip()) for item in value.split(",") if item.strip()}
    except ValueError as error:
        raise argparse.ArgumentTypeError("active rows must be comma-separated integers 1 through 6") from error
    if not rows or not rows <= set(range(1, 7)):
        raise argparse.ArgumentTypeError("active rows must be non-empty and in the range 1 through 6")
    return tuple(row in rows for row in range(1, 7))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live Environment v1 validation; dry-run by default.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--active-rows", type=_active_rows, help="1-based active rows, e.g. 2,3,4")
    group.add_argument("--all-rows", action="store_true", help="explicitly configure all six rows as active")
    parser.add_argument("--execute", action="store_true", help="enable real Controller v1 mouse input")
    parser.add_argument("--policy", choices=("random", "heuristic"), default="heuristic")
    parser.add_argument("--seed", type=int, default=0, help="random-policy seed")
    parser.add_argument("--max-steps", type=int, default=10, help="bounded step horizon (must be positive)")
    parser.add_argument("--episode-id", default="live-environment-v1")
    parser.add_argument("--log-path", type=Path, help="optional ignored JSONL trajectory path")
    return parser


def _policy(arguments: argparse.Namespace):
    if arguments.policy == "random":
        return RandomValidActionPolicy(RandomPolicyConfig(arguments.seed))
    return SimpleHeuristicPolicy()


def main() -> int:
    arguments = _parser().parse_args()
    if arguments.max_steps <= 0:
        raise SystemExit("--max-steps must be positive")
    rows = (True,) * 6 if arguments.all_rows else arguments.active_rows
    reader = PvZGameStateReader(MemoryReader(PROCESS_NAME))
    policy = _policy(arguments)
    config = EpisodeConfig(arguments.episode_id, active_rows=rows, max_steps=arguments.max_steps)

    if not arguments.execute:
        environment = PvZEnvironment(reader, PvZController())
        reset = environment.reset(config)
        decision = policy.select_action(reset.observation, reset.action_mask, state=reset.state)
        print("DRY RUN: no Controller action or mouse input will be issued.")
        print(f"contract={environment_contract().to_dict()}")
        print(f"episode={reset.episode_id} lifecycle={reset.lifecycle.value} active_rows={rows}")
        print(f"observation_shape={reset.observation.shape} action_mask_shape={reset.action_mask.shape}")
        print(f"decision={decode_action(decision.action_index)} reason={decision.reason} legal={bool(reset.action_mask[decision.action_index])}")
        print("Natural win/loss detection is unavailable; execute runs end at the configured max-step truncation unless a future detector is supplied.")
        return 0

    print("EXECUTE MODE: Controller v1 may send normal Windows mouse input to PvZ.")
    print("Confirm that the prepared, unpaused PvZ level is visible and focused. Ctrl+C stops the run.")
    sink = JsonlTransitionSink(arguments.log_path) if arguments.log_path else None
    try:
        environment = PvZEnvironment(reader, PvZController(), transition_sink=sink)

        def report(decision, result) -> None:
            print(
                f"action={decode_action(decision.action_index)} reason={decision.reason} "
                f"reward={result.outcome.reward:.4f} reconciliation={result.reconciliation.value} "
                f"outcome={None if result.outcome.reason is None else result.outcome.reason.value}"
            )

        result = run_episode(environment, policy, config, on_step=report)
        print(f"episode_result={result}")
        return 0
    except KeyboardInterrupt:
        print("Interrupted by user; no additional action will be issued.")
        return 130
    finally:
        if sink is not None:
            sink.close()


if __name__ == "__main__":
    raise SystemExit(main())
