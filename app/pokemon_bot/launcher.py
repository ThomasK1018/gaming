import getpass
import os
import sys
from pathlib import Path


def self_test():
    import httpx
    import mcp
    from altruagent import DecisionContext, GameState
    from pokemon_bot.agent import PokemonAgent
    from pokemon_bot.legal import validate_action
    from pokemon_bot.dex import species_data, move_data, type_effectiveness
    assert species_data('Incineroar')['types'] == ['Fire', 'Dark']
    assert move_data('Protect')['priority'] == 4
    assert type_effectiveness('Electric', ['Ground']) == 0
    moves = [{'type': 'move', 'move_id': 'flamethrower', 'targets': [1, 2], 'base_power': 90, 'category': 'SPECIAL', 'move_type': 'FIRE', 'accuracy': 1.0}]
    template = {'type': 'doubles_turn', 'slots': [{'slot': i, 'active': {'species': 'incineroar'}, 'options': moves} for i in (0, 1)]}
    state = GameState.from_mcp_state({'session_id': 'self-test', 'game_type': 'pokemon_vgc_doubles_draft', 'phase': 'moving', 'state_version': 0, 'is_current_actor': True, 'observation': {'turn': 1, 'opponent_active_pokemon': [{'species': 'rillaboom'}, {'species': 'amoonguss'}]}, 'legal_actions': {'actions': [{'action_id': 'doubles_turn', 'input': {'action': template}}]}})
    context = DecisionContext(session_id='self-test', tournament_id=None, game_type='pokemon_vgc_doubles_draft', agent_id='self')
    action = PokemonAgent().choose_action(state, context)
    assert validate_action(action, template)
    print('PASS: Python, network libraries, offline Dex and legal battle decision.')
    print('This offline test does not authenticate or start a match.')
    return 0


def main():
    if '--self-test' in sys.argv:
        return self_test()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    os.environ.setdefault('ALTRUAGENT_CONTROL_URL', 'https://api.altruagent-game.com')
    os.environ.setdefault('POKEMON_LOG_DIR', str(root / 'logs'))
    print('AltruAgent Pokemon VGC Bot 1.0')
    print('1  Test matches\n2  Tournament matches\n3  Both\n4  Check connection\n5  Offline self-test')
    choice = input('Select [3]: ').strip() or '3'
    if choice == '5':
        return self_test()
    modes = {'1': ['--match'], '2': ['--tournament'], '3': ['--match', '--tournament'], '4': ['--check-tournament']}
    if choice not in modes:
        print('Unknown selection. Restart and choose 1-5.')
        return 2
    if not os.environ.get('ALTRUAGENT_OFFICIAL_AGENT_KEY'):
        key = getpass.getpass('Official Agent Key (hidden; kept in memory): ').strip()
        if not key:
            print('No key entered.')
            return 2
        os.environ['ALTRUAGENT_OFFICIAL_AGENT_KEY'] = key
    print('Pokemon assignments only. Keep this window open while playing.')
    from agent.__main__ import main as runtime_main
    sys.argv = ['agent', *modes[choice]]
    return runtime_main(modes[choice])


if __name__ == '__main__':
    raise SystemExit(main())
