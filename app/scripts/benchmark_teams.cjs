'use strict';

const s = (species, item, ability, nature, evs, moves, ivs = {}) => ({
  species, item, ability, nature, evs, moves, ivs, level: 50,
});

module.exports = [
  {name: 'balance', team: [
    s('Incineroar', 'Safety Goggles', 'Intimidate', 'Careful', {hp:252,def:100,spd:156}, ['Fake Out','Flare Blitz','Knock Off','Parting Shot']),
    s('Rillaboom', 'Assault Vest', 'Grassy Surge', 'Adamant', {hp:252,atk:196,spd:60}, ['Fake Out','Grassy Glide','Wood Hammer','U-turn']),
    s('Urshifu-Rapid-Strike', 'Mystic Water', 'Unseen Fist', 'Adamant', {hp:4,atk:252,spe:252}, ['Surging Strikes','Close Combat','Aqua Jet','Protect']),
    s('Flutter Mane', 'Choice Specs', 'Protosynthesis', 'Timid', {hp:4,spa:252,spe:252}, ['Moonblast','Dazzling Gleam','Shadow Ball','Thunderbolt']),
    s('Tornadus', 'Covert Cloak', 'Prankster', 'Timid', {hp:252,spa:4,spe:252}, ['Tailwind','Bleakwind Storm','Rain Dance','Taunt']),
    s('Amoonguss', 'Rocky Helmet', 'Regenerator', 'Relaxed', {hp:252,def:156,spd:100}, ['Spore','Rage Powder','Pollen Puff','Protect'], {spe:0}),
  ]},
  {name: 'rain', team: [
    s('Pelipper', 'Focus Sash', 'Drizzle', 'Modest', {hp:4,spa:252,spe:252}, ['Weather Ball','Hurricane','Tailwind','Protect']),
    s('Archaludon', 'Assault Vest', 'Stamina', 'Modest', {hp:252,spa:156,spd:100}, ['Electro Shot','Draco Meteor','Flash Cannon','Body Press']),
    s('Urshifu-Rapid-Strike', 'Choice Scarf', 'Unseen Fist', 'Adamant', {hp:4,atk:252,spe:252}, ['Surging Strikes','Close Combat','Aqua Jet','U-turn']),
    s('Rillaboom', 'Miracle Seed', 'Grassy Surge', 'Adamant', {hp:252,atk:196,spd:60}, ['Fake Out','Grassy Glide','Wood Hammer','Protect']),
    s('Incineroar', 'Safety Goggles', 'Intimidate', 'Careful', {hp:252,def:100,spd:156}, ['Fake Out','Flare Blitz','Knock Off','Parting Shot']),
    s('Gholdengo', 'Life Orb', 'Good as Gold', 'Modest', {hp:252,spa:252,spd:4}, ['Make It Rain','Shadow Ball','Nasty Plot','Protect']),
  ]},
  {name: 'trick_room', team: [
    s('Farigiraf', 'Mental Herb', 'Armor Tail', 'Quiet', {hp:252,def:156,spa:100}, ['Trick Room','Psychic','Dazzling Gleam','Helping Hand'], {atk:0,spe:0}),
    s('Ursaluna-Bloodmoon', 'Life Orb', "Mind's Eye", 'Quiet', {hp:252,spa:252,spd:4}, ['Blood Moon','Hyper Voice','Earth Power','Protect'], {atk:0,spe:0}),
    s('Torkoal', 'Charcoal', 'Drought', 'Quiet', {hp:252,spa:252,spd:4}, ['Eruption','Heat Wave','Earth Power','Protect'], {atk:0,spe:0}),
    s('Indeedee-F', 'Psychic Seed', 'Psychic Surge', 'Relaxed', {hp:252,def:252,spd:4}, ['Follow Me','Helping Hand','Psychic','Trick Room'], {atk:0,spe:0}),
    s('Amoonguss', 'Sitrus Berry', 'Regenerator', 'Relaxed', {hp:252,def:156,spd:100}, ['Spore','Rage Powder','Pollen Puff','Protect'], {spe:0}),
    s('Lilligant-Hisui', 'Focus Sash', 'Chlorophyll', 'Jolly', {atk:252,def:4,spe:252}, ['Sleep Powder','After You','Solar Blade','Close Combat']),
  ]},
  {name: 'offense', team: [
    s('Chien-Pao', 'Focus Sash', 'Sword of Ruin', 'Jolly', {atk:252,spd:4,spe:252}, ['Ice Spinner','Sucker Punch','Sacred Sword','Protect']),
    s('Dragonite', 'Choice Band', 'Inner Focus', 'Adamant', {hp:4,atk:252,spe:252}, ['Extreme Speed','Outrage','Stomping Tantrum','Ice Spinner']),
    s('Flutter Mane', 'Booster Energy', 'Protosynthesis', 'Timid', {hp:4,spa:252,spe:252}, ['Moonblast','Dazzling Gleam','Shadow Ball','Protect']),
    s('Chi-Yu', 'Choice Specs', 'Beads of Ruin', 'Timid', {hp:4,spa:252,spe:252}, ['Heat Wave','Overheat','Dark Pulse','Snarl']),
    s('Ogerpon-Wellspring', 'Wellspring Mask', 'Water Absorb', 'Jolly', {hp:4,atk:252,spe:252}, ['Ivy Cudgel','Horn Leech','Follow Me','Spiky Shield']),
    s('Landorus-Therian', 'Choice Scarf', 'Intimidate', 'Adamant', {hp:4,atk:252,spe:252}, ['Stomping Tantrum','Rock Slide','U-turn','Tera Blast']),
  ]},
];
