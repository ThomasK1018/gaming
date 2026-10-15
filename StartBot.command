#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
finish() {
  status=$?
  if [ "$status" -ne 0 ]; then echo "Stopped with an error. See the message above."; fi
  if [ -t 0 ]; then read -r -p "Press Return to close... " ignored; fi
}
trap finish EXIT
if [ ! -x .venv/bin/python ]; then
  echo "Run Setup.command first."
  exit 1
fi
cd app
../.venv/bin/python -X utf8 -m pokemon_bot.launcher "$@"
