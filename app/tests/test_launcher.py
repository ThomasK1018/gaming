from pathlib import Path

import pytest

from pokemon_bot import launcher


@pytest.mark.parametrize('choice,expected', [('1', ['--match']), ('2', ['--tournament']), ('3', ['--match', '--tournament']), ('4', ['--check-tournament'])])
@pytest.mark.parametrize('control_url', [None, 'https://custom.example.invalid'])
def test_launcher_passes_explicit_mode_flags_without_saving_key(monkeypatch, tmp_path, choice, expected, control_url):
    import agent.__main__ as runtime
    import dotenv
    monkeypatch.setattr(launcher, '__file__', str(tmp_path / 'pokemon_bot' / 'launcher.py'))
    monkeypatch.setattr('builtins.input', lambda _: choice)
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *_: None)
    monkeypatch.delenv('ALTRUAGENT_OFFICIAL_AGENT_KEY', raising=False)
    monkeypatch.delenv('POKEMON_LOG_DIR', raising=False)
    if control_url is None:
        monkeypatch.delenv('ALTRUAGENT_CONTROL_URL', raising=False)
    else:
        monkeypatch.setenv('ALTRUAGENT_CONTROL_URL', control_url)
    monkeypatch.setattr(launcher.getpass, 'getpass', lambda _: 'eak_live_example_fixture_only')
    received = []
    monkeypatch.setattr(runtime, 'main', lambda args: received.append(args) or 0)
    monkeypatch.setattr(launcher.sys, 'argv', ['launcher'])
    before = Path.cwd()
    try:
        assert launcher.main() == 0
        assert received == [expected]
        assert launcher.os.environ['ALTRUAGENT_CONTROL_URL'] == (control_url or 'https://api.altruagent-game.com')
        assert not (tmp_path / '.env').exists()
    finally:
        launcher.os.chdir(before)
