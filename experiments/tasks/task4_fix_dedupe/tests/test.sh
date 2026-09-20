#!/bin/sh
set -u
mkdir -p /logs/verifier
python - <<'PY'
import runpy
import sys

sys.path.insert(0, "/app")
namespace = runpy.run_path("/tests/test_broken.py")
cases = [
    (name, value)
    for name, value in namespace.items()
    if name.startswith("test_") and callable(value)
]
if not cases:
    raise SystemExit("no test cases found")
for name, test in cases:
    test()
    print(f"PASS {name}")
PY
status=$?
if [ "$status" -eq 0 ]; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf '0\n' > /logs/verifier/reward.txt
fi
exit "$status"
