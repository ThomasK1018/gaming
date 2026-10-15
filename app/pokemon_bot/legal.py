from itertools import product


def _slot_options(slot):
    out = []
    for option in slot.get('options', []):
        if not isinstance(option, dict):
            continue
        kind = option.get('type')
        if kind == 'move' and isinstance(option.get('move_id'), str) and option['move_id']:
            targets = option.get('targets') or []
            if not isinstance(targets, list):
                continue
            if any(type(t) is not int for t in targets):
                continue
            if targets:
                out.extend({'type': 'move', 'move_id': option['move_id'], 'target': t} for t in targets)
            else:
                out.append({'type': 'move', 'move_id': option['move_id']})
        elif kind == 'switch' and isinstance(option.get('species'), str) and option['species']:
            out.append({'type': 'switch', 'species': option['species']})
        elif kind == 'pass':
            out.append({'type': 'pass'})
    return out


def enumerate_actions(template):
    if not isinstance(template, dict) or template.get('type') != 'doubles_turn':
        return []
    slots = template.get('slots')
    if not isinstance(slots, list) or len(slots) != 2 or not all(isinstance(s, dict) for s in slots):
        return []
    mapped = {s.get('slot', i): s for i, s in enumerate(slots)}
    if set(mapped) != {0, 1}:
        return []
    out = []
    for a, b in product(_slot_options(mapped[0]), _slot_options(mapped[1])):
        if a['type'] == b['type'] == 'switch' and a['species'] == b['species']:
            continue
        if a['type'] == b['type'] == 'pass':
            continue
        out.append({'type': 'doubles_turn', 'slot_0': dict(a), 'slot_1': dict(b)})
    return out


def validate_action(action, template):
    if not isinstance(action, dict) or not isinstance(template, dict):
        return False
    if action.get('type') != template.get('type'):
        return False
    if action.get('type') == 'select_lineup':
        bring, leads, roster = action.get('bring'), action.get('leads'), template.get('roster', [])
        if not isinstance(bring, list) or not isinstance(leads, list):
            return False
        if not all(isinstance(x, str) for x in bring + leads):
            return False
        return len(bring) == 4 and len(set(bring)) == 4 and len(leads) == 2 and len(set(leads)) == 2 and set(leads) <= set(bring) <= set(roster)
    if action.get('type') != 'doubles_turn':
        return False
    for key in ('slot_0', 'slot_1'):
        part = action.get(key)
        if not isinstance(part, dict):
            return False
        if 'target' in part and type(part['target']) is not int:
            return False
    return action in enumerate_actions(template)
