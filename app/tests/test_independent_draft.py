"""Draft regressions for self-supported pressure; not platform win-rate tests."""

from dataclasses import replace

import pytest

from pokemon_bot.draft import _Evaluation, _entry_terrains, _fakeout_targets, _profile


def card(species, moves, ability, item="", **extra):
    return {"species": species, "moves": moves, "ability": ability, "item": item, "level": 50, **extra}


@pytest.mark.parametrize("raw", [
    card("Rillaboom", ["Wood Hammer", "Grassy Glide", "Fake Out", "U-turn"], "Grassy Surge", "Assault Vest"),
    card("Urshifu-Rapid-Strike", ["Surging Strikes", "Close Combat", "Aqua Jet", "Protect"], "Unseen Fist", "Mystic Water"),
    card("Gholdengo", ["Make It Rain", "Shadow Ball", "Nasty Plot", "Protect"], "Good as Gold", "Air Balloon"),
    card("Flutter Mane", ["Moonblast", "Shadow Ball", "Icy Wind", "Protect"], "Protosynthesis", "Booster Energy"),
    card("Basculegion", ["Wave Crash", "Aqua Jet", "Liquidation", "Protect"], "Adaptability", "Life Orb"),
])
def test_actual_attacking_sets_supply_independent_pressure(raw):
    assert "independent" in _profile(raw, "candidate").roles


def test_rillaboom_priority_requires_its_own_grounded_terrain_set():
    raw = card("Rillaboom", ["Wood Hammer", "Grassy Glide"], "Grassy Surge")
    assert "priority" in _profile(raw, "grounded").roles
    assert "priority" not in _profile(raw | {"ability": "Overgrow"}, "no-terrain").roles
    assert "priority" not in _profile(raw | {"item": "Air Balloon"}, "airborne").roles


@pytest.mark.parametrize("raw", [
    card("Rillaboom", ["Wood Hammer", "Grassy Glide"], "Overgrow"),
    card("Gholdengo", ["Nasty Plot", "Protect", "Reflect", "Light Screen"], "Good as Gold"),
    card("Gholdengo", [], "Good as Gold"),
    card("Ludicolo", ["Hydro Pump", "Giga Drain", "Ice Beam", "Protect"], "Swift Swim", "Life Orb"),
])
def test_species_name_or_unactivated_partner_ability_is_not_enough(raw):
    assert "independent" not in _profile(raw, "candidate").roles


def test_immediate_pressure_changes_otherwise_equal_lead_preference():
    # Same offensive stats and moves: this isolates the opening preference
    # from the existing damage model and species strength priors.
    passive = _profile(card("Gholdengo", ["Shadow Ball", "Protect"], "Good as Gold"), "passive")
    dependent = _profile(card("Gholdengo", ["Shadow Ball", "Protect"], "Unburden"), "dependent")
    ally = _profile(card("Rillaboom", ["Wood Hammer"], "Overgrow"), "ally")
    foes = [_profile(card("Snorlax", ["Body Slam"], "Immunity"), "foe1"),
            _profile(card("Blissey", ["Seismic Toss"], "Natural Cure"), "foe2")]
    ev = _Evaluation([passive, dependent, ally, *foes])
    assert ev.lead(("passive", "ally"), ("foe1", "foe2")) > ev.lead(("dependent", "ally"), ("foe1", "foe2"))


def test_fourth_independent_attacker_gets_no_extra_role_reward():
    base = _profile(card("Gholdengo", ["Shadow Ball"], "Good as Gold"), "base")
    first = [replace(base, key=f"core{i}") for i in range(3)]
    fourth = replace(base, key="fourth")
    other = replace(base, key="other", roles=base.roles - {"independent"})
    ev = _Evaluation([*first, fourth, other])
    core = tuple(mon.key for mon in first)
    assert ev.team(core + ("fourth",), ()) == ev.team(core + ("other",), ())


def test_independent_label_does_not_override_type_immunity():
    attacker = _profile(card("Gholdengo", ["Shadow Ball"], "Good as Gold"), "attacker")
    immune = _profile(card("Snorlax", ["Body Slam"], "Immunity"), "immune")
    assert "independent" in attacker.roles
    assert _Evaluation([attacker, immune]).damage(attacker, immune) == 0


@pytest.mark.parametrize("ability", ["Armor Tail", "Queenly Majesty", "Dazzling"])
def test_priority_blocker_protects_itself_and_its_active_partner(ability):
    attacker = _profile(card("Azumarill", ["Aqua Jet"], "Huge Power"), "attacker")
    blank = replace(attacker, key="blank", moves=(), roles=frozenset())
    ally = _profile(card("Gholdengo", ["Shadow Ball"], "Good as Gold"), "ally")
    target = _profile(card("Incineroar", ["Flare Blitz"], "Blaze"), "target")
    guard = _profile(card("Farigiraf", ["Psychic", "Trick Room"], ability), "guard")
    ev = _Evaluation([attacker, blank, ally, target, guard])
    assert ev.damage(attacker, guard) == 0
    assert ev.damage(attacker, target) > 0
    assert ev.lead(("attacker", "ally"), ("target", "guard")) == pytest.approx(
        ev.lead(("blank", "ally"), ("target", "guard")))


@pytest.mark.parametrize("species,ability,ordinary,priority,terrain", [
    ("Rillaboom", "Grassy Surge", "Wood Hammer", "Grassy Glide", "grass"),
    ("Urshifu-Rapid-Strike", "Unseen Fist", "Surging Strikes", "Aqua Jet", ""),
])
def test_blocked_priority_preserves_normal_attack_and_cache_context(species, ability, ordinary, priority, terrain):
    attacker = _profile(card(species, [ordinary, priority], ability), "attacker")
    normal = replace(attacker, key="normal", moves=attacker.moves[:1])
    quick = replace(attacker, key="quick", moves=attacker.moves[1:])
    target = _profile(card("Incineroar", ["Flare Blitz"], "Blaze"), "target")
    ev = _Evaluation([attacker, normal, quick, target])
    assert ev.damage(quick, target, terrain=terrain) > 0
    assert ev.damage(quick, target, terrain=terrain, guarded=True) == 0
    assert ev.damage(quick, target, terrain=terrain) > 0
    assert ev.damage(attacker, target, terrain=terrain, guarded=True) == pytest.approx(
        ev.damage(normal, target, terrain=terrain, guarded=True))
    assert ev.damage(attacker, target, terrain=terrain, guarded=True) > 0


def test_weak_priority_move_does_not_speed_up_stronger_normal_attack():
    attacker = _profile(card("Urshifu-Rapid-Strike", ["Surging Strikes", "Aqua Jet"], "Unseen Fist"), "attacker")
    normal = replace(attacker, key="normal", moves=attacker.moves[:1])
    target = _profile(card("Blissey", ["Ice Beam"], "Natural Cure"), "target")
    # Raise HP to avoid the damage cap hiding a false priority bonus.
    target = replace(target, stats=target.stats | {"hp": 2000})
    ev = _Evaluation([attacker, normal, target])
    assert ev.damage(attacker, target, terrain="", outspeed=0.45) == pytest.approx(
        ev.damage(normal, target, terrain="", outspeed=0.45))


@pytest.mark.parametrize("types,ability,item,blocked", [
    (["normal"], "Immunity", "", True),
    (["normal", "flying"], "Keen Eye", "", False),
    (["normal"], "Levitate", "", False),
    (["normal"], "Immunity", "Air Balloon", False),
    (["normal", "flying"], "Keen Eye", "Iron Ball", True),
])
def test_psychic_terrain_depends_on_target_grounding(types, ability, item, blocked):
    attacker = _profile(card("Azumarill", ["Aqua Jet"], "Huge Power"), "attacker")
    target = _profile(card("Snorlax", ["Body Slam"], ability, item, types=types), "target")
    ev = _Evaluation([attacker, target])
    assert (ev.damage(attacker, target, terrain="psychic") == 0) == blocked
    assert bool(_fakeout_targets([target], "psychic")) == (not blocked)


def test_grassy_glide_is_ordinary_without_grass_and_priority_with_it():
    attacker = _profile(card("Rillaboom", ["Grassy Glide"], "Grassy Surge"), "attacker")
    target = _profile(card("Incineroar", ["Flare Blitz"], "Blaze"), "target")
    ev = _Evaluation([attacker, target])
    assert ev.damage(attacker, target, terrain="grass", guarded=True) == 0
    assert ev.damage(attacker, target, terrain="psychic", guarded=True) > 0
    airborne = replace(attacker, key="airborne", item="airballoon")
    assert ev.damage(airborne, target, terrain="grass", guarded=True) > 0


def test_lead_terrain_uses_both_sides_and_slowest_setter():
    grass = _profile(card("Rillaboom", ["Wood Hammer"], "Grassy Surge"), "grass")
    psychic = _profile(card("Indeedee-F", ["Psychic"], "Psychic Surge"), "psychic")
    grass, psychic = replace(grass, speed=100), replace(psychic, speed=90)
    assert _entry_terrains([grass, psychic]) == ("psychic",)
    assert _entry_terrains([replace(grass, speed=80), psychic]) == ("grass",)
    assert set(_entry_terrains([replace(grass, speed=90), psychic])) == {"grass", "psychic"}


def test_benched_priority_guard_does_not_block_lead_damage():
    raw = [card("Azumarill", ["Aqua Jet"], "Huge Power"),
           card("Gholdengo", ["Shadow Ball"], "Good as Gold"),
           card("Incineroar", ["Flare Blitz"], "Blaze"),
           card("Snorlax", ["Body Slam"], "Immunity")]
    mons = [_profile(mon, str(i)) for i, mon in enumerate(raw)]
    bench = _profile(card("Farigiraf", ["Psychic"], "Armor Tail"), "bench")
    assert _Evaluation(mons).lead(("0", "1"), ("2", "3")) == pytest.approx(
        _Evaluation([*mons, bench]).lead(("0", "1"), ("2", "3")))
