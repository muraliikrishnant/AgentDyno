#!/bin/bash
# Reference solution for task1_fix_add: overwrite the broken `add` with the
# correct implementation (mirrors experiments/tasks/task1_fix_add/solution.py).
set -euo pipefail

cat > broken.py <<'PY'
def add(a, b):
    return a + b
PY
