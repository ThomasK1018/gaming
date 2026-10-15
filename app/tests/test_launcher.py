from pathlib import Path

import pytest

from pokemon_bot import launcher


@pytest.mark.parametrize('choice,expected', [('1', ['--match']), ('2', ['--tournament']), ('3', ['--match', '--tournament']), ('4', ['--check-tournament'])])
def test_launcher_passes_explicit_mode_flags_without_saving_key(monkeypatch, tmp_path, choice, expected):
    import agent.__main__ as runtime
    import dotenv
    monkeypatch.setattr(launcher, '__file__', str(tmp_path / 'pokemon_bot' / 'launcher.py'))
    monkeypatch.setattr('builtins.input', lambda _: choice)
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *_: None)
    monkeypatch.delenv('ALTRUAGENT_OFFICIAL_AGENT_KEY', raising=False)
    monkeypatch.delenv('POKEMON_LOG_DIR', raising=False)
    monkeypatch.setattr(launcher.getpass, 'getpass', lambda _: 'eak_live_example_fixture_only')
    received = []
    monkeypatch.setattr(runtime, 'main', lambda args: received.append(args) or 0)
    monkeypatch.setattr(launcher.sys, 'argv', ['launcher'])
    before = Path.cwd()
    try:
        assert launcher.main() == 0
        assert received == [expected]
        assert not (tmp_path / '.env').exists()
    finally:
        launcher.os.chdir(before)
