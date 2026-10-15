import time

from altruagent.models import LegalAction
from pokemon_bot.draft import choose_draft, choose_lineup


def mon(species, moves, item="", ability="", **extra):
    return {"species": species, "card_id": "vgc-" + species.lower().replace(" ", "-"), "moves": moves, "item": item, "ability": ability, "level": 50, **extra}


def actions(cards):
    return [LegalAction("draft_pick:" + card["card_id"], card["species"], {"action": {"type": "draft_pick", "card_id": card["card_id"]}}) for card in cards]


def test_draft_uses_legal_action_and_actual_set_strength():
    cards = [
        mon("Magikarp", ["Splash", "Tackle"], "Oran Berry", "Swift Swim"),
        mon("Calyrex-Shadow", ["Astral Barrage", "Psychic", "Draining Kiss", "Protect"], "Focus Sash", "As One (Spectrier)", evs={"spa": 252, "spe": 252}),
        mon("Unown", ["Hidden Power"], "Choice Specs", "Levitate"),
    ]
    legal = actions(cards)
    memory = {}
    result = choose_draft({"available_cards": cards, "rosters": {"a": [], "b": []}, "current_seat": "a", "first_drafter": "a"}, legal, memory, "a")
    assert result is legal[1]
    assert "calyrexshadow" in memory["sets"]
    assert memory["draft_scores"][0]["card_id"] == cards[1]["card_id"]


def test_draft_does_not_select_unoffered_strong_card():
    cards = [mon("Calyrex-Shadow", ["Astral Barrage"], "Focus Sash"), mon("Pikachu", ["Thunderbolt"], "Light Ball")]
    legal = actions(cards[1:])
    result = choose_draft({"available_cards": cards, "rosters": {"a": [], "b": []}, "current_seat": "a", "first_drafter": "a"}, legal, {}, "a")
    assert result is legal[0]


def test_snake_forecast_respects_item_clause_and_picked_cards():
    selected = mon("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"], "Sitrus Berry", "Intimidate")
    cards = [
        mon("Calyrex-Shadow", ["Astral Barrage", "Psychic", "Protect", "Nasty Plot"], "Focus Sash"),
        mon("Flutter Mane", ["Moonblast", "Shadow Ball", "Dazzling Gleam", "Protect"], "Focus Sash"),
        mon("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "U-turn"], "Assault Vest", "Grassy Surge"),
        mon("Tornadus", ["Bleakwind Storm", "Tailwind", "Taunt", "Protect"], "Covert Cloak", "Prankster"),
    ]
    memory = {"sets": {"incineroar": selected}, "draft_cards": {selected["card_id"]: selected}}
    observation = {"available_cards": cards, "rosters": {"a": [selected], "b": []}, "current_seat": "b", "first_drafter": "a"}
    choose_draft(observation, actions(cards), memory, "b")
    items = {card["card_id"]: card["item"] for card in cards + [selected]}
    for candidate in memory["draft_scores"]:
        own = {items[candidate["card_id"]]}
        opponent = {"Sitrus Berry"}
        for pick in candidate["forecast"]:
            seen = own if pick["side"] == "own" else opponent
            assert items[pick["card_id"]] not in seen
            seen.add(items[pick["card_id"]])
            assert pick["card_id"] != selected["card_id"]


def test_lineup_has_four_unique_pokemon_and_two_valid_leads():
    roster = [
        mon("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"], "Sitrus Berry", "Intimidate"),
        mon("Flutter Mane", ["Moonblast", "Shadow Ball", "Dazzling Gleam", "Protect"], "Focus Sash", "Protosynthesis"),
        mon("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "U-turn"], "Assault Vest", "Grassy Surge"),
        mon("Tornadus", ["Bleakwind Storm", "Tailwind", "Taunt", "Protect"], "Covert Cloak", "Prankster"),
        mon("Magikarp", ["Splash", "Tackle"], "Oran Berry", "Swift Swim"),
        mon("Unown", ["Hidden Power"], "Choice Specs", "Levitate"),
    ]
    memory = {}
    result = choose_lineup({"your_roster": roster, "opponent_roster": [mon("Garchomp", ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"], "Life Orb", "Rough Skin"), mon("Urshifu-Rapid-Strike", ["Surging Strikes", "Close Combat", "Aqua Jet", "Protect"], "Mystic Water", "Unseen Fist")]}, {}, memory)
    assert result["type"] == "select_lineup"
    assert len(set(result["bring"])) == 4
    assert len(set(result["leads"])) == 2
    assert set(result["leads"]) <= set(result["bring"])
    assert "magikarp" not in result["bring"]
    assert "unown" not in result["bring"]
    assert memory["lineup_analysis"]


def test_lineup_uses_draft_memory_for_preview_hidden_sets():
    cards = [
        mon("Kyogre", ["Water Spout", "Origin Pulse", "Ice Beam", "Thunder"], "Choice Scarf", "Drizzle"),
        mon("Tornadus", ["Bleakwind Storm", "Tailwind", "Taunt", "Protect"], "Covert Cloak", "Prankster"),
        mon("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"], "Sitrus Berry", "Intimidate"),
        mon("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "U-turn"], "Assault Vest", "Grassy Surge"),
        mon("Magikarp", ["Splash", "Tackle"], "Oran Berry", "Swift Swim"),
        mon("Unown", ["Hidden Power"], "Choice Specs", "Levitate"),
    ]
    from pokemon_bot.dex import norm

    memory = {"sets": {norm(card["species"]): card for card in cards}}
    roster = [norm(card["species"]) for card in cards]
    result = choose_lineup({}, {"roster": roster}, memory)
    assert "kyogre" in result["bring"]
    assert "tornadus" in result["bring"]
    assert "magikarp" not in result["bring"]
    assert "unown" not in result["bring"]


def test_lineup_returns_exact_template_spelling():
    roster = ["Incineroar", "Flutter Mane", "Rillaboom", "Urshifu-Rapid-Strike", "Tornadus", "Amoonguss"]
    result = choose_lineup({"your_roster": [{"species": entry.lower().replace("-", "").replace(" ", "")} for entry in roster]}, {"roster": roster}, {})
    assert len(result["bring"]) == 4
    assert set(result["bring"]) <= set(roster)
    assert set(result["leads"]) <= set(result["bring"])


def test_draft_full_pool_meets_clock_budget():
    specs = [
        ("Incineroar", ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"], "Sitrus Berry", "Intimidate"),
        ("Flutter Mane", ["Moonblast", "Shadow Ball", "Dazzling Gleam", "Protect"], "Focus Sash", "Protosynthesis"),
        ("Rillaboom", ["Fake Out", "Grassy Glide", "Wood Hammer", "U-turn"], "Assault Vest", "Grassy Surge"),
        ("Tornadus", ["Bleakwind Storm", "Tailwind", "Taunt", "Protect"], "Covert Cloak", "Prankster"),
        ("Urshifu-Rapid-Strike", ["Surging Strikes", "Close Combat", "Aqua Jet", "Protect"], "Mystic Water", "Unseen Fist"),
        ("Amoonguss", ["Spore", "Rage Powder", "Pollen Puff", "Protect"], "Rocky Helmet", "Regenerator"),
        ("Gholdengo", ["Make It Rain", "Shadow Ball", "Nasty Plot", "Protect"], "Life Orb", "Good as Gold"),
        ("Chien-Pao", ["Ice Spinner", "Sucker Punch", "Sacred Sword", "Protect"], "Focus Sash", "Sword of Ruin"),
        ("Landorus-Therian", ["Stomping Tantrum", "Rock Slide", "U-turn", "Tera Blast"], "Choice Scarf", "Intimidate"),
        ("Iron Hands", ["Fake Out", "Drain Punch", "Wild Charge", "Volt Switch"], "Assault Vest", "Quark Drive"),
        ("Raging Bolt", ["Thunderclap", "Dragon Pulse", "Calm Mind", "Protect"], "Leftovers", "Protosynthesis"),
        ("Farigiraf", ["Trick Room", "Psychic", "Dazzling Gleam", "Helping Hand"], "Safety Goggles", "Armor Tail"),
        ("Kyogre", ["Water Spout", "Origin Pulse", "Ice Beam", "Thunder"], "Choice Scarf", "Drizzle"),
        ("Calyrex-Ice", ["Glacial Lance", "High Horsepower", "Trick Room", "Protect"], "Clear Amulet", "As One (Glastrier)"),
        ("Pelipper", ["Weather Ball", "Hurricane", "Wide Guard", "Tailwind"], "Damp Rock", "Drizzle"),
        ("Ursaluna", ["Facade", "Headlong Rush", "Earthquake", "Protect"], "Flame Orb", "Guts"),
        ("Indeedee-F", ["Follow Me", "Helping Hand", "Psychic", "Trick Room"], "Psychic Seed", "Psychic Surge"),
        ("Hatterene", ["Trick Room", "Expanding Force", "Dazzling Gleam", "Protect"], "Life Orb", "Magic Bounce"),
    ]
    cards = [mon(*spec) for spec in specs]
    observation = {"available_cards": cards, "rosters": {"a": [], "b": []}, "current_seat": "a", "first_drafter": "a"}
    legal = actions(cards)
    start = time.perf_counter()
    result = choose_draft(observation, legal, {}, "a")
    elapsed = time.perf_counter() - start
    assert result in legal
    assert elapsed < 2.0
