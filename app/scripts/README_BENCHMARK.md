# Local Showdown benchmark

`benchmark_showdown.cjs` runs real Pokémon Showdown battles. Damage, speed order,
accuracy, status, ability activation, switching, knockouts, and winners are decided
by Showdown, independently of the Python bot's evaluation model.

Install the Python project dependencies and Node.js, then install the optional
benchmark engine outside the bot directory:

```bash
npm install --prefix ../engine pokemon-showdown@0.11.10
node scripts/benchmark_showdown.cjs --games 24 --output scripts/benchmark_results.json
node scripts/benchmark_showdown.cjs --games 24 --seed-offset 19000 --output scripts/benchmark_holdout.json
```

`SHOWDOWN_PATH` can point to another `pokemon-showdown` package directory, and
`PYTHON` selects the Python executable. In this development workspace, Python
dependencies are under `/workspace/scratch/a026a43a1c2c/deps`, so the run also needs
that directory in `PYTHONPATH`.

The engine is version 0.11.10, whose format catalog does **not** contain
`gen9vgc2025regi`. The harness therefore uses Gen 9 Doubles Custom Game with six
Pokémon at preview, four selected for battle, two active slots, level 50 sets,
and no Terastallization choices. This checks battle mechanics and the documented
action contract, not the live platform's exact installed regulation or connection.

Four hand-authored representative teams cover balance, rain, Trick Room, and
offense. They are not claimed to reproduce the platform's current draft pool.
The harness tests preview and battle decisions; it does not benchmark draft play.
Team pairings, engine seeds, and the bot's seat rotate. Each pair is repeated with
seats reversed. Such paired games are correlated, not independent win-rate trials.

Two intentionally limited opponents are included:

- `greedy_damage` independently scores approximate immediate damage and a small
  Fake Out bonus, brings the first four roster entries, and generally does not
  switch voluntarily. It does not search adversarial responses or optimize support
  combinations. Its damage score is written in JavaScript, without importing the
  tested bot's damage or search functions.
- `random_legal` samples uniformly from enumerated legal joint actions and
  randomizes its preview. It is a weak legality baseline and may target allies.

The adapter sends only own private information and opponent public information to
the Python subprocess. Both drafted sets are treated as preannounced. Opponent
HP is rounded to percent, bench HP is retained from the last visible observation,
and the opponent's hidden chosen four, move PP, choice locks, sleep counters,
actions, and engine RNG state are not sent. The full engine log is saved only
after adjudication for debugging; the bot does not receive it.

The complete-public-set assumption does not test joining after an opponent has
already drafted an unseen card or restoring an agent midway through a battle
without its draft memory. Those cases need separate missing-information tests.

Each output records outcomes, complete engine logs, action traces, rejected
commands, exceptions, fallback warnings, forced-switch decisions, and Python
decision latency. An invalid command is counted before an engine-default
fallback continues the battle. The report includes hashes of all bot modules
and checks that their source did not change during the run. A final validation
must use a fresh Python process after source changes are frozen.

These results are local engineering evidence against limited baselines, **not a
platform win-rate estimate or evidence that the bot is unbeatable**. Reusing
development seeds after tuning is not a holdout evaluation; use a fresh seed
offset for a final run and preserve the result.

## Development benchmark v0, 2026-10-15

The first frozen run is archived as `DEVELOPMENT_v0_validation_results.json`.
Its failures are now being used for further development, so it is no longer a
final holdout evaluation. Earlier runs are also explicitly development-only.
The v0 run used:

```bash
node scripts/benchmark_showdown.cjs --games 24 --seed-offset 10000 --start-index 24 --output scripts/DEVELOPMENT_v0_validation_results.json
```

All six recorded policy/data hashes remained unchanged during this run.

| Opponent | Games | Wins | Losses | Paired scenarios |
|---|---:|---:|---:|---:|
| Approximate greedy damage | 16 | 9 | 7 | 8 |
| Random legal actions | 8 | 8 | 0 | 4 |

There were 183 bot decisions, including 33 forced-switch decisions, with zero
rejected bot commands, rejected baseline commands, bridge exceptions, or logged
evaluation fallbacks. Python decision latency was median 0.076 seconds, 95th
percentile 0.573 seconds, and maximum 0.912 seconds. Games took 4–7 turns.

Against the greedy baseline, four paired scenarios were won from both seats,
one split, and three were lost from both seats. The three complete losses were
Trick Room versus offense, rain versus offense, and Trick Room versus balance.
The split was the offense mirror. This is useful evidence of remaining strategy
weaknesses; the agent is not established as dominant against stronger opponents.

The candidate was compared on these same development cases without changing
the harness or opponents. The next final validation was predeclared as 24 games
with `--start-index 0 --seed-offset 25000`, using a fresh Python process after
the candidate was selected and frozen.

## Development candidate selection

`development_v1_results.json` reruns the same 24 cases with the same harness,
opponents, and seeds. The candidate won 18 games: 10/16 against greedy damage and
8/8 against random legal actions, compared with v0's 17 total and 9/16 against
greedy damage. Both seats of rain-versus-offense and Trick-Room-versus-balance
improved from losses to wins. Both seats of balance-versus-rain and one seat of
the offense mirror regressed from wins to losses. This is a development
comparison after inspecting failures, not an independent win-rate estimate.

Candidate v1 was selected, with only targeted correctness fixes to last-PP and
forced-switch transition handling permitted before the predeclared final run.
The development candidate had zero rejected actions, bridge exceptions, or
evaluation fallbacks across 163 bot decisions. Maximum measured decision latency
was 1.027 seconds. The final run below is authoritative for the
shipped source; earlier runs are retained as development evidence.

## Final predeclared validation, 2026-10-15

`FINAL_validation_results.json` contains the final 24-game run, with all engine
logs and decision traces. The final command was:

```bash
node scripts/benchmark_showdown.cjs --games 24 --seed-offset 25000 --start-index 0 --output scripts/FINAL_validation_results.json
```

The engine, scenarios, and opponents were unchanged. This run used fresh seeds
after policy selection, and all six policy/data hashes remained unchanged
throughout it. There was no further strategic tuning after these results.

| Opponent | Games | Wins | Losses | Paired scenarios |
|---|---:|---:|---:|---:|
| Approximate greedy damage | 16 | 10 | 6 | 8 |
| Random legal actions | 8 | 8 | 0 | 4 |
| Total | 24 | 18 | 6 | 12 |

There were 161 bot decisions, including 22 forced-switch decisions, with zero
rejected bot commands, rejected baseline commands, bridge exceptions, or logged
evaluation fallbacks. Python decision latency was median 0.245 seconds, 95th
percentile 0.685 seconds, and maximum 0.973 seconds. Maximum cumulative measured
Python thinking time in one game was 4.211 seconds. These are measurements on
the development machine, not native Windows or network latency measurements.
Games lasted 3–7 turns.

Five of the eight greedy-opponent scenarios were won from both seats; three were
lost from both seats: balance-versus-rain, Trick-Room-versus-balance, and
offense-versus-rain. All four random-opponent scenarios were won from both seats.
The paired outcomes are correlated. The complete-public-set assumption, lack of
draft testing, approximate opponent strength, and custom format limitations
above still apply. These results establish a functioning, fast local battle
agent with remaining strategic weaknesses; they do not establish a live
platform win rate or dominance over strong competition.

Final `battle.py` SHA-256:
`119d5f64ba2d6735874aa32ab3cc6ddffd423fbc6c04667a8fb6915d9aee0b2b`.
All six full hashes are recorded in the JSON result.
