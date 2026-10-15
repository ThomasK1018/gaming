"""Behavioral checks for the small, rule-based early-tempo update."""
from pokemon_bot.battle import _make_mon, _simulate
from pokemon_bot.draft import _profile


def test_same_species_prefers_immediate_damage_over_setup_only():
    common = {"species": "Garchomp", "ability": "Rough Skin", "item": "Clear Amulet"}
    attack = _profile(dict(common, moves=["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]), "attack")
    setup = _profile(dict(common, moves=["Swords Dance", "Sand Attack", "Protect", "Rest"]), "setup")
    assert attack.quality > setup.quality


def test_early_ko_bonus_requires_unspent_enemy_action_and_expires():
    attacker = _make_mon({"species": "Flutter Mane", "moves": ["Moonblast"]}, 0, 0, {}, 1, {})
    victim = _make_mon({"species": "Garchomp", "moves": ["Tackle"], "current_hp_fraction": .01}, 1, 0, {}, 1, {})
    board = [attacker, None, victim, None]
    attack = {"slot_0": {"type": "move", "move_id": "moonblast", "target": 1}}
    reply = {"slot_0": {"type": "move", "move_id": "tackle", "target": 1}}
    def score(turn, response):
        field = {"weather": "", "fields": set(), "conditions": [set(), set()], "turn": turn}
        return _simulate(board, [{}, {}], field, attack, response)
    assert abs(score(4, reply) - score(5, reply) - .18) < 1e-8
    assert score(4, {}) == score(5, {})
