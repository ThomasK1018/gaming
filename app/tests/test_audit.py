import pytest

from pokemon_bot.battle import Mon, _make_mon, _move, _next_actions, _simulate, _targets


def mon(species, side, slot, *, moves, types=("normal",), hp=1.0, speed=100,
        attack=120, ability="", item=""):
    return Mon(species=species, side=side, slot=slot, hp=hp, maxhp=200,
               stats={"hp": 200, "atk": attack, "def": 100, "spa": attack, "spd": 100, "spe": speed},
               boosts={}, types=set(types), ability=ability, item=item, status="",
               moves=[_move(name) for name in moves], first_turn=True)


def field(fields=()):
    return {"weather": "", "fields": set(fields), "conditions": [set(), set()]}


def joint(slot0=None, slot1=None):
    return {"type": "doubles_turn", "slot_0": slot0 or {"type": "pass"},
            "slot_1": slot1 or {"type": "pass"}}


def attack(move_id, target=1):
    return {"type": "move", "move_id": move_id, "target": target}


@pytest.mark.parametrize("revealed", [{}, {"fakeout": {"id": "fakeout", "current_pp": 9}}])
def test_public_draft_moves_survive_empty_or_partially_revealed_battle_moves(revealed):
    memory = {"sets": {"incineroar": {"species": "Incineroar", "moves": ["Fake Out", "Flare Blitz", "Parting Shot", "Knock Off"]}}}
    parsed = _make_mon({"species": "incineroar", "moves": revealed}, 1, 0, memory, 1, {})
    assert {move["id"] for move in parsed.moves} == {"fakeout", "flareblitz", "partingshot", "knockoff"}
    if revealed:
        assert next(move for move in parsed.moves if move["id"] == "fakeout")["current_pp"] == 9


def test_protect_prevents_damage_from_the_allied_earthquake():
    board = [
        mon("garchomp", 0, 0, moves=["earthquake"], types=("dragon", "ground")),
        mon("pikachu", 0, 1, moves=["protect"], types=("electric",)),
        mon("snorlax", 1, 0, moves=["tackle"]),
        mon("blissey", 1, 1, moves=["tackle"]),
    ]
    protected = _simulate(board, [{}, {}], field(), joint(attack("earthquake", 0), attack("protect", 0)), joint())
    unprotected = _simulate(board, [{}, {}], field(), joint(attack("earthquake", 0)), joint())
    assert protected > unprotected + .1


@pytest.mark.parametrize("enemy_move", ["swordsdance", "quickattack"])
def test_sucker_punch_fails_against_status_or_a_target_that_already_moved(enemy_move):
    board = [mon("kingambit", 0, 0, moves=["suckerpunch"], types=("dark", "steel"), speed=50), None,
             mon("arcanine", 1, 0, moves=[enemy_move], speed=150), None]
    response = joint(attack(enemy_move, 0 if enemy_move == "swordsdance" else 1))
    attempted = _simulate(board, [{}, {}], field(), joint(attack("suckerpunch")), response)
    idle = _simulate(board, [{}, {}], field(), joint(), response)
    assert attempted == pytest.approx(idle)


def test_grassy_glide_terrain_priority_wins_against_a_faster_normal_priority_attack():
    board = [mon("rillaboom", 0, 0, moves=["grassyglide"], types=("grass",), hp=.1, speed=50, attack=200), None,
             mon("sandaconda", 1, 0, moves=["tackle"], types=("ground",), hp=.1, speed=150, attack=200), None]
    score = _simulate(board, [{}, {}], field(["grassyterrain"]), joint(attack("grassyglide")), joint(attack("tackle")))
    assert score > 0


def test_life_dew_targets_the_users_two_allies_never_an_enemy():
    board = [mon("milotic", 0, 0, moves=["lifedew"], hp=.5),
             mon("incineroar", 0, 1, moves=["tackle"], hp=.5),
             mon("urshifu", 1, 0, moves=["tackle"], hp=.5), None]
    targets = _targets(0, attack("lifedew", 0), _move("lifedew"), board, field())
    assert set(targets) == {0, 1}
    score = _simulate(board, [{}, {}], field(), joint(attack("lifedew", 0)), joint())
    assert score > .3


def test_helping_hand_does_not_boost_an_ally_with_good_as_gold():
    board = [mon("cresselia", 0, 0, moves=["helpinghand"]),
             mon("gholdengo", 0, 1, moves=["shadowball"], types=("steel", "ghost"), ability="goodasgold"),
             mon("milotic", 1, 0, moves=["tackle"]), None]
    helped = _simulate(board, [{}, {}], field(), joint(attack("helpinghand", -2), attack("shadowball")), joint())
    unhelped = _simulate(board, [{}, {}], field(), joint(None, attack("shadowball")), joint())
    assert helped == pytest.approx(unhelped)


def test_continuation_does_not_reuse_a_move_after_its_last_pp():
    board = [mon("snorlax", 0, 0, moves=["tackle", "splash"]), None,
             mon("milotic", 1, 0, moves=["tackle"]), None]
    board[0].moves[0]["current_pp"] = 1
    _, child, child_field, _ = _simulate(board, [{}, {}], field(), joint(attack("tackle")), joint(), details=True)
    choices = _next_actions(child, child_field, 0)
    assert all(choice["slot_0"].get("move_id") != "tackle" for choice in choices)
    assert board[0].moves[0]["current_pp"] == 1


def test_forced_switch_does_not_tick_an_extra_residual_turn():
    board = [mon("snorlax", 0, 0, moves=["tackle"], hp=0),
             mon("arcanine", 0, 1, moves=["tackle"], hp=.5),
             mon("milotic", 1, 0, moves=["tackle"]), None]
    board[1].status = "brn"
    incoming = mon("gholdengo", 0, -1, moves=["shadowball"], hp=.5, item="leftovers")
    _, child, _, _ = _simulate(board, [{"gholdengo": incoming}, {}], field(),
                              joint({"type": "switch", "species": "gholdengo"}), joint(), details=True)
    assert child[0].hp == pytest.approx(.5)
    assert child[1].hp == pytest.approx(.5)
