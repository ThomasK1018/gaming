from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field, replace

from .dex import move_data, norm, species_data, stat_values, type_effectiveness
from .legal import enumerate_actions


PROTECT = {"protect", "detect", "spikyshield", "banefulbunker", "silktrap", "burningbulwark", "kingsshield", "obstruct"}
HEAL = {"recover", "roost", "slackoff", "softboiled", "milkdrink", "shoreup", "synthesis", "morningsun", "moonlight", "rest"}
STAT_ALIASES = {"attack": "atk", "defense": "def", "specialattack": "spa", "specialdefense": "spd", "speed": "spe", "accuracy": "accuracy", "evasion": "evasion"}
IMMUNITIES = {
    "electric": {"voltabsorb", "lightningrod", "motordrive"},
    "water": {"waterabsorb", "stormdrain", "dryskin"},
    "fire": {"flashfire", "wellbakedbody"},
    "grass": {"sapsipper"},
    "ground": {"levitate", "eartheater"},
}
RESIST_BERRIES = dict(zip(
    ["normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy"],
    ["chilanberry", "occaberry", "passhoberry", "wacanberry", "rindoberry", "yacheberry", "chopleberry", "kebiaberry", "shucaberry", "cobaberry", "payapaberry", "tangaberry", "chartiberry", "kasibberry", "habanberry", "colburberry", "babiriberry", "roseliberry"],
))


def _names(value):
    if isinstance(value, dict):
        return {norm(k) for k, v in value.items() if v is not None and v is not False}
    if isinstance(value, (list, tuple, set)):
        return {norm(x.get("id", x.get("name", ""))) if isinstance(x, dict) else norm(x) for x in value}
    return {norm(value)} if value else set()


def _list(value):
    if isinstance(value, dict):
        return list(value.values())
    return list(value) if isinstance(value, list) else []


def _pair(value):
    if isinstance(value, dict) and "species" in value:
        return [value, None]
    return (_list(value) + [None, None])[:2]


def _stage(n):
    n = max(-6, min(6, n))
    return (2 + n) / 2 if n >= 0 else 2 / (2 - n)


def _num(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _move(value):
    if isinstance(value, str):
        ident, supplied = norm(value), {}
    else:
        supplied = value or {}
        ident = norm(supplied.get("move_id", supplied.get("id", supplied.get("name", supplied.get("move", "")))))
    data = dict(move_data(ident) or {})
    data.update({k: v for k, v in supplied.items() if v is not None and not (k == "type" and v in {"move", "switch", "pass"}) and not (k == "target" and not isinstance(v, str))})
    data["id"] = ident
    data["type"] = norm(data.get("move_type", data.get("type", "normal")))
    data["category"] = norm(data.get("category", "status"))
    data["basePower"] = _num(data.get("base_power", data.get("basePower")), 0)
    data["priority"] = _num(data.get("priority"), 0)
    accuracy = data.get("accuracy", True)
    data["accuracy"] = 1.0 if accuracy is True else min(1.0, _num(accuracy, 100) / (100 if _num(accuracy, 100) > 1 else 1))
    data["target"] = norm(data.get("target", "normal"))
    data["flags"] = data.get("flags") or {}
    return data


@dataclass
class Mon:
    species: str
    side: int
    slot: int
    hp: float
    maxhp: float
    stats: dict
    boosts: dict
    types: set
    ability: str
    item: str
    status: str
    moves: list
    level: float = 50
    first_turn: bool = False
    protect_streak: int = 0
    effects: set = field(default_factory=set)
    weight: float = 100


def _make_mon(raw, side, slot, memory, turn, tracking):
    if not isinstance(raw, dict):
        return None
    name = raw.get("species", raw.get("name", ""))
    ident = norm(name)
    if not ident:
        return None
    public = dict(memory.get("sets", {}).get(ident, {}) or {})
    merged = dict(public)
    merged.update({k: v for k, v in raw.items() if v is not None and v != "" and v != "unknown"})
    merged["species"] = name
    if side == 1 and 0 < _num(merged.get("max_hp")) <= 100:
        merged.pop("max_hp", None)
    base = species_data(name) or {}
    stats = dict(stat_values(merged) or {})
    stats = {STAT_ALIASES.get(norm(k), norm(k)): _num(v, 100) for k, v in stats.items()}
    for stat in ("hp", "atk", "def", "spa", "spd", "spe"):
        stats.setdefault(stat, 150 if stat == "hp" else 100)
    maxhp = _num(raw.get("max_hp"), stats["hp"])
    if side == 1 and maxhp <= 100:
        maxhp = stats["hp"]
    maxhp = max(1, maxhp)
    fraction = raw.get("current_hp_fraction", raw.get("hp_fraction"))
    if fraction is None:
        fraction = _num(raw.get("current_hp"), maxhp) / max(1, _num(raw.get("max_hp"), maxhp))
    hp = max(0, min(1, _num(fraction, 1)))
    if raw.get("fainted"):
        hp = 0
    boosts = {STAT_ALIASES.get(norm(k), norm(k)): int(_num(v)) for k, v in (raw.get("boosts") or {}).items()}
    moves = {}
    for source in (public.get("moves", []), raw.get("moves", [])):
        if isinstance(source, dict):
            source = [{"id": k, **v} if isinstance(v, dict) else k for k, v in source.items()]
        for value in source or []:
            parsed = _move(value)
            if parsed["id"]:
                moves[parsed["id"]] = {**moves.get(parsed["id"], {}), **parsed}
    if side == 1 and len(moves) < 4:
        priors = base.get("threat_moves") or []
        inferred = []
        for value in priors:
            parsed = _move(value)
            if parsed["id"] and parsed["id"] not in moves:
                parsed["inferred"] = True
                inferred.append(parsed)
        if not inferred and not priors:
            category = "physical" if stats["atk"] >= stats["spa"] else "special"
            for typ in sorted(_names(merged.get("types", base.get("types", ["normal"])))):
                parsed = _move({"id": "inferred" + typ + category, "type": typ, "category": category, "base_power": 80, "accuracy": 1, "target": "normal"})
                parsed["inferred"] = True
                inferred.append(parsed)
        selected_priors = inferred[:6]
        protective_prior = next((m for m in inferred[6:] if m["id"] in PROTECT), None)
        if protective_prior:
            selected_priors.append(protective_prior)
        for parsed in selected_priors:
            moves[parsed["id"]] = parsed
    track = tracking.get(f"{side}:{slot}", {})
    first = track.get("species") != ident or track.get("entered", turn) == turn
    return Mon(ident, side, slot, hp, maxhp, stats, boosts,
               _names(merged.get("types", base.get("types", []))),
               norm(merged.get("ability", "")), norm(merged.get("item", "")),
               norm(raw.get("status", "")), list(moves.values()),
               _num(merged.get("level"), 50), first, int(track.get("protect_streak", 0)),
               _names(raw.get("effects", raw.get("volatile_statuses", []))),
               _num(base.get("weightkg", base.get("weight_kg")), 100))


def _grounded(mon):
    return "flying" not in mon.types and mon.ability != "levitate" and mon.item != "airballoon"


def _weather(obs):
    names = _names(obs.get("weather"))
    if names & {"raindance", "rain", "primordialsea", "heavyrain"}:
        return "rain"
    if names & {"sunnyday", "sun", "desolateland", "harshsunshine"}:
        return "sun"
    if names & {"sandstorm", "sand"}:
        return "sand"
    if names & {"snow", "snowscape", "hail"}:
        return "snow"
    return ""


def _stat(mon, key, field_state, ignore=False):
    value = mon.stats.get(key, 100) * (1 if ignore else _stage(mon.boosts.get(key, 0)))
    ability, item, weather = mon.ability, mon.item, field_state["weather"]
    if key == "atk":
        if ability in {"hugepower", "purepower"}:
            value *= 2
        if ability in {"hustle", "gorillatactics"} or ability == "guts" and mon.status:
            value *= 1.5
        if item == "choiceband":
            value *= 1.5
    if key == "spa" and (item == "choicespecs" or ability == "solarpower" and weather == "sun"):
        value *= 1.5
    if key == "def":
        if ability == "furcoat":
            value *= 2
        if weather == "snow" and "ice" in mon.types:
            value *= 1.5
    if key == "spd":
        if item == "assaultvest":
            value *= 1.5
        if weather == "sand" and "rock" in mon.types:
            value *= 1.5
    if key in {"def", "spd"} and item == "eviolite":
        value *= 1.5
    if key == "spe":
        if mon.status in {"par", "paralysis"}:
            value *= 0.5
        if item == "choicescarf":
            value *= 1.5
        if item in {"ironball", "machobrace"}:
            value *= 0.5
        if "tailwind" in field_state["conditions"][mon.side]:
            value *= 2
        if (weather, ability) in {("rain", "swiftswim"), ("sun", "chlorophyll"), ("sand", "sandrush"), ("snow", "slushrush")}:
            value *= 2
    if ability in {"protosynthesis", "quarkdrive"}:
        activated = item == "boosterenergy" or ability == "protosynthesis" and weather == "sun" or ability == "quarkdrive" and "electricterrain" in field_state["fields"]
        activated = activated or any(e.startswith(ability) for e in mon.effects)
        best = max(("atk", "def", "spa", "spd", "spe"), key=lambda k: mon.stats[k] * _stage(mon.boosts.get(k, 0)))
        if activated and best == key:
            value *= 1.5 if key == "spe" else 1.3
    return value


def _priority(mon, move, state=None):
    value = move["priority"]
    if mon.ability == "prankster" and move["category"] == "status":
        value += 1
    if mon.ability == "galewings" and move["type"] == "flying" and mon.hp >= .999:
        value += 1
    if mon.ability == "triage" and (move["id"] in HEAL or move.get("drain") or move.get("heal")):
        value += 3
    if move["id"] == "grassyglide" and state and "grassyterrain" in state["fields"] and _grounded(mon):
        value += 1
    return value


def _usable(mon, move):
    if move.get("current_pp") is not None and _num(move.get("current_pp")) <= 0:
        return False
    if move["id"] == "fakeout" and not mon.first_turn:
        return False
    if move["category"] == "status" and ("taunt" in mon.effects or mon.item == "assaultvest"):
        return False
    locks = [effect[len("choicelock"):] for effect in mon.effects if effect.startswith("choicelock")]
    if locks and move["id"] not in locks:
        return False
    if move["id"] == "bloodmoon" and "lastmovebloodmoon" in mon.effects:
        return False
    return True


def _accuracy(attacker, target, move, state):
    if attacker.ability == "noguard" or target.ability == "noguard":
        return 1.0
    if move["id"] in {"thunder", "hurricane"} and state["weather"] == "rain" or move["id"] == "blizzard" and state["weather"] == "snow":
        return 1.0
    value = move["accuracy"]
    if move["id"] in {"thunder", "hurricane"} and state["weather"] == "sun":
        value = .5
    if attacker.ability == "compoundeyes":
        value *= 1.3
    if attacker.ability == "hustle" and move["category"] == "physical":
        value *= .8
    if attacker.item == "widelens":
        value *= 1.1
    stages = attacker.boosts.get("accuracy", 0) - target.boosts.get("evasion", 0)
    value *= (3 + stages) / 3 if stages >= 0 else 3 / (3 - stages)
    return max(0, min(1, value))


def _blocked(attacker, target, move, state, board):
    if attacker.side != target.side and _priority(attacker, move, state) > 0:
        if "psychicterrain" in state["fields"] and _grounded(target):
            return True
        if any(m and m.hp > 0 and m.side == target.side and m.ability in {"armortail", "queenlymajesty", "dazzling"} for m in board):
            return True
    if attacker.side != target.side and attacker.ability == "prankster" and move["category"] == "status" and "dark" in target.types:
        return True
    bypass = attacker.ability in {"moldbreaker", "teravolt", "turboblaze"}
    if not bypass:
        if target.ability in IMMUNITIES.get(move["type"], set()):
            return True
        if target.ability == "soundproof" and move["flags"].get("sound"):
            return True
        if target.ability == "bulletproof" and move["flags"].get("bullet"):
            return True
        if target.ability == "goodasgold" and move["category"] == "status" and (attacker.side, attacker.slot) != (target.side, target.slot):
            return True
    return False


def _damage(attacker, target, move, state, board, spread=False, helping=False):
    if not attacker or not target or target.hp <= 0 or not _usable(attacker, move) or _blocked(attacker, target, move, state, board):
        return 0.0
    ident, mtype = move["id"], move["type"]
    if move["category"] == "status":
        return 0.0
    if ident in {"weatherball", "terrainpulse"}:
        if ident == "weatherball" and state["weather"]:
            mtype = {"rain": "water", "sun": "fire", "sand": "rock", "snow": "ice"}[state["weather"]]
        if ident == "terrainpulse" and _grounded(attacker):
            for terrain, typ in (("electricterrain", "electric"), ("grassyterrain", "grass"), ("psychicterrain", "psychic"), ("mistyterrain", "fairy")):
                if terrain in state["fields"]:
                    mtype = typ
    if mtype != move["type"] and _blocked(attacker, target, {**move, "type": mtype}, state, board):
        return 0.0
    effectiveness = type_effectiveness(mtype, list(target.types))
    if mtype == "ground" and target.item == "airballoon":
        return 0.0
    if effectiveness == 0 and attacker.ability in {"scrappy", "mindseye"} and mtype in {"normal", "fighting"} and "ghost" in target.types:
        effectiveness = type_effectiveness(mtype, list(target.types - {"ghost"}))
    if effectiveness <= 0:
        return 0.0
    if target.ability == "wonderguard" and effectiveness <= 1 and attacker.ability not in {"moldbreaker", "teravolt", "turboblaze"}:
        return 0.0
    if ident in {"seismictoss", "nightshade"}:
        return attacker.level / target.maxhp * _accuracy(attacker, target, move, state)
    if ident in {"superfang", "naturesmadness", "ruination"}:
        return target.hp * .5 * _accuracy(attacker, target, move, state)
    if ident == "finalgambit":
        return attacker.hp * attacker.maxhp / target.maxhp * _accuracy(attacker, target, move, state)
    power = move["basePower"]
    if ident in {"eruption", "waterspout", "dragonenergy"}:
        power = max(1, 150 * attacker.hp)
    if ident == "electroball":
        ratio = _stat(attacker, "spe", state) / max(1, _stat(target, "spe", state))
        power = 150 if ratio >= 4 else 120 if ratio >= 3 else 80 if ratio >= 2 else 60 if ratio >= 1 else 40
    if ident == "gyroball":
        power = min(150, 25 * _stat(target, "spe", state) / max(1, _stat(attacker, "spe", state)) + 1)
    if ident in {"lowkick", "grassknot"}:
        power = 120 if target.weight >= 200 else 100 if target.weight >= 100 else 80 if target.weight >= 50 else 60 if target.weight >= 25 else 40 if target.weight >= 10 else 20
    if ident in {"heavyslam", "heatcrash"}:
        ratio = attacker.weight / max(.1, target.weight)
        power = 120 if ratio >= 5 else 100 if ratio >= 4 else 80 if ratio >= 3 else 60 if ratio >= 2 else 40
    if ident in {"storedpower", "powertrip"}:
        power = 20 + 20 * sum(max(0, n) for n in attacker.boosts.values())
    if ident == "facade" and attacker.status or ident == "hex" and target.status or ident == "venoshock" and target.status in {"psn", "tox"}:
        power *= 2
    if ident in {"weatherball", "terrainpulse"} and mtype != move["type"]:
        power *= 2
    if ident == "knockoff" and target.item:
        power *= 1.5
    if ident in {"expandingforce", "risingvoltage"} and _grounded(attacker):
        if ident == "expandingforce" and "psychicterrain" in state["fields"]:
            power *= 1.5
        if ident == "risingvoltage" and "electricterrain" in state["fields"] and _grounded(target):
            power *= 2
    if power <= 0:
        return 0.0
    physical = move["category"] == "physical"
    crit = ident in {"surgingstrikes", "wickedblow", "flowertrick", "frostbreath", "stormthrow"} or bool(move.get("willCrit"))
    offense_key = "def" if ident == "bodypress" else "atk" if physical else "spa"
    defense_key = "def" if physical or ident in {"psyshock", "psystrike", "secretsword"} else "spd"
    source = target if ident == "foulplay" else attacker
    offense = _stat(source, offense_key, state, target.ability == "unaware" or crit and source.boosts.get(offense_key, 0) < 0)
    defense = _stat(target, defense_key, state, attacker.ability == "unaware" or crit and target.boosts.get(defense_key, 0) > 0)
    offense_ruin = "tabletsofruin" if offense_key == "atk" else "vesselofruin" if offense_key == "spa" else ""
    defense_ruin = "swordofruin" if defense_key == "def" else "beadsofruin"
    if offense_ruin and source.ability != offense_ruin and any(m and m.hp > 0 and m.ability == offense_ruin for m in board):
        offense *= .75
    if target.ability != defense_ruin and any(m and m.hp > 0 and m.ability == defense_ruin for m in board):
        defense *= .75
    factor = 1.0
    hits = move.get("multihit", 1)
    if isinstance(hits, (list, tuple)):
        hits = hits[-1] if attacker.ability == "skilllink" else 4.5 if attacker.item == "loadeddice" else 3
    if ident == "surgingstrikes":
        hits = 3
    factor *= _num(hits, 1)
    if crit:
        factor *= 1.5
    if mtype in attacker.types:
        factor *= 2 if attacker.ability == "adaptability" else 1.5
    factor *= effectiveness
    if spread:
        factor *= .75
    if helping:
        factor *= 1.5
    if state["weather"] == "rain" and mtype in {"water", "fire"}:
        factor *= 1.5 if mtype == "water" else .5
    if state["weather"] == "sun" and mtype in {"water", "fire"}:
        factor *= 1.5 if mtype == "fire" else .5
    for terrain, typ in (("electricterrain", "electric"), ("grassyterrain", "grass"), ("psychicterrain", "psychic")):
        if terrain in state["fields"] and mtype == typ and _grounded(attacker):
            factor *= 1.3
    if "mistyterrain" in state["fields"] and mtype == "dragon" and _grounded(target):
        factor *= .5
    if "grassyterrain" in state["fields"] and ident in {"earthquake", "bulldoze", "magnitude"} and _grounded(target):
        factor *= .5
    if physical and attacker.status in {"brn", "burn"} and attacker.ability != "guts" and ident != "facade":
        factor *= .5
    if attacker.ability == "technician" and power <= 60:
        factor *= 1.5
    if attacker.ability == "toughclaws" and move["flags"].get("contact"):
        factor *= 1.3
    if attacker.ability == "strongjaw" and move["flags"].get("bite") or attacker.ability == "sharpness" and move["flags"].get("slicing"):
        factor *= 1.5
    if attacker.ability == "ironfist" and move["flags"].get("punch"):
        factor *= 1.2
    if attacker.ability == "sheerforce" and (move.get("secondary") or move.get("secondaries")):
        factor *= 1.3
    if attacker.ability == "tintedlens" and effectiveness < 1:
        factor *= 2
    if attacker.ability == "waterbubble" and mtype == "water":
        factor *= 2
    if attacker.ability == "transistor" and mtype == "electric" or attacker.ability == "dragonsmaw" and mtype == "dragon":
        factor *= 1.3 if attacker.ability == "transistor" else 1.5
    if attacker.item == "lifeorb":
        factor *= 1.3
    if attacker.item == "expertbelt" and effectiveness > 1:
        factor *= 1.2
    if (attacker.item, mtype) in {("mysticwater", "water"), ("charcoal", "fire"), ("magnet", "electric"), ("miracleseed", "grass"), ("blackglasses", "dark"), ("twistedspoon", "psychic"), ("fairyfeather", "fairy"), ("silkscarf", "normal"), ("softsand", "ground"), ("nevermeltice", "ice"), ("metalcoat", "steel"), ("dragonfang", "dragon"), ("spelltag", "ghost"), ("sharpbeak", "flying"), ("blackbelt", "fighting")}:
        factor *= 1.2
    bypass = attacker.ability in {"moldbreaker", "teravolt", "turboblaze"}
    if not bypass:
        if target.ability in {"multiscale", "shadowshield"} and target.hp >= .999:
            factor *= .5
        if target.ability in {"filter", "solidrock", "prismarmor"} and effectiveness > 1:
            factor *= .75
        if target.ability == "thickfat" and mtype in {"fire", "ice"} or target.ability == "heatproof" and mtype == "fire" or target.ability == "waterbubble" and mtype == "fire" or target.ability == "purifyingsalt" and mtype == "ghost":
            factor *= .5
        if target.ability == "icescales" and not physical:
            factor *= .5
        if target.ability == "fluffy":
            factor *= (.5 if move["flags"].get("contact") else 1) * (2 if mtype == "fire" else 1)
    if any(m and m.hp > 0 and m.side == target.side and m.slot != target.slot and m.ability == "friendguard" for m in board):
        factor *= .75
    screen = "reflect" if physical else "lightscreen"
    if not crit and attacker.ability != "infiltrator" and (screen in state["conditions"][target.side] or "auroraveil" in state["conditions"][target.side]):
        factor *= 2 / 3
    if target.item == RESIST_BERRIES.get(mtype) and (effectiveness > 1 or mtype == "normal"):
        factor *= .5
    damage = ((2 * attacker.level / 5 + 2) * power * offense / max(1, defense) / 50 + 2) * factor * .925 / target.maxhp
    if target.hp >= .999 and (target.item == "focussash" or target.ability == "sturdy" and not bypass) and _num(hits, 1) == 1:
        damage = min(damage, 1 - 1 / target.maxhp)
    return damage * _accuracy(attacker, target, move, state)


def _action_move(mon, action):
    ident = norm(action.get("move_id", ""))
    return next((m for m in mon.moves if m["id"] == ident), None) or _move(ident)


def _targets(index, action, move, board, state):
    side, slot = divmod(index, 2)
    target = int(action.get("target", 0))
    kind = move["target"]
    if move["id"] == "expandingforce" and "psychicterrain" in state["fields"] and _grounded(board[index]):
        kind = "alladjacentfoes"
    if kind in {"alladjacentfoes", "foeside"}:
        return [2 * (1 - side) + j for j in range(2) if board[2 * (1 - side) + j] and board[2 * (1 - side) + j].hp > 0]
    if kind == "alladjacent":
        return [i for i, m in enumerate(board) if i != index and m and m.hp > 0]
    if kind == "all":
        return [i for i, m in enumerate(board) if m and m.hp > 0]
    if kind in {"self", "allyside", "allyteam"}:
        return [index]
    if kind == "allies":
        return [2 * side + j for j in range(2) if board[2 * side + j] and board[2 * side + j].hp > 0]
    if target > 0:
        result = 2 * (1 - side) + target - 1
    elif target < 0:
        result = 2 * side - target - 1
    elif kind == "adjacentally":
        result = 2 * side + (1 - slot)
    else:
        live = [2 * (1 - side) + j for j in range(2) if board[2 * (1 - side) + j] and board[2 * (1 - side) + j].hp > 0]
        return live[:1]
    if result < 0 or result >= 4:
        return []
    if not board[result] or board[result].hp <= 0:
        if target > 0:
            result = 2 * (1 - side) + (1 - (target - 1))
        else:
            return []
    return [result] if board[result] and board[result].hp > 0 else []


def _status_possible(attacker, target, move, state, board):
    ident = move["id"]
    if target.status or _blocked(attacker, target, move, state, board):
        return False
    if "mistyterrain" in state["fields"] and _grounded(target):
        return False
    if ident in {"spore", "sleeppowder", "ragepowder", "stunspore", "poisonpowder"} or move["flags"].get("powder"):
        if "grass" in target.types or target.item == "safetygoggles" or target.ability == "overcoat":
            return False
    status = norm(move.get("status", "slp" if ident in {"spore", "sleeppowder", "hypnosis", "sing", "lovelykiss", "darkvoid"} else "par" if ident in {"thunderwave", "stunspore", "glare"} else "brn" if ident == "willowisp" else "tox" if ident == "toxic" else ""))
    if status == "slp":
        if target.ability in {"insomnia", "vitalspirit", "comatose", "purifyingsalt"} or "electricterrain" in state["fields"] and _grounded(target):
            return False
        if any(m and m.side == target.side and m.hp > 0 and m.ability == "sweetveil" for m in board):
            return False
    if status == "par" and ("electric" in target.types or target.ability in {"limber", "purifyingsalt"} or ident == "thunderwave" and "ground" in target.types):
        return False
    if status == "brn" and ("fire" in target.types or target.ability in {"waterveil", "waterbubble", "thermalexchange", "purifyingsalt"}):
        return False
    if status in {"psn", "tox"} and (target.types & {"poison", "steel"} and attacker.ability != "corrosion" or target.ability in {"immunity", "purifyingsalt"}):
        return False
    return status


def _entry(mon, board, state):
    ability = mon.ability
    if ability == "intimidate":
        for target in board:
            if target and target.side != mon.side and target.hp > 0:
                if target.ability in {"clearbody", "whitesmoke", "hypercutter", "fullmetalbody", "innerfocus", "oblivious", "owntempo", "scrappy"} or target.item == "clearamulet":
                    continue
                if target.ability == "mirrorarmor":
                    mon.boosts["atk"] = max(-6, mon.boosts.get("atk", 0) - 1)
                else:
                    target.boosts["atk"] = max(-6, target.boosts.get("atk", 0) - 1)
                    if target.ability == "defiant":
                        target.boosts["atk"] += 2
                    if target.ability == "competitive":
                        target.boosts["spa"] = min(6, target.boosts.get("spa", 0) + 2)
    weather = {"drizzle": "rain", "drought": "sun", "sandstream": "sand", "snowwarning": "snow"}.get(ability)
    if weather:
        state["weather"] = weather
    terrain = {"electricsurge": "electricterrain", "grassysurge": "grassyterrain", "psychicsurge": "psychicterrain", "mistysurge": "mistyterrain"}.get(ability)
    if terrain:
        state["fields"] -= {"electricterrain", "grassyterrain", "psychicterrain", "mistyterrain"}
        state["fields"].add(terrain)


def _boost(target, boosts, hostile=False):
    value = 0.0
    for key, amount in boosts.items():
        key = STAT_ALIASES.get(norm(key), norm(key))
        if hostile and amount < 0 and (target.item == "clearamulet" or target.ability in {"clearbody", "whitesmoke", "fullmetalbody"}):
            continue
        old = target.boosts.get(key, 0)
        new = max(-6, min(6, old + int(amount) * (2 if target.ability == "simple" else -1 if target.ability == "contrary" else 1)))
        target.boosts[key] = new
        if key in {"atk", "spa"}:
            offense_used = any(m["category"] == ("physical" if key == "atk" else "special") for m in target.moves)
            weight = .12 if offense_used else .015
        else:
            weight = .12 if key == "spe" else .055
        value += weight * (new - old)
    return value


def _copy_mon(mon):
    return replace(mon, boosts=dict(mon.boosts), effects=set(mon.effects), moves=[dict(move) for move in mon.moves]) if mon else None


def _simulate(board0, reserves0, field0, actions0, actions1, tie=0, details=False):
    board = [_copy_mon(m) for m in board0]
    reserves = [dict(side) for side in reserves0]
    state = {"weather": field0["weather"], "fields": set(field0["fields"]), "conditions": [set(x) for x in field0["conditions"]]}
    actions = [actions0.get(f"slot_{i}", {"type": "pass"}) for i in range(2)] + [actions1.get(f"slot_{i}", {"type": "pass"}) for i in range(2)]
    advances_turn = not field0.get("forced_switch", not any(action["type"] == "move" for action in actions))
    utility, changes = [0.0, 0.0], [0.0] * 4
    original_hp = [m.hp if m else 0 for m in board]
    protection, redirect, help_boost, flinch, substitute = {}, {}, set(), set(), {}
    pending = set(range(4))
    executed_moves = {}
    switch_order = sorted(range(4), key=lambda k: (_stat(board[k], "spe", state) if board[k] else 0, k if tie else -k), reverse=True)
    for i in switch_order:
        action = actions[i]
        if action["type"] != "switch":
            continue
        side, slot = divmod(i, 2)
        incoming = reserves[side].get(norm(action.get("species", "")))
        if not incoming:
            pending.discard(i)
            continue
        outgoing = board[i]
        if outgoing and outgoing.hp > 0:
            utility[side] -= .055
            outgoing = replace(outgoing, boosts={}, effects=set())
            if outgoing.ability == "regenerator":
                utility[side] += min(1 - outgoing.hp, 1 / 3) * .7
                outgoing.hp = min(1, outgoing.hp + 1 / 3)
            reserves[side][outgoing.species] = outgoing
        board[i] = replace(incoming, slot=slot, side=side, boosts={}, effects=set(), first_turn=True, protect_streak=0)
        reserves[side].pop(incoming.species, None)
        original_hp[i] = board[i].hp
        _entry(board[i], board, state)
        hazards = state["conditions"][side]
        if board[i].item != "heavydutyboots" and board[i].ability != "magicguard":
            if "stealthrock" in hazards:
                board[i].hp = max(0, board[i].hp - .125 * type_effectiveness("rock", list(board[i].types)))
            if "spikes" in hazards and _grounded(board[i]):
                board[i].hp = max(0, board[i].hp - .125)
        pending.discard(i)
    def order(i):
        mon, action = board[i], actions[i]
        if not mon or mon.hp <= 0 or action["type"] != "move":
            return (-100, 0, i)
        move = _action_move(mon, action)
        speed = _stat(mon, "spe", state)
        return (_priority(mon, move, state), -speed if "trickroom" in state["fields"] else speed, (i if tie else -i))
    while pending:
        i = max(pending, key=order)
        pending.remove(i)
        mon, action = board[i], actions[i]
        if not mon or mon.hp <= 0 or action["type"] != "move" or i in flinch:
            continue
        move = _action_move(mon, action)
        if not _usable(mon, move):
            utility[mon.side] -= .09
            continue
        ident = move["id"]
        executed_moves[i] = ident
        if mon.item in {"choiceband", "choicespecs", "choicescarf"}:
            mon.effects.add("choicelock" + ident)
        reliability = .35 if mon.status in {"slp", "sleep", "frz", "freeze"} else .75 if mon.status in {"par", "paralysis"} else 1.0
        if ident in PROTECT:
            protection[i] = reliability / (3 ** min(4, mon.protect_streak))
            utility[mon.side] -= .035 + .045 * mon.protect_streak
            continue
        if ident in {"wideguard", "quickguard"}:
            state["conditions"][mon.side].add(ident)
            utility[mon.side] -= .025
            continue
        if ident in {"followme", "ragepowder"}:
            redirect[mon.side] = (i, ident)
            utility[mon.side] -= .025
            continue
        if ident == "helpinghand":
            targets = _targets(i, action, move, board, state)
            for target in targets:
                if target != i and not _blocked(mon, board[target], move, state, board):
                    help_boost.add(target)
            continue
        if ident in {"tailwind", "reflect", "lightscreen", "auroraveil", "safeguard"}:
            if ident not in state["conditions"][mon.side] and (ident != "auroraveil" or state["weather"] == "snow"):
                state["conditions"][mon.side].add(ident)
                alive = sum(bool(m and m.hp > 0) for m in board if m is None or m.side == mon.side)
                changes[i] += (.10 if ident == "tailwind" else .12 if ident != "safeguard" else .08) * min(1, alive / 2) * reliability
            continue
        if ident == "trickroom":
            ours = [_stat(m, "spe", state) for m in board if m and m.hp > 0 and m.side == mon.side]
            theirs = [_stat(m, "spe", state) for m in board if m and m.hp > 0 and m.side != mon.side]
            advantage = sum(1 if a < b else -1 if a > b else 0 for a in ours for b in theirs) / max(1, len(ours) * len(theirs))
            active = "trickroom" in state["fields"]
            changes[i] += (.15 * advantage * (-1 if active else 1) - .015) * reliability
            if active:
                state["fields"].remove("trickroom")
            else:
                state["fields"].add("trickroom")
            continue
        if ident in HEAL:
            amount = 1 if ident == "rest" else .5
            if ident in {"synthesis", "morningsun", "moonlight"}:
                amount = 2 / 3 if state["weather"] == "sun" else .25 if state["weather"] else .5
            mon.hp = min(1, mon.hp + amount * reliability)
            if ident == "rest":
                mon.status = "slp"
                changes[i] -= .25
            continue
        if ident == "substitute":
            if mon.hp > .25:
                mon.hp -= .25
                substitute[i] = .25
                changes[i] += .1
            continue
        targets = _targets(i, action, move, board, state)
        spread = len(targets) > 1 and move["category"] != "status"
        spread_move = move["target"] in {"alladjacent", "alladjacentfoes"} or ident == "expandingforce" and "psychicterrain" in state["fields"] and _grounded(mon)
        landed = False
        if len(targets) == 1 and board[targets[0]].side != mon.side and move["target"] in {"normal", "any", "adjacentfoe"}:
            redirected = redirect.get(1 - mon.side)
            if redirected and mon.ability not in {"stalwart", "propellertail"} and ident not in {"snipeshot"}:
                rindex, rmove = redirected
                if board[rindex] and board[rindex].hp > 0 and not (rmove == "ragepowder" and ("grass" in mon.types or mon.ability == "overcoat" or mon.item == "safetygoggles")):
                    targets = [rindex]
            if move["type"] in {"electric", "water"} and mon.ability not in {"stalwart", "propellertail", "moldbreaker", "teravolt", "turboblaze"}:
                attract = "lightningrod" if move["type"] == "electric" else "stormdrain"
                rods = [j for j, target in enumerate(board) if target and target.hp > 0 and j != i and target.ability == attract]
                if rods:
                    targets = [max(rods, key=lambda j: _stat(board[j], "spe", state))]
        for j in targets:
            target = board[j]
            if not target or target.hp <= 0:
                continue
            hostile = target.side != mon.side
            bypass_protect = ident in {"feint", "hyperspacefury", "hyperspacehole", "phantomforce", "shadowforce"} or mon.ability == "unseenfist" and move["flags"].get("contact")
            protect_chance = protection.get(j, 0) if i != j and not bypass_protect else 0
            if spread_move and "wideguard" in state["conditions"][target.side] or hostile and _priority(mon, move, state) > 0 and "quickguard" in state["conditions"][target.side]:
                protect_chance = 1
            if ident == "feint":
                protection.pop(j, None)
            hit = reliability * (1 - protect_chance) * _accuracy(mon, target, move, state)
            if hit <= 0 or _blocked(mon, target, move, state, board):
                continue
            if ident in {"suckerpunch", "thunderclap"} and (j not in pending or actions[j].get("type") != "move" or _action_move(target, actions[j])["category"] == "status"):
                continue
            if ident in {"healpulse", "floralhealing", "pollenpuff"} and not hostile or ident == "lifedew":
                target.hp = min(1, target.hp + (.25 if ident == "lifedew" else .5) * hit)
                continue
            if move["category"] == "status":
                if j in substitute and hostile and not move["flags"].get("sound") and mon.ability != "infiltrator":
                    continue
                status = _status_possible(mon, target, move, state, board)
                if status:
                    target.status = status
                    value = .43 if status == "slp" else .23 if status == "par" else .23 if status == "brn" and target.stats["atk"] >= target.stats["spa"] else .11
                    changes[j] -= value * hit
                    if status == "slp" and j in pending and hit >= .8:
                        flinch.add(j)
                if ident == "taunt" and target.ability not in {"oblivious", "aromaveil"}:
                    target.effects.add("taunt")
                    changes[j] -= .12 * sum(m["category"] == "status" for m in target.moves) * hit
                if ident == "partingshot":
                    changes[j] += _boost(target, {"atk": -1, "spa": -1}, True) * hit
                    utility[mon.side] += .04
                if move.get("boosts"):
                    changes[j] += _boost(target, move["boosts"], hostile) * hit
                continue
            damage = _damage(mon, target, move, state, board, spread, i in help_boost) * reliability * (1 - protect_chance)
            if damage <= 0:
                continue
            if j in substitute and not move["flags"].get("sound") and mon.ability != "infiltrator":
                substitute[j] -= damage
                if substitute[j] <= 0:
                    substitute.pop(j, None)
                continue
            dealt = min(target.hp, damage)
            landed = True
            target.hp = max(0, target.hp - damage)
            if target.hp > 0 and target.ability == "stamina":
                changes[j] += _boost(target, {"def": min(6, int(_num(move.get("multihit"), 3 if ident == "surgingstrikes" else 1)))})
            if target.item == "sitrusberry" and 0 < target.hp <= .5:
                target.hp = min(1, target.hp + .25)
                target.item = ""
            if ident == "fakeout" and target.ability not in {"innerfocus", "shielddust"} and target.item != "covertcloak" and j in pending:
                flinch.add(j)
            if ident == "knockoff":
                if target.item:
                    changes[j] -= .05
                target.item = ""
            if move.get("drain"):
                drain = move["drain"]
                if isinstance(drain, (list, tuple)) and len(drain) == 2:
                    mon.hp = min(1, mon.hp + dealt * target.maxhp / mon.maxhp * drain[0] / drain[1])
            if move.get("recoil"):
                recoil = move["recoil"]
                if isinstance(recoil, (list, tuple)) and len(recoil) == 2 and mon.ability not in {"rockhead", "magicguard"}:
                    mon.hp = max(0, mon.hp - dealt * target.maxhp / mon.maxhp * recoil[0] / recoil[1])
            secondary = move.get("secondary") or {}
            secondaries = move.get("secondaries") or ([secondary] if secondary else [])
            if ident in {"icywind", "electroweb", "bulldoze", "mudshot", "rocktomb"} and not secondaries:
                secondaries = [{"chance": 100, "boosts": {"spe": -1}}]
            if ident == "snarl" and not secondaries:
                secondaries = [{"chance": 100, "boosts": {"spa": -1}}]
            if target.hp > 0 and target.ability != "shielddust" and target.item != "covertcloak" and mon.ability != "sheerforce":
                for effect in secondaries:
                    chance = _num(effect.get("chance"), 100) / 100
                    if effect.get("boosts"):
                        delta = _boost(target, effect["boosts"], hostile) if chance >= .8 else 0
                        changes[j] += delta * hit * chance
                    if effect.get("status") and not target.status:
                        changes[j] -= .12 * chance * hit
                    if effect.get("volatileStatus") == "flinch" and j in pending and target.ability != "innerfocus":
                        utility[mon.side] += .08 * chance * hit
        if move.get("self", {}).get("boosts") and (landed or move["category"] == "status"):
            changes[i] += _boost(mon, move["self"]["boosts"]) * reliability
        if ident in {"uturn", "voltswitch", "flipturn", "chillyreception", "teleport"}:
            utility[mon.side] += .045
        if ident in {"explosion", "selfdestruct", "finalgambit", "mistyexplosion"}:
            mon.hp = 0
        if mon.item == "lifeorb" and landed and move["category"] != "status" and mon.ability not in {"magicguard", "sheerforce"}:
            mon.hp = max(0, mon.hp - .1)
    for i, mon in enumerate(board):
        if not mon:
            continue
        if i in executed_moves:
            used = next((move for move in mon.moves if move["id"] == executed_moves[i]), None)
            if used is not None and used.get("current_pp") is not None:
                used["current_pp"] = max(0, _num(used["current_pp"]) - 1)
            mon.effects = {effect for effect in mon.effects if not effect.startswith("lastmove")}
            mon.effects.add("lastmove" + executed_moves[i])
        if mon.hp > 0:
            if advances_turn and (mon.item == "leftovers" or mon.item == "blacksludge" and "poison" in mon.types):
                mon.hp = min(1, mon.hp + 1 / 16)
            if advances_turn and "grassyterrain" in state["fields"] and _grounded(mon):
                mon.hp = min(1, mon.hp + 1 / 16)
            if advances_turn and mon.status in {"brn", "psn", "tox"} and mon.ability not in {"magicguard", "poisonheal"}:
                mon.hp = max(0, mon.hp - (1 / 16 if mon.status == "brn" else 1 / 8))
            utility[mon.side] += changes[i] * (.5 + .5 * mon.hp)
            if i in substitute:
                utility[mon.side] += min(.25, substitute[i]) * .8
        utility[mon.side] += (mon.hp - original_hp[i]) * .92
        if mon.hp <= 0 and original_hp[i] > 0:
            utility[mon.side] -= .77
        if advances_turn:
            mon.first_turn = actions[i]["type"] == "switch"
            mon.protect_streak = mon.protect_streak + 1 if norm(actions[i].get("move_id", "")) in PROTECT else 0
    for side in range(2):
        guarded = [i for i in range(side*2, side*2+2) if board[i] and board[i].hp > 0 and norm(actions[i].get("move_id", "")) in PROTECT]
        if len(guarded) == 2:
            foes = [m for m in board[(1-side)*2:(1-side)*2+2] if m and m.hp > 0]
            pressure = sum(max((_damage(board[i], foe, move, state, board) for move in board[i].moves if move["category"] != "status" for foe in foes), default=0) for i in guarded)
            utility[side] -= min(.35, .3 * pressure)
    value = utility[0] - utility[1]
    return (value, board, state, reserves) if details else value


def _control_signature(joint):
    controls = {"trickroom", "tailwind", "calmmind", "nastyplot", "swordsdance", "dragondance", "quiverdance", "irondefense", "bulkup"}
    result = []
    for slot in range(2):
        action = joint.get(f"slot_{slot}", {})
        ident = norm(action.get("move_id", ""))
        if ident in controls:
            other = joint.get(f"slot_{1-slot}", {})
            partner = "protect" if norm(other.get("move_id", "")) in PROTECT else other.get("type", "pass")
            result.append((slot, ident, partner))
    return tuple(result)


def _next_actions(board, state, side):
    candidates = []
    for slot in range(2):
        index, mon = side * 2 + slot, board[side * 2 + slot]
        options = []
        if mon and mon.hp > 0:
            for move in mon.moves:
                ident = move["id"]
                if not _usable(mon, move) or move.get("disabled") or _num(move.get("current_pp", 1)) <= 0:
                    continue
                if ident in PROTECT | {"wideguard", "quickguard", "substitute", "tailwind", "trickroom"}:
                    continue
                if move["category"] == "status" and move.get("boosts") and move["target"] == "self":
                    continue
                kind = move["target"]
                if kind in {"self", "allyside", "allyteam", "allies", "all", "alladjacent", "alladjacentfoes", "foeside"}:
                    targets = [0]
                elif kind == "adjacentally":
                    targets = [-2 if slot == 0 else -1]
                elif kind == "adjacentallyorself":
                    targets = [-1, -2]
                else:
                    targets = [1 + j for j in range(2) if board[(1-side)*2+j] and board[(1-side)*2+j].hp > 0]
                    if ident in {"pollenpuff", "healpulse", "floralhealing"}:
                        targets.append(-2 if slot == 0 else -1)
                for target in targets:
                    options.append({"type": "move", "move_id": ident, "target": target})
        if not options:
            options = [{"type": "pass"}]
        def score(action):
            joint = {f"slot_{slot}": action, f"slot_{1-slot}": {"type": "pass"}}
            return _quick(board, [{}, {}], state, joint, side)
        options.sort(key=score, reverse=True)
        candidates.append(options[:3])
    joints = [{"slot_0": first, "slot_1": second} for first, second in itertools.product(*candidates)]
    joints.sort(key=lambda a: _quick(board, [{}, {}], state, a, side), reverse=True)
    return joints[:2]


def _continuation(board0, reserves0, state0):
    board = [_copy_mon(mon) for mon in board0]
    reserves = [dict(side) for side in reserves0]
    state = {"weather": state0["weather"], "fields": set(state0["fields"]), "conditions": [set(x) - {"wideguard", "quickguard"} for x in state0["conditions"]]}
    replacements = []
    for side in range(2):
        active_species = {mon.species for mon in board[side*2:side*2+2] if mon and mon.hp > 0}
        candidates = {key: mon for key, mon in reserves[side].items() if mon.hp > 0 and key not in active_species}
        for slot in range(2):
            i = side * 2 + slot
            if board[i] and board[i].hp > 0 or not candidates:
                continue
            foes = [mon for mon in board[(1-side)*2:(1-side)*2+2] if mon and mon.hp > 0]
            def entry_value(mon):
                attacks = [_damage(mon, foe, move, state, board) for foe in foes for move in mon.moves if move["category"] != "status"]
                threats = [_damage(foe, mon, move, state, board) for foe in foes for move in foe.moves if move["category"] != "status"]
                return .35 * mon.hp + max(attacks, default=0) - .6 * max(threats, default=0)
            key = max(candidates, key=lambda key: entry_value(candidates[key]))
            incoming = candidates.pop(key)
            board[i] = replace(incoming, side=side, slot=slot, boosts={}, effects=set(), first_turn=True, protect_streak=0)
            reserves[side].pop(key, None)
            replacements.append(i)
    for index in sorted(replacements, key=lambda i: _stat(board[i], "spe", state), reverse=True):
        _entry(board[index], board, state)
    choices = [_next_actions(board, state, side) for side in range(2)]
    tied = any(a and b and a.hp > 0 and b.hp > 0 and abs(_stat(a, "spe", state) - _stat(b, "spe", state)) < .01 for a in board[:2] for b in board[2:])
    best = -float("inf")
    for own in choices[0]:
        values = []
        for opponent in choices[1]:
            value = _simulate(board, reserves, state, own, opponent)
            if tied:
                value = .5 * (value + _simulate(board, reserves, state, own, opponent, tie=1))
            values.append(value)
        value = .65 * min(values) + .35 * sum(values) / len(values)
        best = max(best, value)
    return best


def _opponent_options(mon, board, reserves, state):
    if not mon or mon.hp <= 0:
        return [{"type": "pass"}]
    options = []
    for move in mon.moves:
        if not _usable(mon, move) or move.get("disabled") or _num(move.get("current_pp", 1)) <= 0:
            continue
        kind = move["target"]
        if kind in {"self", "allyside", "allyteam", "allies", "all", "alladjacent", "alladjacentfoes", "foeside"}:
            targets = [0]
        elif kind == "adjacentally":
            targets = [-2 if mon.slot == 0 else -1]
        elif kind == "adjacentallyorself":
            targets = [-1, -2]
        else:
            targets = [1 + j for j in range(2) if board[j] and board[j].hp > 0]
            if move["id"] in {"pollenpuff", "healpulse", "floralhealing"}:
                targets.append(-2 if mon.slot == 0 else -1)
        for target in targets:
            options.append({"type": "move", "move_id": move["id"], "target": target})
    if not options:
        options = [{"type": "move", "move_id": "struggle", "target": 1 if board[0] and board[0].hp > 0 else 2}]
    for species, reserve in reserves.items():
        if reserve.hp > 0 and species not in {m.species for m in board[2:] if m}:
            options.append({"type": "switch", "species": species})
    return options


def _quick(board, reserves, state, joint, side):
    total, hit_targets = 0.0, {}
    for slot in range(2):
        i, action = side * 2 + slot, joint.get(f"slot_{slot}", {"type": "pass"})
        mon = board[i]
        if action["type"] == "switch":
            incoming = reserves[side].get(norm(action.get("species", "")))
            if incoming:
                threats = [_damage(foe, incoming, move, state, board) for foe in board[(1-side)*2:(1-side)*2+2] if foe for move in foe.moves if move["category"] != "status"]
                offense = [_damage(incoming, foe, move, state, board) for foe in board[(1-side)*2:(1-side)*2+2] if foe for move in incoming.moves if move["category"] != "status"]
                total += max(offense, default=0) * .15 - max(threats, default=0) * .25 + (0 if not mon or mon.hp <= 0 else -.08)
            continue
        if not mon or mon.hp <= 0 or action["type"] != "move":
            continue
        move = _action_move(mon, action)
        if not _usable(mon, move):
            total -= 2
            continue
        ident = move["id"]
        if ident in PROTECT:
            total += .02 - .1 * mon.protect_streak
        elif ident in {"tailwind", "trickroom", "followme", "ragepowder", "helpinghand", "wideguard"}:
            total += .2
        targets = _targets(i, action, move, board, state)
        for target_index in targets:
            target = board[target_index]
            hostile = target.side != side
            if move["category"] == "status":
                status = _status_possible(mon, target, move, state, board)
                if status:
                    total += .5 * move["accuracy"] * (1 if hostile else -1)
                if ident in HEAL:
                    total += min(.5, 1 - mon.hp) * .7
                continue
            damage = _damage(mon, target, move, state, board, len(targets) > 1)
            if hostile:
                hit_targets[target_index] = hit_targets.get(target_index, 0) + damage
                total += min(target.hp, damage) * .9
                if ident == "fakeout" and damage > 0:
                    total += .3
            else:
                total -= min(target.hp, damage) * 1.3
    for target_index, damage in hit_targets.items():
        hp = board[target_index].hp
        if damage >= hp:
            total += .72
        else:
            total += damage / max(.05, hp) * .05
    return total


def choose_battle(observation: dict, template: dict, memory: dict) -> dict:
    started = time.monotonic()
    clock_left = _num((observation.get("clock") or {}).get("decision_seconds_left"), 50)
    deadline = started + min(1.8, max(.15, clock_left - .4))
    legal = enumerate_actions(template)
    if not legal:
        raise ValueError("No complete legal doubles action is available")
    tracking = memory.setdefault("battle", {})
    turn = int(_num(observation.get("turn"), 1))
    previous = tracking.get("positions", {})
    pending = tracking.get("pending", {})
    if turn > pending.get("turn", turn) and tracking.get("processed_pending_turn") != pending.get("turn"):
        for slot in range(2):
            key = f"0:{slot}"
            record = previous.get(key, {})
            action = pending.get("action", {}).get(f"slot_{slot}", {})
            if norm(action.get("move_id", "")) in PROTECT:
                record["protect_streak"] = record.get("protect_streak", 0) + 1
            else:
                record["protect_streak"] = 0
        tracking["processed_pending_turn"] = pending.get("turn")
    board = []
    for side, key in enumerate(("active_pokemon", "opponent_active_pokemon")):
        for slot, raw in enumerate(_pair(observation.get(key))):
            if side == 0 and not raw:
                matching = next((s for s in template.get("slots", []) if s.get("slot") == slot), {})
                raw = matching.get("active", matching.get("active_pokemon"))
                if isinstance(raw, str):
                    raw = {"species": raw}
            board.append(_make_mon(raw, side, slot, memory, turn, previous))
    for i, mon in enumerate(board):
        if mon:
            key = f"{mon.side}:{mon.slot}"
            old = previous.get(key, {})
            same = old.get("species") == mon.species
            previous[key] = {"species": mon.species, "entered": old.get("entered", turn) if same else turn, "protect_streak": old.get("protect_streak", 0) if same else 0}
    tracking["positions"] = previous
    available = observation.get("available_moves", [[], []])
    for slot in range(2):
        if board[slot]:
            moves = available[slot] if isinstance(available, list) and len(available) > slot and isinstance(available[slot], list) else []
            known = {m["id"]: m for m in board[slot].moves}
            for m in moves:
                parsed = _move(m)
                known[parsed["id"]] = parsed
            for slot_template in template.get("slots", []):
                if slot_template.get("slot") == slot:
                    for option in slot_template.get("options", []):
                        if option.get("type") == "move":
                            parsed = _move(option)
                            if parsed["id"] not in known:
                                known[parsed["id"]] = parsed
            board[slot].moves = list(known.values())
    reserves = [{}, {}]
    for side, key in enumerate(("team", "opponent_team")):
        rows = _list(observation.get(key))
        if side == 0:
            switches = observation.get("available_switches", [])
            for row in _list(switches):
                rows.extend(row if isinstance(row, list) else [row])
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            if side == 1 and raw.get("revealed") is False:
                continue
            mon = _make_mon(raw, side, -1, memory, turn, {})
            if mon and mon.hp > 0 and mon.species not in {x.species for x in board[side*2:side*2+2] if x}:
                reserves[side][mon.species] = mon
    for joint in legal:
        for slot in range(2):
            action = joint.get(f"slot_{slot}", {})
            if action.get("type") == "switch":
                ident = norm(action.get("species", ""))
                if ident and ident not in reserves[0]:
                    reserves[0][ident] = _make_mon({"species": action["species"]}, 0, slot, memory, turn, {})
    state = {"weather": _weather(observation), "fields": _names(observation.get("fields")), "conditions": [_names(observation.get("side_conditions")), _names(observation.get("opponent_side_conditions"))]}
    if any(m and m.hp > 0 and m.ability in {"cloudnine", "airlock"} for m in board):
        state["weather"] = ""
    forced = observation.get("force_switch", [False, False])
    if isinstance(forced, bool):
        forced = [forced]
    state["forced_switch"] = any(forced)
    if any(forced):
        responses = [{"slot_0": {"type": "pass"}, "slot_1": {"type": "pass"}}]
    else:
        opponent_options = [_opponent_options(board[i+2], board, reserves[1], state) for i in range(2)]
        responses = []
        for a, b in itertools.product(*opponent_options):
            if a["type"] == b["type"] == "switch" and norm(a["species"]) == norm(b["species"]):
                continue
            responses.append({"slot_0": a, "slot_1": b})
        responses.sort(key=lambda a: _quick(board, reserves, state, a, 1), reverse=True)
        top = responses[:18]
        for candidate in responses:
            if any(norm(candidate[f"slot_{i}"].get("move_id", "")) in PROTECT | {"wideguard", "followme", "ragepowder", "trickroom", "tailwind"} for i in range(2)) and candidate not in top:
                top.append(candidate)
                if len(top) >= 26:
                    break
        responses = top
    ranked = sorted(legal, key=lambda a: _quick(board, reserves, state, a, 0), reverse=True)
    controls = {}
    for action in ranked:
        signature = _control_signature(action)
        if signature and signature not in controls:
            controls[signature] = action
    if len(ranked) > 64:
        coarse = [(sum(_simulate(board, reserves, state, action, reply) for reply in responses[:3]) / min(3, len(responses)), action) for action in ranked[:140]]
        coarse.sort(key=lambda pair: pair[0], reverse=True)
        ranked = [action for _, action in coarse[:64]]
    for action in controls.values():
        if action not in ranked:
            ranked.append(action)
    opponent_values = [_quick(board, reserves, state, response, 1) for response in responses]
    max_response = max(opponent_values, default=0)
    weights = [math.exp(max(-12, 2 * (value - max_response))) for value in opponent_values]
    weight_sum = max(1e-9, sum(weights))
    own_alive = sum(m.hp > 0 for m in board[:2] if m) + len(reserves[0])
    opp_alive = sum(m.hp > 0 for m in board[2:] if m) + len(reserves[1])
    risk = .40 if own_alive >= opp_alive else .28
    speed_tie = any(a and b and abs(_stat(a, "spe", state) - _stat(b, "spe", state)) < .01 for a in board[:2] for b in board[2:])
    best, best_score = ranked[0], -float("inf")
    scored = []
    for action in ranked:
        values = [_simulate(board, reserves, state, action, response) for response in responses]
        if speed_tie:
            values = [(value + _simulate(board, reserves, state, action, response, tie=1)) / 2 for value, response in zip(values, responses)]
        average = sum(value * weight for value, weight in zip(values, weights)) / weight_sum
        value = (1 - risk) * average + risk * min(values)
        value += .006 * _quick(board, reserves, state, action, 0)
        scored.append((value, action, values))
        if value > best_score:
            best, best_score = action, value
    scored.sort(key=lambda row: row[0], reverse=True)
    candidates = scored[:12]
    grouped = {}
    for row in scored:
        signature = _control_signature(row[1])
        if signature and signature not in grouped:
            grouped[signature] = row
    for row in list(grouped.values())[:10]:
        if row not in candidates:
            candidates.append(row)
    if grouped:
        support = list(grouped.values())[:4]
        candidates = candidates[:2] + [row for row in support if row not in candidates[:2]] + [row for row in candidates[2:] if row not in support]
    continuation_cache = {}
    deeper_best, deeper_score, deeper_count = best, -float("inf"), 0
    for _, action, first_values in candidates:
        if time.monotonic() >= deadline:
            break
        indices = list(range(min(5, len(responses))))
        worst = sorted(range(len(responses)), key=lambda index: first_values[index])[:3]
        for index in worst:
            if index not in indices:
                indices.append(index)
        values, selected_weights = [], []
        complete = True
        for index in indices:
            if time.monotonic() >= deadline:
                complete = False
                break
            result = _simulate(board, reserves, state, action, responses[index], details=True)
            immediate, child, field_after, reserves_after = result
            def future_value(child, field_after, reserves_after):
                key = (tuple((m.species, round(m.hp, 4), tuple(sorted(m.boosts.items())), m.status, m.item, m.first_turn, m.protect_streak, tuple(sorted(m.effects))) if m else None for m in child), field_after["weather"], tuple(sorted(field_after["fields"])), tuple(tuple(sorted(s)) for s in field_after["conditions"]), tuple(tuple(sorted((name, round(m.hp, 4)) for name, m in side.items())) for side in reserves_after))
                if key not in continuation_cache:
                    continuation_cache[key] = _continuation(child, reserves_after, field_after)
                return continuation_cache[key]
            value = immediate + .78 * future_value(child, field_after, reserves_after)
            if speed_tie:
                alternate, alternate_child, alternate_field, alternate_reserves = _simulate(board, reserves, state, action, responses[index], tie=1, details=True)
                value = .5 * (value + alternate + .78 * future_value(alternate_child, alternate_field, alternate_reserves))
            values.append(value)
            selected_weights.append(weights[index])
        if not complete:
            break
        average = sum(value * weight for value, weight in zip(values, selected_weights)) / max(1e-9, sum(selected_weights))
        score = (1 - risk) * average + risk * min(values)
        score += .004 * _quick(board, reserves, state, action, 0)
        deeper_count += 1
        if score > deeper_score:
            deeper_best, deeper_score = action, score
    if deeper_count:
        best, best_score = deeper_best, deeper_score
    pending_action = dict(best)
    if any(forced) and pending.get("turn") == turn:
        for slot in range(2):
            key = f"slot_{slot}"
            if pending_action.get(key, {}).get("type") == "pass" and pending.get("action", {}).get(key):
                pending_action[key] = pending["action"][key]
    tracking["pending"] = {"turn": turn, "action": pending_action}
    tracking["last_search"] = {"candidates": len(ranked), "responses": len(responses), "second_turn_candidates": deeper_count, "score": round(best_score, 4), "seconds": round(time.monotonic() - started, 4), "inferred_opponent_moves": sum(bool(move.get("inferred")) for mon in board[2:] if mon for move in mon.moves)}
    return best
