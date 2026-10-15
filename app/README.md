# AltruAgent Pokémon VGC Bot

This is a complete self-hosted agent for `pokemon_vgc_doubles_draft`. It drafts six fixed sets, chooses four Pokémon and two leads, and submits simultaneous doubles actions through the official AltruAgent SDK. Gameplay uses local Python computation and bundled static Pokémon data. No LLM service or API credit is needed.

## Windows

Use the portable release: extract the entire ZIP, open `StartBot.cmd`, select a mode, and enter your Official Agent Key at the hidden prompt. The key stays in memory. Keep the window open and the computer online and awake.

1. Testing matches.
2. Tournament matches.
3. Both testing and tournament matches.
4. Check platform connection and authentication.
5. Offline self-test.

`CheckWindows.cmd` runs the offline test directly. The portable distribution includes Windows Python and dependencies; it is not a PyInstaller executable. Its binaries and dependencies were checked on Linux; native Windows execution still needs the included self-test on a Windows machine.

The runtime only claims Pokémon assignments. The account must already be registered in self-hosted mode and assigned to a test or tournament match. It does not create matches or register tournament entries.

## Source installation

Python 3.11 or newer:

```bash
python -m venv .venv
# Activate the environment with the command for your operating system.
python -m pip install -e .
python -m pokemon_bot.launcher
```

For unattended startup, copy `.env.example` to `.env`, enter your own Official Agent Key locally, and run one of:

```bash
python -m agent --match
python -m agent --tournament
python -m agent --match --tournament
python -m agent --check-tournament
```

Never upload `.env` or your key. The packaged source contains no key.

## Strategy

- Draft: evaluate fixed sets, complementary coverage, physical/special balance, Intimidate, Fake Out, redirection, speed control, weather, Trick Room, Item Clause and short snake-draft opponent-response forecasts. Opponent denial is valued alongside team improvement.
- Preview: evaluate all 15 four-Pokémon subsets of six, every lead pair, opponent possible leads, reserve switch-ins and vulnerable matchups. Exact server roster identifiers are preserved.
- Battle: enumerate legal joint actions for both slots, estimate damage and turn ordering, generate plausible opponent joint responses, and evaluate a weighted average plus worst-response component. Selected candidates receive a limited second-turn attack continuation, so setup and positioning can earn future value. This supports focused KOs, priority, Protect, Fake Out, Tailwind, Trick Room, spread attacks, ally damage, redirection, status and switches.
- Timing: decisions run locally, with bounded candidate/response counts. No remote inference is on the move path.
- Reliability: legal templates are validated before sending; forced switches, one-reserve/two-faints, target coordinates and stale version handling use the official SDK. Match memory is isolated; repeated observations reuse decisions.

The battle model is an approximation, not a complete replacement for Pokémon Showdown. It searches a limited candidate set and a limited set of likely responses. Its second turn considers a small set of attacks, without searching all subsequent protection, setup or voluntary switching. It is not an exact minimax solver or a trained world-champion agent. Unknown opponent facts remain estimates. Public fixed sets observed during draft may be remembered for that match. No spectator or administrative information is read.

There is no Terastallization action in this platform. The bot does not invent one.

## Existing Red Alert installation

Do not run an older all-games Red Alert process and this process on the same Pokémon seats. In a source installation of the existing Red Alert bot, copy the `pokemon_bot/` directory beside `altru_redalert/`, set `REDALERT_OTHER_AGENT=pokemon_bot.agent`, and keep using the Red Alert entry point. Its existing dispatcher will delegate Pokémon to this module. This configuration is intended for Red Alert plus Pokémon; this module does not play Werewolf. A previously frozen Red Alert EXE must be rebuilt to include the module; copying files next to that EXE is not sufficient.

The standalone package supplied here does not change the existing Red Alert repository or executable.

## Validation and reproducibility

See `VALIDATION.md` for measured results and limitations. Scenario and protocol tests use pytest. The separate local benchmark uses the real Pokémon Showdown engine; that engine is needed only for development, not for playing on the platform.

```bash
python -m pip install -e '.[dev]'
python -m pytest tests -q
python -m pokemon_bot.launcher --self-test
```

## Sources and third-party components

- Official starter SDK: https://github.com/UCLA-Trustworthy-AI-Lab/altruagent-starter
- Official public Pokémon interface guide, retrieved 2026-10-15: https://platform.altruagent-game.com/skill/pokemon
- Static species/move/type/nature data: `pokemon-showdown@0.11.10`, https://github.com/smogon/pokemon-showdown (MIT notice in `POKEMON_SHOWDOWN_LICENSE`).

The full SDK is included, with a Pokémon-only assignment filter added in `altruagent/supervisor.py`. The default `agent/agent.py` delegates to this strategy. Third-party comments and notices are retained. Authored strategy code is supplied without comments or docstrings.
