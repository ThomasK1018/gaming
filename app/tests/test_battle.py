import copy
import time
import unittest

from pokemon_bot.battle import _blocked, _damage, _make_mon, _move, _next_actions, _priority, _simulate, _status_possible, _targets, _usable, choose_battle
from pokemon_bot.legal import validate_action


def state(**extra):
    result = {"weather": "", "fields": set(), "conditions": [set(), set()]}
    result.update(extra)
    return result


def mon(species, side=0, slot=0, **extra):
    return _make_mon({"species": species, "current_hp_fraction": 1, **extra}, side, slot, {}, 1, {})


def move(ident, target=1):
    return {"type": "move", "move_id": ident, "target": target}


def joint(first, second=None):
    return {"type": "doubles_turn", "slot_0": first, "slot_1": second or {"type": "pass"}}


class DamageTests(unittest.TestCase):
    def test_percent_opponent_hp_is_scaled_to_calculated_stats(self):
        target = _make_mon({"species": "Blissey", "current_hp": 43, "max_hp": 100}, 1, 0, {}, 3, {})
        self.assertGreater(target.maxhp, 300)
        self.assertAlmostEqual(target.hp, .43)

    def test_public_draft_moves_survive_empty_or_partial_revelation(self):
        memory = {"sets": {"incineroar": {"moves": ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"], "ability": "Intimidate"}}}
        for revealed in ({}, {"fakeout": {"current_pp": 4}}):
            target = _make_mon({"species": "Incineroar", "moves": revealed, "ability": None}, 1, 0, memory, 3, {})
            self.assertEqual({m["id"] for m in target.moves}, {"fakeout", "flareblitz", "knockoff", "partingshot"})
            self.assertEqual(target.ability, "intimidate")

    def test_move_template_does_not_overwrite_element_type(self):
        parsed = _move({"type": "move", "move_id": "thunderbolt", "targets": [1, 2]})
        self.assertEqual(parsed["type"], "electric")

    def test_unknown_opponent_moves_are_threat_hypotheses_not_struggle(self):
        target = _make_mon({"species": "Flutter Mane", "moves": {}}, 1, 0, {}, 7, {})
        attacker = mon("Garchomp")
        attacks = [m for m in target.moves if m.get("inferred") and m["category"] != "status"]
        self.assertTrue(attacks)
        self.assertTrue(any(_damage(target, attacker, m, state(), [attacker, None, target, None]) > .2 for m in attacks))
        self.assertNotIn("struggle", {m["id"] for m in target.moves})

    def test_known_complete_set_does_not_invent_coverage(self):
        memory = {"sets": {"fluttermane": {"moves": ["Moonblast", "Shadow Ball", "Dazzling Gleam", "Protect"]}}}
        target = _make_mon({"species": "Flutter Mane", "moves": {}}, 1, 0, memory, 7, {})
        self.assertEqual(len(target.moves), 4)
        self.assertFalse(any(m.get("inferred") for m in target.moves))

    def test_type_and_ability_immunity(self):
        attacker = mon("Raichu", moves=["Thunderbolt"])
        ground = mon("Landorus-Therian", 1)
        absorber = mon("Raichu", 1, ability="Lightning Rod")
        self.assertEqual(_damage(attacker, ground, _move("thunderbolt"), state(), [attacker, None, ground, None]), 0)
        self.assertEqual(_damage(attacker, absorber, _move("thunderbolt"), state(), [attacker, None, absorber, None]), 0)

    def test_weather_screen_and_burn_change_damage(self):
        attacker = mon("Incineroar", moves=["Flare Blitz"])
        target = mon("Amoonguss", 1)
        board = [attacker, None, target, None]
        neutral = _damage(attacker, target, _move("flareblitz"), state(), board)
        rain = _damage(attacker, target, _move("flareblitz"), state(weather="rain"), board)
        screen = _damage(attacker, target, _move("flareblitz"), state(conditions=[set(), {"reflect"}]), board)
        attacker.status = "brn"
        burned = _damage(attacker, target, _move("flareblitz"), state(), board)
        self.assertAlmostEqual(rain / neutral, .5)
        self.assertAlmostEqual(screen / neutral, 2 / 3)
        self.assertAlmostEqual(burned / neutral, .5)

    def test_spore_immunities(self):
        attacker = mon("Amoonguss", moves=["Spore"])
        for target in (mon("Rillaboom", 1), mon("Incineroar", 1, item="Safety Goggles"), mon("Mandibuzz", 1, ability="Overcoat"), mon("Gholdengo", 1, ability="Good as Gold")):
            self.assertFalse(_status_possible(attacker, target, _move("spore"), state(), [attacker, None, target, None]))
        target = mon("Incineroar", 1)
        self.assertEqual(_status_possible(attacker, target, _move("spore"), state(), [attacker, None, target, None]), "slp")
        self.assertFalse(_status_possible(attacker, target, _move("spore"), state(fields={"electricterrain"}), [attacker, None, target, None]))

    def test_grassy_glide_and_psychic_priority(self):
        attacker, target = mon("Rillaboom"), mon("Indeedee-F", 1)
        self.assertEqual(_priority(attacker, _move("grassyglide"), state(fields={"grassyterrain"})), 1)
        self.assertTrue(_blocked(attacker, target, _move("fakeout"), state(fields={"psychicterrain"}), [attacker, None, target, None]))

    def test_fake_out_first_turn_only(self):
        attacker = mon("Incineroar")
        self.assertTrue(_usable(attacker, _move("fakeout")))
        attacker.first_turn = False
        self.assertFalse(_usable(attacker, _move("fakeout")))

    def test_ruin_field_modifies_defense_but_not_holder(self):
        attacker, target, holder = mon("Metagross"), mon("Snorlax", 1), mon("Chien-Pao", slot=1, ability="Sword of Ruin")
        regular = _damage(attacker, target, _move("ironhead"), state(), [attacker, None, target, None])
        ruined = _damage(attacker, target, _move("ironhead"), state(), [attacker, holder, target, None])
        self.assertGreater(ruined, regular * 1.25)
        target.ability = "swordofruin"
        protected = _damage(attacker, target, _move("ironhead"), state(), [attacker, holder, target, None])
        self.assertAlmostEqual(protected, regular)


class JointTurnTests(unittest.TestCase):
    def test_protect_blocks_friendly_earthquake(self):
        board = [mon("Garchomp", moves=["Earthquake"]), mon("Gholdengo", slot=1, moves=["Protect"]), mon("Raichu", 1, moves=["Splash"]), None]
        enemy = joint(move("splash", 0))
        safe = _simulate(board, [{}, {}], state(), joint(move("earthquake", 0), move("protect", 0)), enemy)
        unsafe = _simulate(board, [{}, {}], state(), joint(move("earthquake", 0)), enemy)
        self.assertGreater(safe, unsafe + .2)

    def test_life_dew_heals_own_side(self):
        board = [mon("Goodra", moves=["Life Dew"], current_hp_fraction=.3), mon("Arcanine", slot=1, current_hp_fraction=.3), mon("Incineroar", 1, current_hp_fraction=.3), None]
        self.assertEqual(_targets(0, move("lifedew", 0), _move("lifedew"), board, state()), [0, 1])
        value = _simulate(board, [{}, {}], state(), joint(move("lifedew", 0)), joint({"type": "pass"}))
        self.assertGreater(value, .4)

    def test_sucker_punch_fails_against_status_and_already_acted_target(self):
        board = [mon("Kingambit", moves=["Sucker Punch"]), None, mon("Cresselia", 1, moves=["Calm Mind"]), None]
        failed = _simulate(board, [{}, {}], state(), joint(move("suckerpunch")), joint(move("calmmind", 0)))
        passed = _simulate(board, [{}, {}], state(), joint({"type": "pass"}), joint(move("calmmind", 0)))
        self.assertAlmostEqual(failed, passed)

    def test_helping_hand_does_not_buff_good_as_gold(self):
        board = [mon("Indeedee-F", moves=["Helping Hand"]), mon("Gholdengo", slot=1, ability="Good as Gold", moves=["Shadow Ball"]), mon("Snorlax", 1), None]
        self.assertTrue(_blocked(board[0], board[1], _move("helpinghand"), state(), board))

    def test_consecutive_protect_is_less_reliable(self):
        board = [mon("Pelipper", moves=["Protect"]), None, mon("Regieleki", 1, moves=["Thunderbolt"]), None]
        enemy = joint(move("thunderbolt"))
        first = _simulate(board, [{}, {}], state(), joint(move("protect", 0)), enemy)
        board[0].protect_streak = 1
        repeated = _simulate(board, [{}, {}], state(), joint(move("protect", 0)), enemy)
        self.assertGreater(first, repeated + .2)

    def test_wide_guard_still_blocks_with_only_one_target(self):
        board = [mon("Pelipper", moves=["Wide Guard"]), None, mon("Tyranitar", 1, moves=["Rock Slide"]), None]
        blocked = _simulate(board, [{}, {}], state(), joint(move("wideguard", 0)), joint(move("rockslide", 0)))
        unblocked = _simulate(board, [{}, {}], state(), joint({"type": "pass"}), joint(move("rockslide", 0)))
        self.assertGreater(blocked, unblocked + .3)

    def test_stamina_boosts_body_press_within_same_turn(self):
        board = [mon("Metagross", moves=["Bullet Punch"]), None, mon("Archaludon", 1, moves=["Body Press"]), None]
        no_ability = _simulate(board, [{}, {}], state(), joint(move("bulletpunch")), joint(move("bodypress")))
        board[2].ability = "stamina"
        stamina = _simulate(board, [{}, {}], state(), joint(move("bulletpunch")), joint(move("bodypress")))
        self.assertLess(stamina, no_ability - .05)

    def test_second_turn_respects_choice_lock(self):
        board = [mon("Gholdengo", item="Choice Specs", moves=["Shadow Ball", "Thunderbolt"]), None, mon("Snorlax", 1, moves=["Splash"]), None]
        _, child, after, _ = _simulate(board, [{}, {}], state(), joint(move("shadowball")), joint(move("splash", 0)), details=True)
        actions = _next_actions(child, after, 0)
        self.assertTrue(all(action["slot_0"].get("move_id") == "shadowball" for action in actions))

    def test_second_turn_blood_moon_is_unavailable_but_first_still_hits(self):
        board = [mon("Ursaluna-Bloodmoon", moves=["Blood Moon", "Earth Power"]), None, mon("Snorlax", 1, moves=["Splash"]), None]
        _, child, after, _ = _simulate(board, [{}, {}], state(), joint(move("bloodmoon")), joint(move("splash", 0)), details=True)
        self.assertLess(child[2].hp, 1)
        actions = _next_actions(child, after, 0)
        self.assertTrue(all(action["slot_0"].get("move_id") != "bloodmoon" for action in actions))

    def test_slow_team_sets_trick_room_and_preserves_vulnerable_attacker(self):
        ours = [{"species": "Farigiraf", "ability": "Armor Tail", "max_hp": 400, "stats": {"hp": 400, "def": 300, "spd": 300, "spa": 50, "spe": 10}, "moves": ["Trick Room", "Psychic", "Helping Hand", "Protect"]}, {"species": "Torkoal", "max_hp": 200, "stats": {"hp": 200, "spa": 400, "spe": 5}, "moves": ["Eruption", "Flamethrower", "Earth Power", "Protect"]}]
        foes = [{"species": "Inteleon", "stats": {"spa": 300, "spe": 200, "spd": 80}, "moves": ["Water Pulse", "Ice Beam", "Dark Pulse", "Protect"]}, {"species": "Rillaboom", "stats": {"atk": 200, "spe": 150}, "moves": ["Wood Hammer", "Grassy Glide", "U-turn", "Protect"]}]
        observation = {"turn": 1, "active_pokemon": ours, "opponent_active_pokemon": foes}
        options = [[("trickroom", [0]), ("psychic", [1, 2]), ("helpinghand", [-2]), ("protect", [0])], [("eruption", [0]), ("flamethrower", [1, 2]), ("earthpower", [1, 2]), ("protect", [0])]]
        template = {"type": "doubles_turn", "slots": [{"slot": slot, "options": [{"type": "move", "move_id": ident, "targets": targets} for ident, targets in choices]} for slot, choices in enumerate(options)]}
        memory = {}
        chosen = choose_battle(observation, template, memory)
        self.assertEqual(chosen["slot_0"]["move_id"], "trickroom")
        self.assertEqual(chosen["slot_1"]["move_id"], "protect")
        self.assertGreater(memory["battle"]["last_search"]["second_turn_candidates"], 1)

    def test_double_protect_does_not_displace_immediate_winning_attacks(self):
        ours = [{"species": "Flutter Mane", "stats": {"spe": 300, "spa": 300}, "moves": ["Shadow Ball", "Protect"]}, {"species": "Gholdengo", "stats": {"spe": 280, "spa": 300}, "moves": ["Shadow Ball", "Protect"]}]
        foes = [{"species": "Gengar", "current_hp_fraction": .2, "moves": ["Shadow Ball", "Sludge Bomb", "Thunderbolt", "Energy Ball"]}, {"species": "Alakazam", "current_hp_fraction": .2, "moves": ["Psychic", "Shadow Ball", "Dazzling Gleam", "Energy Ball"]}]
        template = {"type": "doubles_turn", "slots": [{"slot": i, "options": [{"type": "move", "move_id": "shadowball", "targets": [1, 2]}, {"type": "move", "move_id": "protect", "targets": [0]}]} for i in range(2)]}
        chosen = choose_battle({"turn": 1, "active_pokemon": ours, "opponent_active_pokemon": foes}, template, {})
        self.assertEqual(chosen["slot_0"]["move_id"], "shadowball")
        self.assertEqual(chosen["slot_1"]["move_id"], "shadowball")

    def test_joint_action_search_splits_guaranteed_knockouts(self):
        ours = [{"species": "Flutter Mane", "moves": ["Shadow Ball"], "stats": {"spe": 300, "spa": 300}}, {"species": "Gholdengo", "moves": ["Shadow Ball"], "stats": {"spe": 280, "spa": 300}}]
        foes = [{"species": "Gengar", "current_hp_fraction": .2, "moves": ["Shadow Ball"]}, {"species": "Alakazam", "current_hp_fraction": .2, "moves": ["Psychic"]}]
        obs = {"turn": 1, "active_pokemon": ours, "opponent_active_pokemon": foes, "available_moves": [[{"id": "shadowball"}], [{"id": "shadowball"}]]}
        template = {"type": "doubles_turn", "slots": [{"slot": i, "options": [{"type": "move", "move_id": "shadowball", "targets": [1, 2]}]} for i in range(2)]}
        chosen = choose_battle(obs, template, {})
        self.assertNotEqual(chosen["slot_0"]["target"], chosen["slot_1"]["target"])

    def test_full_policy_is_legal_and_does_not_mutate_observation(self):
        ours = [{"species": "Incineroar", "moves": ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"], "ability": "Intimidate"}, {"species": "Rillaboom", "moves": ["Fake Out", "Grassy Glide", "Wood Hammer", "U-turn"], "ability": "Grassy Surge"}]
        foes = [{"species": "Urshifu-Rapid-Strike", "moves": ["Surging Strikes", "Close Combat", "Aqua Jet", "Protect"], "ability": "Unseen Fist"}, {"species": "Gholdengo", "moves": ["Make It Rain", "Shadow Ball", "Nasty Plot", "Protect"], "ability": "Good as Gold"}]
        obs = {"turn": 1, "active_pokemon": ours, "opponent_active_pokemon": foes, "team": list(ours), "available_switches": [[{"species": "Pelipper"}], [{"species": "Pelipper"}]], "fields": ["grassyterrain"]}
        template = {"type": "doubles_turn", "slots": [{"slot": i, "options": [{"type": "move", "move_id": ident, "targets": [1, 2]} for ident in (["fakeout", "flareblitz", "knockoff", "partingshot"] if i == 0 else ["fakeout", "grassyglide", "woodhammer", "uturn"])] + [{"type": "switch", "species": "pelipper"}]} for i in range(2)]}
        before = copy.deepcopy(obs)
        start = time.monotonic()
        chosen = choose_battle(obs, template, {})
        self.assertTrue(validate_action(chosen, template))
        self.assertEqual(obs, before)
        self.assertLess(time.monotonic() - start, 3)

    def test_single_choice_still_updates_entry_memory(self):
        observation = {"turn": 1, "active_pokemon": [{"species": "Incineroar", "moves": ["Fake Out"]}, None], "opponent_active_pokemon": [{"species": "Snorlax", "moves": ["Splash"]}, None]}
        template = {"type": "doubles_turn", "slots": [{"slot": 0, "options": [{"type": "move", "move_id": "fakeout", "targets": [1]}]}, {"slot": 1, "options": [{"type": "pass"}]}]}
        memory = {}
        choose_battle(observation, template, memory)
        self.assertEqual(memory["battle"]["positions"]["0:0"]["entered"], 1)
        observation["turn"] = 2
        choose_battle(observation, template, memory)
        self.assertEqual(memory["battle"]["positions"]["0:0"]["entered"], 1)

    def test_speed_ties_do_not_always_favor_own_side(self):
        observation = {"turn": 1, "active_pokemon": [{"species": "Gengar", "moves": ["Shadow Ball"], "current_hp_fraction": .1}, None], "opponent_active_pokemon": [{"species": "Gengar", "moves": ["Shadow Ball", "Sludge Bomb", "Thunderbolt", "Energy Ball"], "current_hp_fraction": .1}, None]}
        template = {"type": "doubles_turn", "slots": [{"slot": 0, "options": [{"type": "move", "move_id": "shadowball", "targets": [1]}]}, {"slot": 1, "options": [{"type": "pass"}]}]}
        memory = {}
        choose_battle(observation, template, memory)
        self.assertLess(abs(memory["battle"]["last_search"]["score"]), .1)

    def test_forced_switch_preserves_legal_one_reserve_rule(self):
        obs = {"turn": 2, "force_switch": [True, True], "active_pokemon": [{"species": "Gholdengo", "fainted": True}, {"species": "Tornadus", "fainted": True}], "opponent_active_pokemon": [{"species": "Incineroar", "moves": ["Flare Blitz"]}, None], "team": [{"species": "Pelipper", "current_hp_fraction": 1}]}
        options = [{"type": "switch", "species": "pelipper"}, {"type": "pass"}]
        template = {"type": "doubles_turn", "slots": [{"slot": i, "options": options} for i in range(2)]}
        chosen = choose_battle(obs, template, {})
        self.assertTrue(validate_action(chosen, template))
        self.assertEqual(sum(chosen[f"slot_{i}"]["type"] == "switch" for i in range(2)), 1)


if __name__ == "__main__":
    unittest.main()
