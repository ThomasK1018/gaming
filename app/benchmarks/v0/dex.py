import json
import math
import re
from pathlib import Path

_DATA = json.loads(Path(__file__).with_name('dex_data.json').read_text(encoding='utf-8'))


def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())


def species_data(value):
    return dict(_DATA['species'].get(norm(value), {}))


def move_data(value):
    return dict(_DATA['moves'].get(norm(value), {}))


def type_effectiveness(attack_type, target_types):
    result = 1.0
    for typ in target_types or []:
        chart = _DATA['typechart'].get(str(typ).lower(), {})
        code = next((v for k, v in chart.items() if norm(k) == norm(attack_type)), 0)
        result *= {0: 1.0, 1: 2.0, 2: 0.5, 3: 0.0}.get(code, 1.0)
    return result


def stat_values(mon):
    if isinstance(mon, str):
        mon = {'species': mon}
    mon = mon or {}
    base = mon.get('base_stats') or mon.get('baseStats') or species_data(mon.get('species') or mon.get('name')).get('baseStats', {})
    level = int(mon.get('level') or 50)
    evs, ivs = mon.get('evs') or {}, mon.get('ivs') or {}
    nature = _DATA['natures'].get(norm(mon.get('nature')), {})
    actual = mon.get('stats') or {}
    result = {}
    for key in ('hp', 'atk', 'def', 'spa', 'spd', 'spe'):
        v = int(base.get(key) or 80)
        x = math.floor((2 * v + int(ivs.get(key, 31)) + int(evs.get(key, 0)) // 4) * level / 100)
        value = x + level + 10 if key == 'hp' else x + 5
        if key != 'hp':
            value = math.floor(value * (1.1 if nature.get('plus') == key else 0.9 if nature.get('minus') == key else 1.0))
        if key == 'hp' and norm(mon.get('species')) == 'shedinja':
            value = 1
        result[key] = int(actual.get(key) or value)
    if mon.get('max_hp') and float(mon['max_hp']) > 1:
        result['hp'] = int(mon['max_hp'])
    return result
