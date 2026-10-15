#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
finish() {
  status=$?
  if [ "$status" -ne 0 ]; then echo "Stopped with an error. See the message above."; fi
  if [ -t 0 ]; then read -r -p "Press Return to close... " ignored; fi
}
trap finish EXIT
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
PYTHON="${POKEMON_PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Install Python 3.11 or newer for macOS from python.org, then run Setup.command again."
  exit 1
fi
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "Python 3.11 or newer is required.")'
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install ./app
cd app
../.venv/bin/python -m pokemon_bot.launcher --self-test
echo "Setup complete. Open StartBot.command to run the bot."
