#!/bin/bash
# Install pytest and run test_outputs.py against broken.py in the working
# directory (task1_fix_add_harbor/environment/broken.py, uploaded there by
# Harbor's _upload_environment_dir_after_start). Writes reward.txt per the
# Harbor pytest-tests convention (see harbor/cli/template-task/pytest-tests).
set -uo pipefail

pip install --quiet pytest

mkdir -p /logs/verifier
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

pytest /tests/test_outputs.py -rA
status=$?

if [ $status -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

exit $status
