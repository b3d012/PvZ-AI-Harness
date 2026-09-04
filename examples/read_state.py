"""Print a read-only runtime snapshot from a locally running PvZ client."""

from __future__ import annotations

import json

from pvz_runtime import PvZRuntime


runtime = PvZRuntime()
try:
    print(json.dumps(runtime.snapshot().to_dict(), indent=2, sort_keys=True))
finally:
    runtime.close()
