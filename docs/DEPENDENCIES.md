# Phase 1–2 dependencies

The frozen Phase 1–2 stack intentionally remains small:

- Python 3.12
- `pymem==1.14.0` — Windows process-memory access used by the reader
- `psutil==7.2.2` — process discovery
- `numpy==2.5.2` — numerical dependency already part of the project environment and retained for the upcoming observation-encoding work

The canonical Conda environment is `environment.yml`; `requirements.txt` mirrors the pip packages for CI and simple installs.

Deep-learning and RL packages such as Gymnasium, PyTorch and Stable-Baselines3 are deliberately not pinned yet. They will be introduced with the Phase 3/4 code that uses them, avoiding unnecessary dependencies before the environment interface is defined.
