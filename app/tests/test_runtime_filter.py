from altruagent.models import OfficialAssignment
from altruagent.supervisor import ALL_KINDS, TESTING, TOURNAMENT, TournamentState, run_tournament_once


class Process:
    def __init__(self, target, args, daemon):
        self.args = args
        self.pid = 123
    def start(self):
        pass
    def is_alive(self):
        return True


class Official:
    def assignments(self):
        return [OfficialAssignment(match_id=game + kind, seat_id=game + kind, game_type=game, context=kind)
                for game in ('pokemon_vgc_doubles_draft', 'redalert', 'werewolf')
                for kind in ('testing', 'tournament')]


def test_pokemon_process_does_not_claim_other_game_seats():
    state = TournamentState()
    run_tournament_once(Official(), state, agent_spec='pokemon_bot.agent', kinds=ALL_KINDS, process_factory=Process, log=lambda _: None)
    assert len(state.registry) == 2
    assert all(key.startswith('pokemon_vgc_doubles_draft') for key in state.registry.keys())


def test_testing_and_tournament_mode_filters_are_respected():
    for kind in (TESTING, TOURNAMENT):
        state = TournamentState()
        run_tournament_once(Official(), state, agent_spec='pokemon_bot.agent', kinds={kind}, process_factory=Process, log=lambda _: None)
        assert len(state.registry) == 1
        assert next(iter(state.registry.keys())).endswith(kind.lower())
