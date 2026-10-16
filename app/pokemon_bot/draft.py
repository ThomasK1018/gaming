from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import exp, sqrt
from typing import Any

from .dex import move_data, norm, species_data, stat_values, type_effectiveness


_TYPES = ("normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy")
_PRIOR = {
    "calyrexshadow": 5.4, "calyrexice": 5.0, "miraidon": 5.0, "koraidon": 4.8,
    "kyogre": 4.6, "groudon": 4.3, "zacian": 3.2, "zaciancrowned": 4.7,
    "zamazentacrowned": 4.4, "terapagos": 3.0, "lunala": 3.6, "necrozmaduskmane": 2.8,
    "incineroar": 3.3, "rillaboom": 2.7, "urshifurapidstrike": 3.7, "urshifu": 3.3,
    "fluttermane": 3.6, "tornadus": 2.5, "tornadusincarnate": 2.5, "amoonguss": 2.7,
    "ogerponwellspring": 3.5, "ogerponhearthflame": 3.3, "ogerpon": 2.5,
    "landorus": 2.7, "landorustherian": 2.6, "ragingbolt": 3.1, "ironhands": 2.5,
    "chiyu": 2.9, "chienpao": 2.6, "whimsicott": 2.0,
    "gholdengo": 2.8, "ursalunabloodmoon": 3.1, "ursaluna": 2.5, "farigiraf": 2.3,
    "indeedeef": 1.7, "hatterene": 1.7, "torkoal": 1.6, "pelipper": 1.4,
    "dondozo": 1.7, "tatsugiri": 0.4, "dragonite": 2.0, "porygon2": 2.0,
    "enamorus": 1.9, "enamorustherian": 1.7,
}
_ABILITY_VALUE = {
    "intimidate": 1.7, "prankster": 1.8, "unseenfist": 1.6, "goodasgold": 1.2,
    "grassysurge": 1.0, "psychicsurge": 1.0, "electricsurge": 0.7,
    "drizzle": 1.2, "drought": 1.2, "hadronengine": 1.6, "orichalcumpulse": 1.6,
    "asone": 1.4, "asonespectrier": 1.4, "asoneglastrier": 1.4,
    "shadowshield": 1.4, "multiscale": 1.0, "disguise": 0.9, "sturdy": 0.6,
    "beadsofruin": 1.1, "swordofruin": 1.1, "tabletsofruin": 0.2,
    "defiant": 0.8, "competitive": 0.8, "clearbody": 0.7, "innerfocus": 0.8,
    "friendguard": 1.6, "armortail": 1.7, "queenlymajesty": 1.2, "dazzling": 1.0,
    "regenerator": 0.9, "waterabsorb": 0.5, "stormdrain": 1.0, "lightningrod": 0.8,
}
_STATUS_VALUE = {
    "protect": 0.65, "detect": 0.65, "spikyshield": 0.75, "silktrap": 0.7,
    "kingsshield": 0.65, "banefulbunker": 0.65, "burningbulwark": 0.7,
    "tailwind": 1.7, "trickroom": 1.6, "spore": 1.8, "ragepowder": 1.5,
    "followme": 1.7, "fakeout": 1.4, "helpinghand": 0.6, "wideguard": 0.85,
    "quickguard": 0.3, "partingshot": 1.0, "icywind": 0.8, "electroweb": 0.8,
    "taunt": 0.65, "thunderwave": 0.6, "willowisp": 0.6, "encore": 0.7,
    "nuzzle": 0.8, "snarl": 0.6, "screens": 0.5, "auroraveil": 1.1,
}
_WEATHER_ABILITIES = {"drizzle": "rain", "drought": "sun", "orichalcumpulse": "sun", "sandstream": "sand", "snowwarning": "snow"}
_PRIORITY_GUARDS = {"armortail", "queenlymajesty", "dazzling"}
_TERRAIN_ABILITIES = {"grassysurge": "grass", "psychicsurge": "psychic", "electricsurge": "electric", "hadronengine": "electric", "mistysurge": "misty"}
_CHART_CACHE: dict[tuple[str, tuple[str, ...]], float] = {}


def _effect(kind: str, types: tuple[str, ...]) -> float:
    key = (kind, types)
    if key not in _CHART_CACHE:
        try:
            _CHART_CACHE[key] = float(type_effectiveness(kind, list(types)))
        except (KeyError, TypeError, ValueError):
            _CHART_CACHE[key] = 1.0
    return _CHART_CACHE[key]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _move_id(value: Any) -> str:
    if isinstance(value, dict):
        return norm(value.get("id") or value.get("move_id") or value.get("name") or value.get("move") or "")
    return norm(str(value))


def _merge_set(value: Any, memory: dict) -> dict:
    if isinstance(value, str):
        value = {"species": value}
    if not isinstance(value, dict):
        return {}
    species = norm(value.get("species") or value.get("name") or value.get("id") or "")
    known = memory.get("sets", {}).get(species, {})
    merged = dict(known) if isinstance(known, dict) else {}
    for key, entry in value.items():
        if entry is not None and entry != "" and entry != [] and entry != {}:
            merged[key] = entry
    merged["species"] = species
    return merged


@dataclass(frozen=True)
class _Move:
    name: str
    kind: str
    category: str
    power: float
    accuracy: float
    priority: float
    spread: bool


@dataclass
class _Mon:
    key: str
    species: str
    types: tuple[str, ...]
    stats: dict[str, float]
    ability: str
    item: str
    moves: tuple[_Move, ...]
    roles: frozenset[str]
    quality: float
    physical: float
    special: float
    speed: float
    weather: str


def _profile(raw: dict, key: str) -> _Mon:
    species = norm(raw.get("species") or raw.get("name") or key)
    data = species_data(species) or {}
    types = tuple(norm(x) for x in (raw.get("types") or data.get("types") or ["normal"]))
    ability = norm(raw.get("ability") or "")
    if not ability:
        abilities = data.get("abilities", {})
        if isinstance(abilities, dict):
            ability = norm(abilities.get("0") or next(iter(abilities.values()), ""))
    item = norm(raw.get("item") or "")
    try:
        computed = stat_values(raw)
    except (KeyError, TypeError, ValueError):
        computed = {}
    base = raw.get("base_stats") or data.get("baseStats") or data.get("base_stats") or {}
    stats = {}
    for stat in ("hp", "atk", "def", "spa", "spd", "spe"):
        fallback = _num(base.get(stat), 80) + (75 if stat == "hp" else 20)
        stats[stat] = max(1, _num(computed.get(stat), fallback)) if isinstance(computed, dict) else fallback
    if item == "eviolite":
        stats["def"] *= 1.5
        stats["spd"] *= 1.5
    if item == "assaultvest":
        stats["spd"] *= 1.5
    if ability in {"hugepower", "purepower"}:
        stats["atk"] *= 2
    if ability in {"guts", "toxicboost"} and item in {"flameorb", "toxicorb"}:
        stats["atk"] *= 1.5
    if ability == "gorillatactics":
        stats["atk"] *= 1.5
    if ability in {"intrepidsword", "orichalcumpulse"}:
        stats["atk"] *= 1.25
    if ability == "hadronengine":
        stats["spa"] *= 1.25
    if item == "choiceband":
        stats["atk"] *= 1.5
    if item == "choicespecs":
        stats["spa"] *= 1.5
    speed = stats["spe"] * (1.5 if item == "choicescarf" else 0.5 if item in {"ironball", "machobrace"} else 1)
    names = raw.get("moves") or []
    if isinstance(names, dict):
        names = list(names)
    moves = []
    roles = set()
    for value in names:
        mid = _move_id(value)
        source = dict(move_data(mid) or {})
        if isinstance(value, dict):
            source.update(value)
        category = norm(source.get("category") or "status")
        power = _num(source.get("basePower", source.get("base_power")), 0)
        if mid == "surgingstrikes":
            power = 112.5
        elif mid in {"wickedblow", "flowertrick"}:
            power *= 1.5
        elif mid in {"watershuriken", "bulletseed", "rockblast", "iciclespear", "pinmissile"}:
            power *= 4.5 if item == "loadeddice" or ability == "skilllink" else 3.0
        elif mid == "populationbomb":
            power *= 7.5 if item == "widelens" else 5.8
        elif mid == "tripleaxel":
            power = 105
        elif mid == "electroball":
            power = 80
        elif mid in {"gyroball", "grassknot", "lowkick", "heavyslam", "heatcrash"}:
            power = 85
        elif mid in {"return", "frustration"}:
            power = 102
        elif mid == "facade" and item in {"flameorb", "toxicorb"}:
            power *= 2
        accuracy = source.get("accuracy", 100)
        accuracy = 1.0 if accuracy is True else _num(accuracy, 100)
        if accuracy > 1:
            accuracy /= 100
        target = norm(source.get("target") or "")
        moves.append(_Move(mid, norm(source.get("type", source.get("move_type")) or types[0]), category, power, accuracy, _num(source.get("priority")), target in {"alladjacent", "alladjacentfoes"}))
        if mid in {"tailwind", "trickroom", "fakeout", "taunt", "spore", "helpinghand", "wideguard", "encore"}:
            roles.add(mid)
        if mid in {"ragepowder", "followme"}:
            roles.add("redirect")
        if mid in {"icywind", "electroweb", "thunderwave", "nuzzle", "glare"}:
            roles.add("speedcontrol")
        if mid in {"protect", "detect", "spikyshield", "silktrap", "kingsshield", "banefulbunker", "burningbulwark"}:
            roles.add("protect")
        if mid in {"swordsdance", "nastyplot", "calmmind", "quiverdance", "dragondance", "bellydrum", "bulkup"}:
            roles.add("setup")
        if mid in {"trickroom", "imprison"} and "imprison" in {_move_id(x) for x in names}:
            roles.add("antitrickroom")
        if _num(source.get("priority")) > 0 and category != "status" and mid != "fakeout":
            roles.add("priority")
    damaging = [move for move in moves if move.power > 0 and move.category != "status"]
    if not moves:
        category = "physical" if stats["atk"] >= stats["spa"] else "special"
        moves = [_Move("unknownstab", types[0], category, 75, 1, 0, False)]
        damaging = moves[:]
    physical = max((move.power * move.accuracy * stats["atk"] / 160 for move in damaging if move.category == "physical"), default=0)
    special = max((move.power * move.accuracy * stats["spa"] / 160 for move in damaging if move.category == "special"), default=0)
    offense = max(physical, special)
    # Draft-only role estimates: reward the offered set, not a species name.
    # The battle evaluator still checks the actual terrain and grounding.
    self_grass = ability == "grassysurge" and "flying" not in types and item != "airballoon"
    if self_grass and any(move.name == "grassyglide" for move in damaging):
        roles.add("priority")
    reliable_stab = [move for move in damaging if move.kind in types and move.power >= 70 and move.accuracy >= 0.9]
    passive_pressure = (
        ability in {"adaptability", "goodasgold"}
        or ability == "unseenfist" and any(move.name in {"surgingstrikes", "wickedblow", "closecombat"} for move in reliable_stab)
        or self_grass and any(move.kind == "grass" for move in reliable_stab)
        or ability == "beadsofruin" and any(move.category == "special" for move in reliable_stab)
        or ability == "swordofruin" and any(move.category == "physical" for move in reliable_stab)
        or item == "boosterenergy" and ability in {"protosynthesis", "quarkdrive"}
    )
    if names and offense > 70 and reliable_stab and (passive_pressure or speed >= 135):
        roles.add("independent")
    bulk = sqrt(stats["hp"] * sqrt(stats["def"] * stats["spd"]))
    # Early-tempo profile: modestly favor immediate offense and speed.
    quality = 0.036 * offense + 0.026 * bulk + 0.014 * speed + _PRIOR.get(species, 0)
    if "priority" in roles:
        quality += 0.45
    # Owning a setup move is not itself a drawback: penalize weak immediate output.
    if "setup" in roles and offense <= 70:
        quality -= 0.60
    quality += _ABILITY_VALUE.get(ability, 0)
    quality += min(3.8, sum(_STATUS_VALUE.get(move.name, 0) for move in moves))
    quality += 0.65 * sum(move.spread for move in damaging)
    if item in {"focussash", "sitrusberry", "clearamulet", "boosterenergy"}:
        quality += 0.65
    if item == "lifeorb":
        quality += 0.7
    if ability == "prankster" and "tailwind" in roles:
        quality += 0.9
    if ability == "intimidate":
        roles.add("intimidate")
    if ability in {"armortail", "queenlymajesty", "dazzling", "psychicsurge"}:
        roles.add("antipriority")
    if ability in {"swift swim", "swiftswim", "raindish", "hydration"} or "water" in types:
        roles.add("rainbenefit")
    if ability in {"chlorophyll", "protosynthesis", "solarpower"} or "fire" in types:
        roles.add("sunbenefit")
    if ability == "chlorophyll":
        roles.add("sunspeed")
    if ability == "swiftswim":
        roles.add("rainspeed")
    if ability in {"slushrush", "icebody", "snowcloak"} or "ice" in types:
        roles.add("snowbenefit")
    if ability in {"sandrush", "sandforce", "sandveil"} or "rock" in types:
        roles.add("sandbenefit")
    weather = _WEATHER_ABILITIES.get(ability, "")
    if not weather:
        weather = "rain" if "raindance" in {_move_id(x) for x in names} else "sun" if "sunnyday" in {_move_id(x) for x in names} else ""
    return _Mon(key, species, types, stats, ability, item, tuple(moves), frozenset(roles), quality, physical, special, speed, weather)


def _grounded(mon: _Mon) -> bool:
    return mon.item == "ironball" or ("flying" not in mon.types and mon.ability != "levitate" and mon.item != "airballoon")


def _entry_terrains(mons: list[_Mon]) -> tuple[str, ...]:
    # Opening abilities resolve fastest first; the slowest setter wins.
    # Average tied setters rather than promising either terrain will remain.
    setters = [mon for mon in mons if mon.ability in _TERRAIN_ABILITIES]
    if not setters:
        return ("",)
    slowest = min(mon.speed for mon in setters)
    return tuple(_TERRAIN_ABILITIES[mon.ability] for mon in setters if mon.speed == slowest)


def _priority_protected(defender: _Mon, guarded: bool, terrain: str) -> bool:
    return guarded or defender.ability in _PRIORITY_GUARDS or terrain == "psychic" and _grounded(defender)


def _fakeout_targets(targets: list[_Mon], terrain: str) -> list[_Mon]:
    guarded = any(mon.ability in _PRIORITY_GUARDS for mon in targets)
    return [mon for mon in targets if not _priority_protected(mon, guarded, terrain)
            and "ghost" not in mon.types and mon.ability not in {"innerfocus", "shielddust"} and mon.item != "covertcloak"]


class _Evaluation:
    def __init__(self, mons: list[_Mon]):
        self.mons = {mon.key: mon for mon in mons}
        self.damage_cache: dict[tuple[str, str, str, bool, float | None], float] = {}
        self.team_cache: dict[tuple[tuple[str, ...], tuple[str, ...]], float] = {}
        self.pair_cache: dict[tuple[str, str], float] = {}

    def damage(self, attacker: _Mon, defender: _Mon, *, terrain: str | None = None, guarded: bool = False, outspeed: float | None = None) -> float:
        if terrain is None:
            terrains = _entry_terrains([attacker, defender])
            return sum(self.damage(attacker, defender, terrain=entry, guarded=guarded, outspeed=outspeed) for entry in terrains) / len(terrains)
        key = (attacker.key, defender.key, terrain, guarded, outspeed)
        if key in self.damage_cache:
            return self.damage_cache[key]
        best = 0.0
        for move in attacker.moves:
            if move.power <= 0 or move.category == "status":
                continue
            priority = move.priority + (1 if move.name == "grassyglide" and terrain == "grass" and _grounded(attacker) else 0)
            if priority > 0 and _priority_protected(defender, guarded, terrain):
                continue
            effectiveness = _effect(move.kind, defender.types)
            if defender.ability in {"levitate", "eartheater"} and move.kind == "ground":
                effectiveness = 0
            if defender.ability in {"waterabsorb", "stormdrain", "dryskin"} and move.kind == "water":
                effectiveness = 0
            if defender.ability in {"voltabsorb", "lightningrod", "motordrive"} and move.kind == "electric":
                effectiveness = 0
            if defender.ability == "flashfire" and move.kind == "fire":
                effectiveness = 0
            if defender.ability == "sapsipper" and move.kind == "grass":
                effectiveness = 0
            if defender.ability in {"thickfat", "heatproof"} and move.kind in {"fire", "ice"}:
                effectiveness *= 0.5
            if defender.ability in {"multiscale", "shadowshield"}:
                effectiveness *= 0.7
            if defender.ability == "purifyingsalt" and move.kind == "ghost":
                effectiveness *= 0.5
            atk = attacker.stats["atk"] if move.category == "physical" else attacker.stats["spa"]
            defense = defender.stats["def"] if move.category == "physical" else defender.stats["spd"]
            if move.name == "bodypress":
                atk = attacker.stats["def"]
            if move.name == "foulplay":
                atk = defender.stats["atk"]
            if move.name in {"psyshock", "psystrike", "secretsword"}:
                defense = defender.stats["def"]
            if defender.ability == "intimidate" and move.category == "physical" and attacker.ability not in {"defiant", "competitive", "clearbody", "innerfocus", "fullmetalbody"} and attacker.item != "clearamulet" and move.name not in {"surgingstrikes", "wickedblow"}:
                atk *= 0.82
            if defender.ability == "intimidate" and (attacker.ability == "defiant" and move.category == "physical" or attacker.ability == "competitive" and move.category == "special"):
                atk *= 1.3
            stab = 1.5 if move.kind in attacker.types else 1.0
            if attacker.ability == "adaptability" and stab > 1:
                stab = 2.0
            modifier = 1.3 if attacker.item == "lifeorb" else 1.0
            if attacker.ability in {"beadsofruin", "hadronengine"} and move.category == "special":
                modifier *= 1.25 if attacker.ability == "beadsofruin" else 1
            if attacker.ability == "swordofruin" and move.category == "physical":
                modifier *= 1.25
            if attacker.ability == "technician" and move.power <= 60:
                modifier *= 1.5
            if attacker.ability in {"sheerforce", "toughclaws", "sharpness"}:
                modifier *= 1.15
            if move.kind == "water" and attacker.weather == "rain" or move.kind == "fire" and attacker.weather == "sun":
                modifier *= 1.5
            if move.spread:
                modifier *= 0.75
            fraction = (22 * move.power * atk / defense / 50 + 2) * stab * effectiveness * modifier * 0.925 / defender.stats["hp"]
            fraction *= move.accuracy
            if priority > 0:
                fraction *= 1.08
            if outspeed is not None:
                # A weak priority move must not lend its speed to a stronger
                # ordinary attack. Score each usable move before taking max.
                fraction *= 0.72 + 0.28 * (max(outspeed, 0.85) if priority > 0 else outspeed)
            if move.name == "fakeout":
                fraction *= 0.4
            best = max(best, fraction)
        self.damage_cache[key] = min(1.65, best)
        return self.damage_cache[key]

    def synergy(self, a: _Mon, b: _Mon) -> float:
        key = tuple(sorted((a.key, b.key)))
        if key in self.pair_cache:
            return self.pair_cache[key]
        value = 0.0
        for setter, partner in ((a, b), (b, a)):
            if "tailwind" in setter.roles:
                value += 1.5 if partner.speed >= 90 and max(partner.physical, partner.special) > 65 else 0.35
            if "trickroom" in setter.roles:
                value += 2.1 if partner.speed < 80 and max(partner.physical, partner.special) > 65 else 0.7 if partner.speed < 105 else -0.2
            if "fakeout" in setter.roles and partner.roles & {"tailwind", "trickroom", "setup", "spore"}:
                value += 1.15
            if "redirect" in setter.roles and partner.roles & {"trickroom", "setup"}:
                value += 1.6
            if "redirect" in setter.roles and max(partner.physical, partner.special) > 110:
                value += 0.55
            if setter.weather:
                if setter.weather + "benefit" in partner.roles:
                    value += 1.3
                if setter.weather + "speed" in partner.roles:
                    value += 1.9
                if setter.weather == "rain" and "fire" in partner.types:
                    value -= 1.0
                if setter.weather == "sun" and "water" in partner.types:
                    value -= 0.85
            if setter.ability == "grassysurge":
                if partner.species in {"ragingbolt", "incineroar", "ursaluna"}:
                    value += 0.65
                if "ground" in partner.types and any(move.name == "earthquake" for move in partner.moves):
                    value -= 0.8
            if setter.ability == "psychicsurge":
                if any(move.name == "expandingforce" for move in partner.moves):
                    value += 3.2
                if "priority" in partner.roles or "fakeout" in partner.roles:
                    value -= 0.85
            if setter.ability in {"beadsofruin", "swordofruin"}:
                relevant = partner.special if setter.ability == "beadsofruin" else partner.physical
                value += 0.9 if relevant > 90 else -0.25
            if setter.ability == "friendguard":
                value += 0.7
            if setter.ability == "stormdrain" and _effect("water", partner.types) > 1:
                value += 0.8
            if setter.ability == "lightningrod" and _effect("electric", partner.types) > 1:
                value += 0.8
            if any(move.name in {"earthquake", "discharge", "surf", "lavaplume"} for move in setter.moves):
                kind = {"earthquake": "ground", "discharge": "electric", "surf": "water", "lavaplume": "fire"}
                for move in setter.moves:
                    if move.name in kind:
                        eff = _effect(kind[move.name], partner.types)
                        immune = eff == 0 or kind[move.name] == "ground" and partner.ability == "levitate" or kind[move.name] == "water" and partner.ability in {"waterabsorb", "stormdrain"} or kind[move.name] == "electric" and partner.ability in {"voltabsorb", "lightningrod"}
                        value += 0.8 if immune else -0.4 if eff >= 1 else 0.0
        if {a.species, b.species} == {"dondozo", "tatsugiri"}:
            value += 7.0
        if a.weather and b.weather and a.weather != b.weather:
            value -= 0.9
        if a.roles & b.roles & {"redirect"}:
            value -= 1.25
        if max(a.physical, a.special) < 55 and max(b.physical, b.special) < 55:
            value -= 1.3
        cover = 0.0
        overlap = 0.0
        for kind in _TYPES:
            ae, be = _effect(kind, a.types), _effect(kind, b.types)
            if ae > 1 and be < 1 or be > 1 and ae < 1:
                cover += 0.08
            if ae > 1 and be > 1:
                overlap += 0.12 * min(ae, be)
        value += min(0.7, cover) - min(1.5, overlap)
        self.pair_cache[key] = value
        return value

    def team(self, own: tuple[str, ...], opposition: tuple[str, ...]) -> float:
        key = (tuple(sorted(own)), tuple(sorted(opposition)))
        if key in self.team_cache:
            return self.team_cache[key]
        members = [self.mons[entry] for entry in own]
        enemies = [self.mons[entry] for entry in opposition]
        if not members:
            return 0.0
        n = len(members)
        quality = sorted((mon.quality for mon in members), reverse=True)
        value = sum(quality[:4]) + 0.25 * sum(quality[4:])
        # A small preference for up to three attackers that need no setup
        # turn or partner activation. Matchups and item legality still decide.
        value += 0.8 * min(3, sum("independent" in mon.roles for mon in members))
        synergies = [self.synergy(a, b) for a, b in combinations(members, 2)]
        value += sum(synergies) * (0.75 if n <= 4 else 0.45)
        roles = set().union(*(mon.roles for mon in members))
        slow = sum(mon.speed < 90 and max(mon.physical, mon.special) > 65 for mon in members)
        fast = sum(mon.speed >= 135 for mon in members)
        if n >= 3:
            if not roles & {"tailwind", "trickroom", "speedcontrol"}:
                value -= 2.5 * (1 - min(fast, 3) / 4)
            if slow >= 2 and "trickroom" not in roles:
                value -= 1.1 * slow
            offense = sum(max(mon.physical, mon.special) > 70 for mon in members)
            if offense < min(n - 1, 3):
                value -= 3.0 * (min(n - 1, 3) - offense)
            if all(mon.physical > mon.special for mon in members):
                value -= 2.0
            if all(mon.special >= mon.physical for mon in members):
                value -= 1.0
        if "dondozo" in {mon.species for mon in members} and "tatsugiri" not in {mon.species for mon in members}:
            value -= 1.2
        if "tatsugiri" in {mon.species for mon in members} and "dondozo" not in {mon.species for mon in members}:
            value -= 3.7
        if enemies:
            weights = [max(1, enemy.quality - 5) for enemy in enemies]
            total = sum(weights)
            offense_score = defense_score = 0.0
            for enemy, weight in zip(enemies, weights):
                attacks = sorted((self.damage(mon, enemy) for mon in members), reverse=True)
                danger = sorted(self.damage(enemy, mon) for mon in members)
                offense_score += weight * (0.70 * attacks[0] + 0.30 * attacks[min(1, n - 1)])
                defense_score += weight * (0.45 * danger[0] + 0.25 * danger[min(1, n - 1)] + 0.30 * sum(danger) / n)
            value += min(n, 4) * (2.8 * offense_score / total - 2.0 * defense_score / total)
            if any(enemy.roles & {"trickroom"} for enemy in enemies) and slow == 0 and not roles & {"taunt", "antitrickroom", "spore", "trickroom"}:
                value -= 1.6
            if any(enemy.roles & {"intimidate"} for enemy in enemies):
                exposed = sum(mon.physical > mon.special and mon.ability not in {"defiant", "competitive", "clearbody", "innerfocus", "fullmetalbody"} and mon.item != "clearamulet" for mon in members)
                value -= max(0, exposed - 2) * 0.7
            if any(enemy.roles & {"antipriority"} for enemy in enemies):
                value -= 0.35 * sum("priority" in mon.roles for mon in members)
        self.team_cache[key] = value
        return value

    def lead(self, pair: tuple[str, str], opposition: tuple[str, str]) -> float:
        terrains = _entry_terrains([self.mons[x] for x in pair + opposition])
        return sum(self._lead_in_terrain(pair, opposition, terrain) for terrain in terrains) / len(terrains)

    def _lead_in_terrain(self, pair: tuple[str, str], opposition: tuple[str, str], terrain: str) -> float:
        own = [self.mons[x] for x in pair]
        enemies = [self.mons[x] for x in opposition]
        if len(own) < 2 or len(enemies) < 2:
            return 0.0
        value = self.synergy(*own) * 0.7
        if not _fakeout_targets(enemies, terrain):
            for setter, partner in ((own[0], own[1]), (own[1], own[0])):
                if "fakeout" in setter.roles and partner.roles & {"tailwind", "trickroom", "setup", "spore"}:
                    value -= 0.7 * 1.15
        # Discourage double low-output leads, symmetrically for both teams.
        for side, sign in ((own, 1), (enemies, -1)):
            value += sign * 0.35 * sum("independent" in mon.roles for mon in side)
            if all(max(mon.physical, mon.special) <= 70 for mon in side):
                value -= sign * 1.0
        own_control = any("tailwind" in mon.roles for mon in own)
        opp_control = any("tailwind" in mon.roles for mon in enemies)
        own_slow = sum(mon.speed < 95 for mon in own)
        opp_slow = sum(mon.speed < 95 for mon in enemies)
        own_tr = any("trickroom" in mon.roles for mon in own)
        opp_tr = any("trickroom" in mon.roles for mon in enemies)
        for side, targets, sign, controlled, counter_control in ((own, enemies, 1, own_control, opp_control), (enemies, own, -1, opp_control, own_control)):
            results = []
            guarded = any(mon.ability in _PRIORITY_GUARDS for mon in targets)
            for mon in side:
                damage = []
                for enemy in targets:
                    speed = mon.speed * (1.50 if controlled and not counter_control else 1)
                    enemy_speed = enemy.speed * (1.50 if counter_control and not controlled else 1)
                    outspeed = 1.0 if speed > enemy_speed else 0.7 if speed == enemy_speed else 0.45
                    damage.append(self.damage(mon, enemy, terrain=terrain, guarded=guarded, outspeed=outspeed))
                results.append(damage)
                if "fakeout" in mon.roles:
                    vulnerable = _fakeout_targets(targets, terrain)
                    if vulnerable:
                        value += sign * (0.75 + 0.5 * any(enemy.roles & {"trickroom", "tailwind", "spore", "setup"} for enemy in vulnerable))
                if "intimidate" in mon.roles:
                    value += sign * 0.4 * sum(enemy.physical > enemy.special and enemy.ability not in {"defiant", "competitive", "clearbody", "innerfocus", "fullmetalbody"} and enemy.item != "clearamulet" for enemy in targets)
                    value -= sign * 0.8 * sum(enemy.ability in {"defiant", "competitive"} for enemy in targets)
                if "spore" in mon.roles:
                    susceptible = sum("grass" not in enemy.types and enemy.item != "safetygoggles" and enemy.ability not in {"overcoat", "goodasgold", "insomnia", "vitalspirit", "purifyingsalt"} for enemy in targets)
                    value += sign * susceptible * 0.3
                if "taunt" in mon.roles:
                    value += sign * 0.45 * sum(bool(enemy.roles & {"tailwind", "trickroom", "redirect", "spore"}) and (mon.speed >= enemy.speed or mon.ability == "prankster" and "dark" not in enemy.types) for enemy in targets)
                if "wideguard" in mon.roles:
                    value += sign * 0.3 * sum(any(move.spread for move in enemy.moves) for enemy in targets)
            split = max(results[0][0] + results[1][1], results[0][1] + results[1][0])
            focus = max(min(1.7, results[0][j] + results[1][j]) + (0.45 if results[0][j] + results[1][j] >= 1 else 0) for j in range(2))
            value += sign * 2.8 * max(split, focus)
        if own_tr and own_slow > opp_slow:
            value += 1.0 + 0.5 * any("redirect" in mon.roles or "fakeout" in mon.roles and _fakeout_targets(enemies, terrain) for mon in own)
        if opp_tr and opp_slow > own_slow:
            value -= 1.0 + 0.5 * any("redirect" in mon.roles or "fakeout" in mon.roles and _fakeout_targets(own, terrain) for mon in enemies)
        if own_control and not opp_control:
            value += 0.7
        if opp_control and not own_control:
            value -= 0.7
        return value


def _card_id(action: Any) -> str:
    payload = action.get("input", {}) if isinstance(action, dict) else getattr(action, "input", {})
    structured = payload.get("action", {}) if isinstance(payload, dict) else {}
    action_id = action.get("action_id", "") if isinstance(action, dict) else getattr(action, "action_id", "")
    return structured.get("card_id") or str(action_id).removeprefix("draft_pick:")


def choose_draft(observation: dict, legal_actions: list, memory: dict, agent_id: str = "") -> Any:
    if not legal_actions:
        raise ValueError("A draft decision requires at least one legal action")
    stored = memory.setdefault("sets", {})
    cards = memory.setdefault("draft_cards", {})
    for card in observation.get("available_cards") or []:
        if not isinstance(card, dict):
            continue
        cid = card.get("card_id") or norm(card.get("species") or "")
        cards[cid] = dict(card)
        stored[norm(card.get("species") or "")] = dict(card)
    rosters = observation.get("rosters") or {}
    own_seat = agent_id if agent_id in rosters else observation.get("current_seat")
    if own_seat not in rosters and len(rosters) == 1:
        own_seat = next(iter(rosters))
    own_raw = rosters.get(own_seat, [])
    opp_raw = [mon for seat, roster in rosters.items() if seat != own_seat for mon in roster]
    selected = set()
    profiles = {}
    teams = [[], []]
    for side, roster in enumerate((own_raw, opp_raw)):
        for index, card in enumerate(roster):
            merged = _merge_set(card, memory)
            cid = merged.get("card_id") or f"roster-{side}-{index}"
            if cid in cards:
                merged = dict(cards[cid]) | merged
            selected.add(cid)
            profiles[cid] = _profile(merged, cid)
            teams[side].append(cid)
    picked = {pick.get("card_id") for pick in observation.get("picks", []) if isinstance(pick, dict)}
    selected.update(picked)
    legal = {_card_id(action): action for action in legal_actions}
    for cid in legal:
        if cid not in cards:
            inferred = cid.removeprefix("vgc-").removeprefix("ou-")
            cards[cid] = {"species": inferred, "card_id": cid}
    pool = [cid for cid in cards if cid not in selected]
    for cid in pool:
        profiles[cid] = _profile(_merge_set(cards[cid], memory), cid)
    evaluator = _Evaluation(list(profiles.values()))
    own, enemy = tuple(teams[0]), tuple(teams[1])
    base = evaluator.team(own, enemy)
    enemy_base = evaluator.team(enemy, own)

    def admissible(cid: str, team: tuple[str, ...]) -> bool:
        item = profiles[cid].item
        return not item or all(profiles[other].item != item for other in team)

    def gain(cid: str, team: tuple[str, ...], opponents: tuple[str, ...]) -> float:
        return evaluator.team(team + (cid,), opponents) - evaluator.team(team, opponents)

    immediate = {}
    for cid in legal:
        value = gain(cid, own, enemy)
        denial = gain(cid, enemy, own) if admissible(cid, enemy) else 0.0
        completion = 0.0
        if len(own) < 4:
            viable = [other for other in pool if other != cid and admissible(other, own + (cid,))]
            if viable:
                completion = 0.28 * max(evaluator.synergy(profiles[cid], profiles[other]) for other in viable)
        immediate[cid] = value + 0.12 * denial + completion
    contenders = sorted(legal, key=lambda cid: (immediate[cid], profiles[cid].quality, cid), reverse=True)[:7]
    first = observation.get("first_drafter")
    sequence = [0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0]
    if first and first != own_seat:
        sequence = [1 - side for side in sequence]
    consumed = len(own) + len(enemy)
    if consumed < len(sequence) and sequence[consumed] != 0:
        sequence = [1 - side for side in sequence]
    horizon = consumed + 1
    future_own = 0
    while horizon < 12 and horizon < consumed + 6:
        future_own += sequence[horizon] == 0
        horizon += 1
        if future_own >= 2 or future_own >= 1 and horizon < 12 and sequence[horizon] == 1:
            break
    scored = {}
    for candidate in contenders:
        simulated = [own + (candidate,), enemy]
        remaining = [cid for cid in pool if cid != candidate]
        forecast = []
        for step in range(consumed + 1, horizon):
            side = sequence[step]
            options = [cid for cid in remaining if admissible(cid, simulated[side])]
            if not options or len(simulated[side]) >= 6:
                continue
            other = 1 - side
            chosen = max(options, key=lambda cid: gain(cid, simulated[side], simulated[other]) + 0.10 * (gain(cid, simulated[other], simulated[side]) if admissible(cid, simulated[other]) else 0))
            simulated[side] += (chosen,)
            remaining.remove(chosen)
            forecast.append({"side": "own" if side == 0 else "opponent", "card_id": chosen})
        result = evaluator.team(simulated[0], simulated[1]) - base
        enemy_gain = evaluator.team(simulated[1], simulated[0]) - enemy_base
        rating = result - 0.68 * enemy_gain + 0.22 * immediate[candidate]
        scored[candidate] = (rating, forecast)
    chosen = max(contenders, key=lambda cid: (scored[cid][0], immediate[cid], cid))
    memory["draft_scores"] = [{"card_id": cid, "score": round(scored[cid][0], 4), "immediate": round(immediate[cid], 4), "forecast": scored[cid][1]} for cid in sorted(contenders, key=lambda cid: scored[cid][0], reverse=True)]
    return legal[chosen]


def _weighted_robust(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    total = sum(weight for _, weight in values)
    average = sum(value * weight for value, weight in values) / total
    remaining = total * 0.25
    tail = 0.0
    for value, weight in sorted(values):
        take = min(weight, remaining)
        tail += value * take
        remaining -= take
        if remaining <= 1e-12:
            break
    lower = tail / (total * 0.25)
    return 0.65 * average + 0.35 * lower


def choose_lineup(observation: dict, template: dict, memory: dict) -> dict:
    own_raw = observation.get("your_roster") or []
    if isinstance(own_raw, dict):
        own_raw = list(own_raw.values())
    roster_ids = template.get("roster") or []
    exact_names = {norm(entry): entry for entry in roster_ids if isinstance(entry, str)}
    if not own_raw:
        own_raw = roster_ids
    enemy_raw = observation.get("opponent_roster") or []
    if isinstance(enemy_raw, dict):
        enemy_raw = list(enemy_raw.values())
    own = []
    enemy = []
    roster_names = {}
    for side, raw_list, output in (("own", own_raw, own), ("enemy", enemy_raw, enemy)):
        seen = set()
        for entry in raw_list:
            raw = _merge_set(entry, memory)
            species = norm(raw.get("species") or "")
            if not species or species in seen:
                continue
            seen.add(species)
            key = side + ":" + species
            output.append(_profile(raw, key))
            roster_names[key] = exact_names.get(species, species) if side == "own" else species
    if not own:
        raise ValueError("Team preview did not provide a roster")
    evaluator = _Evaluation(own + enemy)
    own_keys = tuple(mon.key for mon in own)
    enemy_keys = tuple(mon.key for mon in enemy)
    own_fours = list(combinations(own_keys, min(4, len(own_keys))))
    enemy_fours = list(combinations(enemy_keys, min(4, len(enemy_keys)))) if enemy else []
    enemy_pairs = list(combinations(enemy_keys, 2)) if len(enemy) >= 2 else []
    enemy_quality = {team: evaluator.team(team, own_keys) for team in enemy_fours}
    strongest = max(enemy_quality.values(), default=0.0)
    enemy_weights = {team: exp(max(-8, (quality - strongest) / 4)) for team, quality in enemy_quality.items()}
    pair_weights = {}
    for pair in enemy_pairs:
        mass = sum(enemy_weights[team] for team in enemy_fours if set(pair).issubset(team))
        lead_quality = evaluator.synergy(*(evaluator.mons[key] for key in pair))
        role_bonus = sum(bool(evaluator.mons[key].roles & {"fakeout", "tailwind", "trickroom", "intimidate", "redirect"}) for key in pair)
        pair_weights[pair] = max(1e-6, mass * exp(max(-3, min(3, (lead_quality + 0.8 * role_bonus) / 3))))
    pair_values = {}
    for pair in combinations(own_keys, 2):
        pair_values[pair] = _weighted_robust([(evaluator.lead(pair, opponents), pair_weights[opponents]) for opponents in enemy_pairs])
        if not enemy_pairs:
            pair_values[pair] = evaluator.synergy(*(evaluator.mons[key] for key in pair))
    candidates = []
    for team in own_fours:
        team_value = evaluator.team(team, enemy_keys)
        if enemy_fours:
            matchup_values = [(evaluator.team(team, opponents) - 0.35 * evaluator.team(opponents, team), enemy_weights[opponents]) for opponents in enemy_fours]
            team_value = 0.45 * team_value + 0.55 * _weighted_robust(matchup_values)
        pairs = list(combinations(team, 2))
        lead_pair = max(pairs, key=lambda pair: pair_values[pair]) if pairs else team
        lead_value = pair_values.get(lead_pair, 0.0)
        bench = [key for key in team if key not in lead_pair]
        reserve_value = 0.0
        if bench and enemy:
            for front in lead_pair:
                threats = [foe for foe in enemy if evaluator.damage(foe, evaluator.mons[front]) > 0.65]
                if threats:
                    reserve_value += sum(max(0, evaluator.damage(foe, evaluator.mons[front]) - min(evaluator.damage(foe, evaluator.mons[backup]) for backup in bench)) for foe in threats) / len(threats)
        total = team_value + 1.25 * lead_value + 0.5 * reserve_value
        candidates.append((total, team, lead_pair, team_value, lead_value))
    candidates.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    best = candidates[0]
    bring = [roster_names[key] for key in best[2]] + [roster_names[key] for key in best[1] if key not in best[2]]
    leads = [roster_names[key] for key in best[2]]
    memory["lineup_analysis"] = [{"bring": [roster_names[key] for key in candidate[1]], "leads": [roster_names[key] for key in candidate[2]], "score": round(candidate[0], 4), "team_score": round(candidate[3], 4), "lead_score": round(candidate[4], 4)} for candidate in candidates[:5]]
    memory["selected_lineup"] = {"bring": bring, "leads": leads}
    return {"type": "select_lineup", "bring": bring, "leads": leads}
