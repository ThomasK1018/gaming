import ast
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from collections import OrderedDict

from .dex import norm
from .legal import enumerate_actions, validate_action

_LOG = logging.getLogger(__name__)


def _observation(state):
    raw = getattr(state, 'raw', {}) or {}
    value = raw.get('observation', getattr(state, 'observation', {}))
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if isinstance(value, str) and len(value) <= 2_000_000:
        for parse in (json.loads, ast.literal_eval):
            try:
                parsed = parse(value)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, SyntaxError, TypeError, RecursionError):
                pass
    return {}


class PokemonAgent:
    def __init__(self):
        self.sessions = OrderedDict()
        self.memory = {}

    def __call__(self, state, context=None):
        return self.choose_action(state, context)

    def choose_action(self, state, context=None):
        from .battle import choose_battle
        from .draft import choose_draft, choose_lineup
        game = (getattr(context, 'game_type', '') or (getattr(state, 'raw', {}) or {}).get('game_type', ''))
        if game and game != 'pokemon_vgc_doubles_draft':
            raise ValueError('This agent supports pokemon_vgc_doubles_draft only.')
        legal = getattr(state, 'legal_actions', []) or []
        if not legal:
            raise ValueError('No legal action is available.')
        sid = getattr(state, 'session_id', '') or getattr(context, 'session_id', '') or 'local'
        if sid not in self.sessions:
            self.sessions[sid] = {'sets': {}, 'decisions': OrderedDict()}
            if len(self.sessions) > 32:
                self.sessions.popitem(last=False)
        memory = self.memory = self.sessions[sid]
        obs = _observation(state)
        rosters = obs.get('rosters') or {}
        lists = [obs.get('available_cards', []), obs.get('your_roster', []), obs.get('opponent_roster', [])]
        lists += list(rosters.values()) if isinstance(rosters, dict) else []
        for cards in lists:
            if not isinstance(cards, list):
                continue
            for card in cards:
                if isinstance(card, dict) and card.get('species'):
                    ident = norm(card['species'])
                    old = memory['sets'].get(ident, {})
                    memory['sets'][ident] = {**old, **{k: v for k, v in card.items() if v not in (None, {}, [])}}
        signature = json.dumps({'phase': getattr(state, 'phase', ''), 'version': getattr(state, 'state_version', 0), 'obs': obs, 'legal': [a.input for a in legal]}, sort_keys=True, default=str)
        key = hashlib.sha256(signature.encode()).hexdigest()
        if key in memory['decisions']:
            return copy.deepcopy(memory['decisions'][key])
        if all(a.action_id.startswith('draft_pick:') for a in legal):
            try:
                result = choose_draft(obs, legal, memory, getattr(context, 'agent_id', '') or '')
            except Exception:
                _LOG.exception('Draft evaluation failed; selecting an offered card.')
                result = legal[0]
            if result not in legal:
                result = legal[0]
        else:
            template = next((a.input.get('action') for a in legal if isinstance(a.input, dict) and isinstance(a.input.get('action'), dict)), {})
            kind = template.get('type')
            if kind == 'select_lineup':
                fallback = {'type': kind, 'bring': list(template.get('roster', []))[:4], 'leads': list(template.get('roster', []))[:2]}
                try:
                    result = choose_lineup(obs, copy.deepcopy(template), memory)
                except Exception:
                    _LOG.exception('Lineup evaluation failed; using a validated fallback.')
                    result = fallback
                if not validate_action(result, template):
                    result = fallback
            elif kind == 'doubles_turn':
                choices = enumerate_actions(template)
                if not choices:
                    raise ValueError('No legal joint action can be constructed from the current template.')
                try:
                    result = choose_battle(obs, copy.deepcopy(template), memory)
                except Exception:
                    _LOG.exception('Battle evaluation failed; using a validated fallback.')
                    result = self._fallback(choices)
                if not validate_action(result, template):
                    result = self._fallback(choices)
            else:
                raise ValueError('Unsupported Pokemon action template.')
            if not validate_action(result, template):
                raise ValueError('The current template has no valid supported action.')
        memory['decisions'][key] = copy.deepcopy(result)
        if len(memory['decisions']) > 8:
            memory['decisions'].popitem(last=False)
        destination = os.environ.get('POKEMON_LOG_DIR')
        if destination:
            try:
                folder = Path(destination)
                folder.mkdir(parents=True, exist_ok=True)
                payload = {
                    'time': datetime.now(timezone.utc).isoformat(),
                    'session': sid,
                    'phase': getattr(state, 'phase', ''),
                    'state_version': getattr(state, 'state_version', 0),
                    'observation': obs,
                    'action': getattr(result, 'action_id', result),
                    'search': memory.get('battle', {}).get('last_search'),
                }
                filename = hashlib.sha256(sid.encode()).hexdigest()[:16] + '.jsonl'
                with (folder / filename).open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(payload, ensure_ascii=False, default=str) + '\n')
            except OSError:
                _LOG.warning('Could not write local decision log.')
        return result

    @staticmethod
    def _fallback(choices):
        def score(action):
            value = 0
            for key in ('slot_0', 'slot_1'):
                part = action[key]
                if part['type'] == 'move':
                    value += 2 if part.get('target', 0) >= 0 else -10
                elif part['type'] == 'switch':
                    value += 1
            return value
        return max(choices, key=score)


def create_agent():
    return PokemonAgent()
