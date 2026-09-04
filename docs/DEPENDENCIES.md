# Dependencies

The frozen Phase 1–3.5 harness intentionally remains small:

- Python 3.12
- `pymem==1.14.0` — Windows process-memory access used by the reader
- `psutil==7.2.2` — process discovery
- `numpy==2.5.2` — numerical dependency already part of the project environment and retained for the upcoming observation-encoding work

The canonical Conda environment is `environment.yml`; `requirements.txt`
mirrors the pip packages for CI and simple installs. The public package metadata
in `pyproject.toml` exposes the same runtime requirements; install the harness
with `python -m pip install -e .`.

Deep-learning and RL packages such as Gymnasium, PyTorch and Stable-Baselines3
are deliberately not pinned yet. They belong to Phase 4 learning work, not the
frozen Environment v1/runtime harness.
