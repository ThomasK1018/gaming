"""Small regressions motivated by the Oct 15/16 public replay timelines.

These are controlled scenarios, not exact replay observations or win-rate tests.
"""
import pytest

from pokemon_bot.battle import (
    _make_mon, _move, _policy_candidates, _quick, _tailwind_gain, choose_battle,
)
from pokemon_bot.legal import enumerate_actions, validate_action


def mon(species, side=0, slot=0, **extra):
    return _make_mon({"species": species, **extra}, side, slot, {}, 1, {})


def state(**extra):
    return {"weather": "", "fields": set(), "conditions": [set(), set()], **extra}


def template(move_id, targets, second=None):
    return {"type": "doubles_turn", "slots": [
        {"slot": 0, "options": [{"type": "move", "move_id": move_id, "targets": targets}]},
        {"slot": 1, "options": second or [{"type": "pass"}]},
    ]}


@pytest.mark.parametrize("species,move_id", [
    ("Incineroar", "fakeout"), ("Iron Hands", "drainpunch"), ("Amoonguss", "spore"),
])
def test_policy_never_deliberately_attacks_or_sleeps_ally(species, move_id):
    obs = {"turn": 1, "active_pokemon": [
        {"species": species, "moves": [move_id]}, {"species": "Porygon2", "moves": ["Recover"]}],
        "opponent_active_pokemon": [{"species": "Snorlax", "moves": ["Tackle"]}, None]}
    legal = template(move_id, [-2, 1])
    action = choose_battle(obs, legal, {})
    assert action["slot_0"]["target"] == 1
    assert validate_action(action, legal)


@pytest.mark.parametrize("move_id", ["pollenpuff", "helpinghand", "healpulse"])
def test_ally_support_is_preserved(move_id):
    board = [mon("Amoonguss", moves=[move_id]), mon("Snorlax", slot=1), None, None]
    legal = enumerate_actions(template(move_id, [-2, 1]))
    assert _policy_candidates(legal, board, state()) == legal


@pytest.mark.parametrize("buff", ["tailwind", "lightscreen", "reflect"])
def test_active_team_buff_is_not_recast(buff):
    obs = {"turn": 6, "side_conditions": [buff], "active_pokemon": [
        {"species": "Whimsicott", "moves": [buff, "Moonblast"]}, None],
        "opponent_active_pokemon": [{"species": "Snorlax", "moves": ["Tackle"]}, None]}
    legal = template(buff, [0])
    legal["slots"][0]["options"].append({"type": "move", "move_id": "moonblast", "targets": [1]})
    action = choose_battle(obs, legal, {})
    assert action["slot_0"]["move_id"] == "moonblast"
    assert validate_action(action, legal)


def test_duplicate_tailwind_and_forced_only_legal_fallback():
    board = [mon("Tornadus"), mon("Whimsicott", slot=1), mon("Snorlax", 1), None]
    legal = template("tailwind", [0], [
        {"type": "move", "move_id": "tailwind", "targets": [0]},
        {"type": "move", "move_id": "moonblast", "targets": [1]}])
    candidates = _policy_candidates(enumerate_actions(legal), board, state())
    assert len(candidates) == 1
    assert candidates[0]["slot_1"]["move_id"] == "moonblast"
    only = enumerate_actions(template("tailwind", [0]))
    assert _policy_candidates(only, board, state(conditions=[{"tailwind"}, set()])) == only


def test_tailwind_bonus_requires_speed_order_improvement():
    board = [mon("Tornadus", stats={"spe": 100}), None, mon("Snorlax", 1, stats={"spe": 150}), None]
    assert _tailwind_gain(board, state(), 0) > 0
    board[2].stats["spe"] = 50
    assert _tailwind_gain(board, state(), 0) == 0
    board[2].stats["spe"] = 150
    assert _tailwind_gain(board, state(fields={"trickroom"}), 0) == 0
    assert _tailwind_gain(board, state(conditions=[{"tailwind"}, set()]), 0) == 0


def test_switch_ranking_accounts_for_both_foes_and_remaining_hp():
    current = mon("Incineroar")
    incoming = mon("Gyarados", moves=["Waterfall"])
    foe = mon("Iron Hands", 1, moves=["Thunder Punch"], stats={"atk": 30})
    board = [current, None, foe, None]
    reserves = [{"gyarados": incoming}, {}]
    switch = {"slot_0": {"type": "switch", "species": "gyarados"}}
    one = _quick(board, reserves, state(), switch, 0)
    board[3] = mon("Iron Hands", 1, 1, moves=["Thunder Punch"], stats={"atk": 30})
    two = _quick(board, reserves, state(), switch, 0)
    assert two < one
    incoming.hp = .4
    assert _quick(board, reserves, state(), switch, 0) < two


def test_immunity_switch_beats_electric_weak_switch():
    board = [mon("Incineroar"), None, mon("Iron Hands", 1, moves=["Wild Charge"]), None]
    reserves = [{"gyarados": mon("Gyarados", moves=["Waterfall"]),
                 "landorustherian": mon("Landorus-Therian", moves=["Earthquake"])}, {}]
    scores = {name: _quick(board, reserves, state(), {"slot_0": {"type": "switch", "species": name}}, 0)
              for name in reserves[0]}
    assert scores["landorustherian"] > scores["gyarados"]
