from copy import deepcopy

import pytest

from altruagent import DecisionContext, GameState, LegalAction, WithReasoning
from altruagent.runner import run_game
from pokemon_bot.agent import PokemonAgent
from pokemon_bot.legal import enumerate_actions, validate_action


CONTEXT = DecisionContext(
    session_id="protocol-match", tournament_id=None,
    game_type="pokemon_vgc_doubles_draft", agent_id="our-agent", seat_position=0,
)
ROSTER = ["incineroar", "rillaboom", "amoonguss", "fluttermane", "gholdengo", "gyarados"]


def pokemon(species, types, hp=100, active=True):
    return {
        "species": species, "current_hp": hp, "max_hp": 100,
        "current_hp_fraction": hp / 100, "status": None, "ability": None,
        "item": None, "types": types, "base_stats": {}, "boosts": {},
        "moves": {}, "fainted": hp == 0, "active": active, "revealed": True,
        "is_terastallized": False,
    }


def move(move_id="fakeout", targets=(1, 2), move_type="NORMAL", power=40):
    return {
        "type": "move", "move_id": move_id, "base_power": power,
        "category": "PHYSICAL", "move_type": move_type, "current_pp": 10,
        "accuracy": 1.0, "targets": list(targets),
    }


def switch(species):
    return {"type": "switch", "species": species}


def doubles_template(slot_0=None, slot_1=None, forced=(False, False)):
    return {
        "type": "doubles_turn",
        "slots": [
            {"slot": 0, "board_position": -1,
             "active": pokemon("incineroar", ["FIRE", "DARK"]),
             "force_switch": forced[0],
             "options": slot_0 if slot_0 is not None else [move(), move("protect", (0,), power=0)]},
            {"slot": 1, "board_position": -2,
             "active": pokemon("rillaboom", ["GRASS"]),
             "force_switch": forced[1],
             "options": slot_1 if slot_1 is not None else [move("woodhammer", (1, 2), "GRASS", 120)]},
        ],
        "target_legend": {"1": "Opponent position A", "2": "Opponent position B",
                          "-1": "Your position A", "-2": "Your position B", "0": "No target"},
    }


def lineup_template():
    return {"type": "select_lineup", "roster": list(ROSTER), "bring_count": 4, "lead_count": 2}


def legal_entry(template, version=0):
    return {
        "action_id": template["type"], "label": template["type"],
        "input": {"session_id": CONTEXT.session_id, "state_version": version,
                  "action_id": template["type"], "action": deepcopy(template)},
    }


def battle_observation():
    own = [pokemon("incineroar", ["FIRE", "DARK"]), pokemon("rillaboom", ["GRASS"])]
    foes = [pokemon("urshifurapidstrike", ["WATER", "FIGHTING"]), pokemon("gholdengo", ["STEEL", "GHOST"])]
    return {
        "phase": "moving", "turn": 1, "format": "gen9vgc2025regi", "is_doubles": True,
        "waiting_for_action": True, "active_pokemon": own, "opponent_active_pokemon": foes,
        "team": {"p1: Incineroar": own[0], "p1: Rillaboom": own[1]},
        "opponent_team": {"p2: Urshifu": foes[0], "p2: Gholdengo": foes[1]},
        "force_switch": [False, False], "available_moves": [[], []],
        "available_switches": [[], []], "weather": {}, "fields": {},
        "side_conditions": {}, "opponent_side_conditions": {},
        "clock": {"decision_seconds_left": 41, "bank_seconds_left": 312},
    }


def state_for(template, observation=None, phase="moving", version=0):
    return GameState.from_mcp_state({
        "session_id": CONTEXT.session_id, "game_type": CONTEXT.game_type,
        "runtime_adapter": "pokemon", "status": "in_progress", "state_version": version,
        "phase": phase, "is_terminal": False, "is_current_actor": True,
        "current_actor": {"agent_id": CONTEXT.agent_id, "position": 0},
        "observation": battle_observation() if observation is None else observation,
        "legal_actions": {"session_id": CONTEXT.session_id, "state_version": version,
                          "actions": [legal_entry(template, version)]},
    })


def unwrap(decision):
    return decision.action if isinstance(decision, WithReasoning) else decision


def assert_joint_legal(action, template):
    assert isinstance(action, dict)
    assert action.get("type") == "doubles_turn"
    slots = {slot["slot"]: slot for slot in template["slots"]}
    selected_switches = []
    for number in (0, 1):
        selected = action[f"slot_{number}"]
        matching = [option for option in slots[number]["options"] if option["type"] == selected["type"]]
        if selected["type"] == "move":
            matching = [option for option in matching if option["move_id"] == selected.get("move_id")]
            assert matching
            targets = matching[0].get("targets", [])
            if targets:
                assert type(selected.get("target")) is int
                assert selected["target"] in targets
            else:
                assert "target" not in selected or selected["target"] in (None, 0)
        elif selected["type"] == "switch":
            assert any(option["species"] == selected.get("species") for option in matching)
            selected_switches.append(selected["species"])
        else:
            assert selected["type"] == "pass" and matching
    assert len(set(selected_switches)) == len(selected_switches)
    assert not all(action[f"slot_{i}"]["type"] == "pass" for i in (0, 1))
    assert validate_action(action, template)


def test_joint_enumeration_covers_both_target_choices():
    template = doubles_template([move(targets=(1, 2))], [move("woodhammer", (1, 2))])
    actions = enumerate_actions(template)
    assert len(actions) == 4
    assert {(a["slot_0"]["target"], a["slot_1"]["target"]) for a in actions} == {(1, 1), (1, 2), (2, 1), (2, 2)}
    for action in actions:
        assert_joint_legal(action, template)


@pytest.mark.parametrize("targets", [(), (0,)])
def test_targetless_options_accept_the_two_published_shapes(targets):
    template = doubles_template([move("protect", targets, power=0)], [move("heatwave", targets, "FIRE", 95)])
    actions = enumerate_actions(template)
    assert len(actions) == 1
    assert_joint_legal(actions[0], template)
    if targets:
        assert actions[0]["slot_0"]["target"] == 0


def test_one_reserve_for_two_fainted_slots_has_exactly_two_legal_actions():
    options = [switch("gholdengo"), {"type": "pass"}]
    template = doubles_template(options, deepcopy(options), forced=(True, True))
    template["notice"] = "Only one reserve remains; switch one slot and pass the other."
    actions = enumerate_actions(template)
    assert len(actions) == 2
    assert {a["slot_0"]["type"] for a in actions} == {"switch", "pass"}
    for action in actions:
        assert_joint_legal(action, template)


def test_two_reserves_never_double_switch_the_same_species():
    options = [switch("gholdengo"), switch("amoonguss")]
    template = doubles_template(options, deepcopy(options), forced=(True, True))
    actions = enumerate_actions(template)
    assert len(actions) == 2
    for action in actions:
        assert_joint_legal(action, template)


def test_enumeration_uses_slot_numbers_when_template_order_is_reversed():
    template = doubles_template([move("fakeout", (1,))], [move("woodhammer", (2,))])
    template["slots"].reverse()
    actions = enumerate_actions(template)
    assert len(actions) == 1
    assert actions[0]["slot_0"]["move_id"] == "fakeout"
    assert actions[0]["slot_1"]["move_id"] == "woodhammer"


@pytest.mark.parametrize("bad", [None, [], "doubles_turn", {}, {"type": "doubles_turn"}])
def test_validator_rejects_malformed_actions(bad):
    assert not validate_action(bad, doubles_template())


@pytest.mark.parametrize("target", [True, False, "1", 1.5, 3, -1, None])
def test_validator_rejects_unoffered_or_noninteger_targets(target):
    template = doubles_template([move(targets=(1, 2))], [move("woodhammer", (1,))])
    action = {"type": "doubles_turn", "slot_0": {"type": "move", "move_id": "fakeout", "target": target},
              "slot_1": {"type": "move", "move_id": "woodhammer", "target": 1}}
    assert not validate_action(action, template)


def test_validator_rejects_unoffered_pass_unknown_move_and_duplicate_switch():
    template = doubles_template([move(), switch("amoonguss")], [move("woodhammer"), switch("amoonguss")])
    base = {"type": "doubles_turn", "slot_0": {"type": "move", "move_id": "fakeout", "target": 1},
            "slot_1": {"type": "move", "move_id": "woodhammer", "target": 1}}
    for bad_slot in ({"type": "pass"}, {"type": "move", "move_id": "tackle", "target": 1}):
        action = {**base, "slot_0": bad_slot}
        assert not validate_action(action, template)
    assert not validate_action({"type": "doubles_turn", "slot_0": switch("amoonguss"), "slot_1": switch("amoonguss")}, template)


def test_lineup_validator_enforces_four_distinct_bring_two_distinct_leads():
    template = lineup_template()
    valid = {"type": "select_lineup", "bring": ROSTER[:4], "leads": ROSTER[:2]}
    assert validate_action(valid, template)
    for change in (
        {"bring": ROSTER[:3]}, {"bring": [ROSTER[0]] * 4}, {"bring": [*ROSTER[:3], "mewtwo"]},
        {"leads": [ROSTER[0]]}, {"leads": [ROSTER[0], ROSTER[0]]}, {"leads": [ROSTER[0], ROSTER[5]]},
    ):
        assert not validate_action({**valid, **change}, template)


def test_agent_reads_the_official_battle_envelope_without_mutating_it():
    template = doubles_template()
    state = state_for(template)
    before = deepcopy(state.raw)
    assert isinstance(state.observation, str)
    assert isinstance(state.raw["observation"], dict)
    action = unwrap(PokemonAgent().choose_action(state, CONTEXT))
    assert_joint_legal(action, template)
    assert state.raw == before


@pytest.mark.parametrize("observation", [{}, "No pending decision is currently available.", "{not JSON}", []])
def test_agent_keeps_a_legal_template_fallback_when_optional_observation_is_missing(observation):
    template = doubles_template([move("fakeout", (1,))], [{"type": "pass"}], forced=(False, False))
    action = unwrap(PokemonAgent().choose_action(state_for(template, observation), CONTEXT))
    assert_joint_legal(action, template)


def test_agent_preserves_enemy_and_ally_target_coordinates():
    slot_0_move = move("pollenpuff", (-2, 1, 2), "BUG", 90)
    slot_0_move["target_options"] = [
        {"target": -2, "side": "ally", "species": "rillaboom"},
        {"target": 1, "side": "opponent", "species": "urshifurapidstrike"},
        {"target": 2, "side": "opponent", "species": "gholdengo"},
    ]
    template = doubles_template([slot_0_move], [move("woodhammer", (1, 2), "GRASS", 120)])
    assert_joint_legal(unwrap(PokemonAgent().choose_action(state_for(template), CONTEXT)), template)


def test_agent_handles_single_forced_switch_with_other_slot_passing():
    template = doubles_template([switch("gholdengo"), switch("amoonguss")], [{"type": "pass"}], forced=(True, False))
    observation = battle_observation()
    observation["force_switch"] = [True, False]
    observation["active_pokemon"][0]["fainted"] = True
    observation["active_pokemon"][0]["current_hp_fraction"] = 0
    assert_joint_legal(unwrap(PokemonAgent().choose_action(state_for(template, observation), CONTEXT)), template)


def test_agent_handles_two_faints_and_one_reserve():
    options = [switch("gholdengo"), {"type": "pass"}]
    template = doubles_template(options, deepcopy(options), forced=(True, True))
    assert_joint_legal(unwrap(PokemonAgent().choose_action(state_for(template), CONTEXT)), template)


def test_agent_builds_a_private_preview_selection_from_roster_ids():
    template = lineup_template()
    observation = {
        "phase": "team_preview", "battle_format": "gen9vgc2025regi", "waiting_for_action": True,
        "your_roster": [{"species": species, "name": species, "types": [], "base_stats": {}} for species in ROSTER],
        "opponent_roster": [{"species": "urshifurapidstrike", "types": ["WATER", "FIGHTING"], "base_stats": {}}],
    }
    action = unwrap(PokemonAgent().choose_action(state_for(template, observation, "team_preview"), CONTEXT))
    assert isinstance(action, dict) and action["type"] == "select_lineup"
    assert len(set(action["bring"])) == 4 and set(action["bring"]) <= set(ROSTER)
    assert len(set(action["leads"])) == 2 and set(action["leads"]) <= set(action["bring"])
    assert validate_action(action, template)


def test_draft_uses_only_currently_offered_cards_and_allows_version_reset():
    agent = PokemonAgent()
    cards = [
        {"card_id": "vgc-urshifu-rapid-strike", "species": "Urshifu-Rapid-Strike", "item": "Mystic Water",
         "ability": "Unseen Fist", "nature": "Adamant", "level": 50,
         "evs": {"hp": 4, "atk": 252, "spe": 252}, "ivs": {},
         "moves": ["Surging Strikes", "Close Combat", "Aqua Jet", "Protect"]},
    ]
    observation = {
        "phase": "draft", "draft_complete": False, "battle_format": "gen9vgc2025regi",
        "current_seat": CONTEXT.agent_id, "pick_number": 12, "picks_remaining": 1,
        "first_drafter": CONTEXT.agent_id, "available_card_ids": [cards[0]["card_id"]],
        "available_cards": cards, "rosters": {CONTEXT.agent_id: [], "opponent-agent": []}, "picks": [],
        "decision_timeout_seconds": 15, "decision_deadline_at": "2099-10-16T17:00:15+00:00",
        "battle_starting": False,
    }
    action_template = {"type": "draft_pick", "card_id": cards[0]["card_id"]}
    state = state_for(action_template, observation, "draft", version=11)
    entry = state.raw["legal_actions"]["actions"][0]
    entry["action_id"] = entry["input"]["action_id"] = f"draft_pick:{cards[0]['card_id']}"
    state = GameState.from_mcp_state(state.raw)
    draft = unwrap(agent.choose_action(state, CONTEXT))
    if isinstance(draft, LegalAction):
        assert draft.action_id == entry["action_id"]
    elif isinstance(draft, str):
        assert draft == entry["action_id"]
    else:
        assert draft == action_template
    template = doubles_template()
    battle = unwrap(agent.choose_action(state_for(template, version=0), CONTEXT))
    assert_joint_legal(battle, template)


def test_can_tera_information_does_not_create_an_unsupported_action():
    template = doubles_template()
    observation = battle_observation()
    observation["can_tera"] = True
    action = unwrap(PokemonAgent().choose_action(state_for(template, observation), CONTEXT))
    assert_joint_legal(action, template)
    assert set(action) == {"type", "slot_0", "slot_1"}
    for number in (0, 1):
        assert not any("tera" in key.lower() for key in action[f"slot_{number}"])


def test_real_sdk_runner_submits_preview_battle_and_forced_switch_with_current_versions():
    preview = lineup_template()
    battle = doubles_template()
    forced = doubles_template([switch("gholdengo")], [{"type": "pass"}], forced=(True, False))
    preview_observation = {"phase": "team_preview", "your_roster": [], "opponent_roster": []}
    waiting = {
        "session_id": CONTEXT.session_id, "game_type": CONTEXT.game_type,
        "status": "in_progress", "phase": "moving", "state_version": 1,
        "is_terminal": False, "is_current_actor": False,
        "observation": {"message": "No pending decision is currently available.",
                        "waiting_for_action": False, "finished": False},
    }
    terminal = {
        "session_id": CONTEXT.session_id, "game_type": CONTEXT.game_type,
        "status": "completed", "phase": "moving", "state_version": 3,
        "is_terminal": True, "is_current_actor": False,
        "observation": {"message": "Battle finished.", "finished": True},
    }

    class ScriptedGame:
        def __init__(self):
            self.states = [state_for(preview, preview_observation, "team_preview", 0).raw, waiting,
                           state_for(battle, version=1).raw, state_for(forced, version=2).raw, terminal]
            self.actions = []
            self.waits = []

        def get_state(self):
            return GameState.from_mcp_state(self.states.pop(0))

        def wait_for_update(self, **kwargs):
            self.waits.append(kwargs)
            return self.get_state()

        def play_action(self, **kwargs):
            self.actions.append(kwargs)
            return {"accepted": True, "state": self.states.pop(0)}

        def get_result(self):
            return {"is_terminal": True, "status": "completed", "termination_reason": "completed",
                    "returns": {CONTEXT.agent_id: 1.0, "opponent-agent": 0.0}}

    game = ScriptedGame()
    final = run_game(game, CONTEXT, PokemonAgent())
    assert final.is_terminal and final.returns[CONTEXT.agent_id] == 1.0
    assert len(game.actions) == 3 and len(game.waits) == 1
    assert [call["state_version"] for call in game.actions] == [0, 1, 2]
    assert validate_action(game.actions[0]["action"], preview)
    assert_joint_legal(game.actions[1]["action"], battle)
    assert_joint_legal(game.actions[2]["action"], forced)
