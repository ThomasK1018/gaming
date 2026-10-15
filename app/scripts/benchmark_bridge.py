#!/usr/bin/env python3
"""JSONL adapter for the isolated local Showdown benchmark."""
import json
import logging
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from altruagent import DecisionContext, GameState, WithReasoning
from pokemon_bot.agent import PokemonAgent


class CaptureWarnings(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


def main():
    agents = {}
    captured = CaptureWarnings()
    logging.getLogger("pokemon_bot").addHandler(captured)
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if message.get("command") == "reset":
                agents.pop(message["session_id"], None)
                print(json.dumps({"ok": True}), flush=True)
                continue
            state_data = message["state"]
            session = state_data["session_id"]
            agent = agents.setdefault(session, PokemonAgent())
            context = DecisionContext(
                session_id=session, tournament_id=None,
                game_type="pokemon_vgc_doubles_draft", agent_id="benchmark-bot",
                seat_position=message["seat_position"],
            )
            start = time.perf_counter()
            captured.messages.clear()
            decision = agent.choose_action(GameState.from_mcp_state(state_data), context)
            elapsed = time.perf_counter() - start
            action = decision.action if isinstance(decision, WithReasoning) else decision
            if hasattr(action, "raw"):
                action = action.raw.get("input", {}).get("action", action.raw)
            print(json.dumps({"action": action, "seconds": elapsed, "warnings": captured.messages}), flush=True)
        except Exception:
            print(json.dumps({"error": traceback.format_exc()}), flush=True)


if __name__ == "__main__":
    main()
