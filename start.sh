#!/usr/bin/env sh
# Same job as start.bat, for macOS and Linux. run.py installs what it needs on first use.
set -u
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 run.py "$@"
fi
if command -v python >/dev/null 2>&1; then
    exec python run.py "$@"
fi
echo
echo "Python was not found on this computer."
echo "Install Python 3.11 or newer from https://www.python.org/downloads/"
echo "and run ./start.sh again."
echo
exit 1
