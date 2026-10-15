const fs = require('fs');
const path = require('path');
const {Dex} = require(process.env.SHOWDOWN_PATH || '../../engine/node_modules/pokemon-showdown');
const out = {source:'pokemon-showdown@0.11.10', species:{}, moves:{}, typechart:{}, natures:{}};
const support = ['fakeout','tailwind','trickroom','spore','followme','ragepowder','partingshot','wideguard','helpinghand','willowisp','thunderwave','taunt','nastyplot','swordsdance'];
const banned = new Set(['explosion','selfdestruct','mistyexplosion','steelbeam','mindblown','gigaimpact','hyperbeam','blastburn','hydrocannon','frenzyplant','rockwrecker','roaroftime','prismaticlaser','eternabeam','meteorassault','focuspunch','lastresort','snore','dreameater','belch','burnup','double shock','doubleshock','burningjealousy','futuresight','doomdesire']);
for (const p of Dex.species.all()) {
 if (!p.exists || p.gen > 9) continue;
 const learns = new Set();
 try {for(const entry of Dex.species.getFullLearnset(p.id)) for (const [id,sources] of Object.entries(entry.learnset||{})) if(sources.some(s=>s.startsWith('9'))) learns.add(id);} catch{}
 const damage = [...learns].map(id=>Dex.moves.get(id)).filter(m=>m.exists&&m.category!=='Status'&&m.basePower>0&&!banned.has(m.id)&&!m.flags.charge&&!m.flags.recharge);
 const score = m => {
  let power=m.basePower*(typeof m.multihit==='number'?m.multihit:1);
  let a=m.accuracy===true?1:m.accuracy/100;
  if(m.willCrit) power*=1.5;
  if(m.recoil)power*=.87;
  if(m.id==='acrobatics')power*=1.2;
  const atk=m.category==='Physical'?p.baseStats.atk:p.baseStats.spa;
  return power*a*atk*(m.priority>0?1.12:1);
 };
 damage.sort((a,b)=>score(b)-score(a));
 const picks=[];
 const add=id=>{if(id&&!picks.includes(id))picks.push(id);};
 for(const type of p.types)add(damage.find(m=>m.type===type)?.id);
 const special={archaludon:['bodypress','electroshot'],rillaboom:['grassyglide'],kingambit:['suckerpunch'],chienpao:['suckerpunch','icespinner'],ragingbolt:['thunderclap'],dragonite:['extremespeed'],ursaluna:['facade'],ursalunabloodmoon:['bloodmoon'],ogerponwellspring:['ivycudgel'],ogerponhearthflame:['ivycudgel']};
 for(const id of special[p.id]||[])if(learns.has(id))add(id);
 const types=new Set(p.types);
 for(const m of damage)if(!types.has(m.type)){add(m.id);types.add(m.type);if(picks.length>=4)break;}
 for(const id of support)if(learns.has(id)){add(id);if(picks.length>=7)break;}
 if(learns.has('protect'))add('protect');
 out.species[p.id]={name:p.name,types:p.types,baseStats:p.baseStats,abilities:p.abilities,weightkg:p.weightkg,threat_moves:picks.slice(0,8)};
}
for(const m of Dex.moves.all())if(m.exists&&m.gen<=9)out.moves[m.id]=JSON.parse(JSON.stringify(m));
for(const t of Dex.types.all())out.typechart[t.name.toLowerCase()]=t.damageTaken;
for(const n of Dex.natures.all())out.natures[n.id]={plus:n.plus,minus:n.minus};
fs.writeFileSync(path.resolve(__dirname,'../pokemon_bot/dex_data.json'),JSON.stringify(out));
console.log(Object.keys(out.species).length,Object.keys(out.moves).length);
