#!/usr/bin/env node
'use strict';

// Real engine benchmark. Engine internals are used only by the adapter; the
// decision subprocess sees the same restricted observation schema as the guide.
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const {spawn} = require('child_process');
const {createHash} = require('crypto');
const enginePath = process.env.SHOWDOWN_PATH || path.resolve(__dirname, '../../engine/node_modules/pokemon-showdown');
const {Battle, Dex, toID} = require(enginePath);
const teams = require('./benchmark_teams.cjs');
const args = process.argv.slice(2);
const argument = (name, fallback) => { const i = args.indexOf(name); return i < 0 ? fallback : args[i+1]; };
const gameCount = Number(argument('--games', 24));
const seedOffset = Number(argument('--seed-offset', 0));
const startIndex = Number(argument('--start-index', 0));
const output = path.resolve(argument('--output', path.join(__dirname, 'benchmark_results.json')));
const engineFormat = 'gen9doublescustomgame@@@!!Max Team Size=6,Picked Team Size=4';
const targeted = new Set(['normal','adjacentFoe','adjacentAlly','adjacentAllyOrSelf','any']);
const copy = value => JSON.parse(JSON.stringify(value));

class PythonAgent {
  constructor() {
    this.child = spawn(process.env.PYTHON || 'python', [path.join(__dirname,'benchmark_bridge.py')], {stdio:['pipe','pipe','inherit']});
    this.waiters = [];
    readline.createInterface({input:this.child.stdout}).on('line', line => {
      const next = this.waiters.shift();
      if (!next) throw new Error(`Unexpected Python output: ${line}`);
      try { next.resolve(JSON.parse(line)); } catch (error) { next.reject(error); }
    });
    this.child.on('exit', code => {for (const waiter of this.waiters.splice(0)) waiter.reject(new Error(`Python bridge exited ${code}`));});
    this.child.stdin.on('error', error => {for (const waiter of this.waiters.splice(0)) waiter.reject(error);});
  }
  send(message) {
    return new Promise((resolve,reject) => {
      const timer=setTimeout(()=>reject(new Error('Python decision exceeded 45 seconds')),45000);
      this.waiters.push({resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});
      this.child.stdin.write(JSON.stringify(message)+'\n');
    });
  }
  close() { this.child.stdin.end(); }
}

function moveDescription(id, pp) {
  const move=Dex.moves.get(id);
  return {id:move.id,move_id:move.id,name:move.name,type:move.type.toUpperCase(),move_type:move.type.toUpperCase(),
    category:move.category.toUpperCase(),base_power:move.basePower,accuracy:move.accuracy===true?1:move.accuracy/100,
    priority:move.priority,current_pp:pp===undefined?Math.floor(move.pp*1.6):pp,max_pp:Math.floor(move.pp*1.6),target:move.target};
}

function rosterSummary(set) {
  const species=Dex.species.get(set.species);
  return {...copy(set),species:species.id,name:species.name,types:species.types.map(x=>x.toUpperCase()),
    base_stats:copy(species.baseStats),current_hp:null,max_hp:null,current_hp_fraction:1,
    item:toID(set.item),ability:toID(set.ability),moves:Object.fromEntries(set.moves.map(id=>[toID(id),moveDescription(id)])),
    boosts:{},status:null,fainted:false,active:false,revealed:false,is_terastallized:false};
}

class ObservationAdapter {
  constructor(battle, allTeams, session) {
    this.battle=battle; this.allTeams=allTeams; this.session=session; this.version=[0,0];
    this.lastSeen=allTeams.map(team=>Object.fromEntries(team.map(set=>[toID(set.species),rosterSummary(set)])));
  }
  summary(pokemon, owner, own=false) {
    if (!pokemon) return null;
    const id=pokemon.baseSpecies.id;
    const previous=this.lastSeen[owner][id] || rosterSummary(pokemon.set);
    const summary={...copy(previous),species:pokemon.species.id,name:pokemon.species.name,
      types:pokemon.getTypes().map(x=>x.toUpperCase()),base_stats:copy(pokemon.species.baseStats),
      current_hp:own?pokemon.hp:Math.ceil(100*pokemon.hp/pokemon.maxhp),max_hp:own?pokemon.maxhp:100,
      current_hp_fraction:own?pokemon.hp/pokemon.maxhp:Math.ceil(100*pokemon.hp/pokemon.maxhp)/100,
      status:pokemon.status||null,boosts:copy(pokemon.boosts),fainted:pokemon.fainted,
      active:pokemon.isActive,revealed:true,is_terastallized:false,
      effects:Object.keys(pokemon.volatiles).filter(k=>['substitute','confusion','taunt','encore','yawn','leechseed','perishsong','disable','torment','attract'].includes(k))};
    if (own) {
      summary.item=pokemon.item;summary.ability=pokemon.ability;
      summary.moves=Object.fromEntries(pokemon.moveSlots.map(m=>[m.id,moveDescription(m.id,m.pp)]));
    }
    // Public item removal is observable. Never read an opponent's held item,
    // bench HP, chosen four, move PP, choice lock, sleep counter, or RNG state.
    const names=new Set([pokemon.name,pokemon.species.name]);
    for (const line of this.battle.log) {
      if (!line.startsWith('|-enditem|')) continue;
      const [,,ident]=line.split('|');
      if (ident?.startsWith(`p${owner+1}`) && names.has(ident.split(': ')[1])) summary.item='';
    }
    if (!own) this.lastSeen[owner][id]=copy(summary);
    return summary;
  }
  snapshot(sideIndex) {
    const battle=this.battle, side=battle.sides[sideIndex], foe=battle.sides[1-sideIndex], request=side.activeRequest;
    const version=++this.version[sideIndex];
    let phase, observation, template;
    if (request.teamPreview) {
      phase='team_preview';
      observation={phase,battle_format:'gen9vgc2025regi',waiting_for_action:true,
        your_roster:this.allTeams[sideIndex].map(rosterSummary),opponent_roster:this.allTeams[1-sideIndex].map(rosterSummary)};
      template={type:'select_lineup',roster:this.allTeams[sideIndex].map(s=>toID(s.species)),bring_count:4,lead_count:2};
    } else {
      phase='moving';
      const own=side.active.map(p=>this.summary(p,sideIndex,true));
      const opponents=foe.active.map(p=>this.summary(p,1-sideIndex,false));
      for (const entry of Object.values(this.lastSeen[1-sideIndex])) entry.active=opponents.some(p=>p&&p.species===entry.species&&!p.fainted);
      const reserves=side.pokemon.filter(p=>!p.fainted&&!side.active.includes(p));
      const forced=request.forceSwitch || [false,false];
      const forceCount=forced.filter(Boolean).length;
      const slots=[0,1].map(slot=>{
        const active=side.active[slot], options=[];
        if (request.forceSwitch) {
          if (forced[slot]) for (const p of reserves) options.push({type:'switch',species:p.species.id});
          if (!forced[slot] || reserves.length<forceCount) options.push({type:'pass'});
        } else if (!active || active.fainted) options.push({type:'pass'});
        else {
          const activeRequest=request.active[slot];
          for (const move of activeRequest.moves) {
            if (move.disabled || move.pp===0) continue;
            // Locked attacks omit target from the request. Showdown's choice
            // parser treats that missing value as normal before lock handling.
            const targetType=move.target || 'normal';
            const targets=targeted.has(targetType)?[-1,-2,1,2].filter(loc=>{
              const target=loc>0?foe.active[loc-1]:side.active[-loc-1];
              return target && !target.fainted && battle.validTargetLoc(loc,active,targetType);
            }):[0];
            if (targets.length) options.push({...moveDescription(move.id,move.pp),type:'move',target:targetType,targets});
          }
          if (!activeRequest.trapped) for (const p of reserves) options.push({type:'switch',species:p.species.id});
        }
        return {slot,board_position:-slot-1,active:own[slot],force_switch:!!forced[slot],options};
      });
      template={type:'doubles_turn',slots,target_legend:{1:'Opponent A',2:'Opponent B','-1':'Own A','-2':'Own B',0:'No target'}};
      observation={phase,turn:battle.turn,format:'gen9vgc2025regi',battle_format:'gen9vgc2025regi',is_doubles:true,
        waiting_for_action:true,active_pokemon:own,opponent_active_pokemon:opponents,
        team:Object.fromEntries(side.pokemon.map(p=>[p.fullname,this.summary(p,sideIndex,true)])),
        opponent_team:Object.fromEntries(Object.values(this.lastSeen[1-sideIndex]).map(p=>[`p${2-sideIndex}: ${p.name}`,copy(p)])),
        force_switch:forced,available_moves:slots.map(s=>s.options.filter(o=>o.type==='move')),
        available_switches:slots.map(s=>s.options.filter(o=>o.type==='switch').map(o=>this.summary(side.pokemon.find(p=>p.species.id===o.species),sideIndex,true))),
        weather:battle.field.weather?{[battle.field.weather]:{}}:{},
        fields:{...(battle.field.terrain?{[battle.field.terrain]:{}}:{}),...Object.fromEntries(Object.keys(battle.field.pseudoWeather).map(k=>[k,{}]))},
        side_conditions:Object.fromEntries(Object.keys(side.sideConditions).map(k=>[k,{}])),
        opponent_side_conditions:Object.fromEntries(Object.keys(foe.sideConditions).map(k=>[k,{}])),
        clock:{decision_seconds_left:50,bank_seconds_left:420}};
    }
    return {state:{session_id:this.session,game_type:'pokemon_vgc_doubles_draft',runtime_adapter:'pokemon',status:'in_progress',
      state_version:version,phase,observation,is_terminal:false,is_current_actor:true,current_actor:{agent_id:'benchmark-bot',position:sideIndex},
      legal_actions:{session_id:this.session,state_version:version,actions:[{action_id:template.type,label:template.type,
        input:{session_id:this.session,state_version:version,action_id:template.type,action:template}}]}},template};
  }
}

function expanded(options) {
  return options.flatMap(o=>o.type==='move'?o.targets.map(target=>({type:'move',move_id:o.move_id,target})): [{type:o.type,...(o.species?{species:o.species}:{})}]);
}
function legalPairs(template) {
  const result=[];
  for (const a of expanded(template.slots[0].options)) for (const b of expanded(template.slots[1].options)) {
    if (a.type==='pass'&&b.type==='pass') continue;
    if (a.type==='switch'&&b.type==='switch'&&a.species===b.species) continue;
    const forced=template.slots.filter(s=>s.force_switch).length;
    const reserves=new Set(template.slots.flatMap(s=>s.options.filter(o=>o.type==='switch').map(o=>o.species))).size;
    if (forced && [a,b].filter(x=>x.type==='switch').length!==Math.min(forced,reserves)) continue;
    result.push({type:'doubles_turn',slot_0:a,slot_1:b});
  }
  return result;
}
function convert(action, side) {
  if (action.type==='select_lineup') {
    const ordering=[...action.leads,...action.bring.filter(x=>!action.leads.includes(x))];
    return 'team '+ordering.map(id=>side.pokemon.findIndex(p=>p.species.id===toID(id))+1).join('');
  }
  return [0,1].map(i=>{
    const a=action[`slot_${i}`];
    if (a.type==='pass') return 'pass';
    if (a.type==='switch') return 'switch '+(side.pokemon.findIndex(p=>p.species.id===toID(a.species))+1);
    return `move ${a.move_id}${a.target?' '+a.target:''}`;
  }).join(', ');
}
function rng(seed) {let value=seed|0;return ()=>{value^=value<<13;value^=value>>>17;value^=value<<5;return (value>>>0)/4294967296;};}
function stat(p, name) {
  const base=p.base_stats[name], iv=p.ivs?.[name]??31, ev=p.evs?.[name]??0;
  const nature=Dex.natures.get(p.nature);
  const modifier=nature.plus===name?1.1:nature.minus===name?0.9:1;
  const stage=p.boosts?.[name]||0;
  return Math.floor((Math.floor((2*base+iv+Math.floor(ev/4))*50/100)+5)*modifier)*(stage>=0?(2+stage)/2:2/(2-stage));
}
function greedyDamage(move, user, target, observation, spread) {
  if (!target || target.fainted || move.category==='Status') return 0;
  let power=move.basePower;
  if (move.id==='fakeout' && !user.firstTurn) return 0;
  if (move.id==='suckerpunch') power*=0.65;
  if (move.id==='surgingstrikes') power*=4.5;
  if (move.id==='weatherball') power=Object.keys(observation.weather).length?100:50;
  if (move.id==='eruption') power=150*user.current_hp_fraction;
  if (move.id==='electroshot') power=observation.weather.raindance?130:65;
  const type=move.id==='weatherball'?(observation.weather.raindance?'Water':observation.weather.sunnyday?'Fire':move.type):move.type;
  let effective=1;
  for (const typeName of target.types) {
    const chart=Dex.types.get(typeName).damageTaken[type];
    if (chart===3) return 0;
    effective*=chart===1?2:chart===2?0.5:1;
  }
  if (type==='Water'&&['waterabsorb','stormdrain','dryskin'].includes(target.ability)) return 0;
  if (type==='Ground'&&target.ability==='levitate') return 0;
  if (type==='Electric'&&['voltabsorb','lightningrod','motordrive'].includes(target.ability)) return 0;
  const physical=move.category==='Physical';
  let attack=stat(user,move.id==='bodypress'?'def':physical?'atk':'spa');
  let defense=stat(target,physical?'def':'spd');
  if (physical&&user.item==='choiceband') attack*=1.5;
  if (!physical&&user.item==='choicespecs') attack*=1.5;
  if (!physical&&target.item==='assaultvest') defense*=1.5;
  let damage=(22*power*attack/defense/50+2)*effective*(user.types.includes(type.toUpperCase())?1.5:1)*(spread?0.75:1);
  if (physical&&user.status==='brn') damage*=0.5;
  if (user.item==='lifeorb') damage*=1.3;
  if (type==='Water'&&observation.weather.raindance || type==='Fire'&&observation.weather.sunnyday) damage*=1.5;
  if (type==='Water'&&observation.weather.sunnyday || type==='Fire'&&observation.weather.raindance) damage*=0.5;
  const maxhp=Math.floor((2*target.base_stats.hp+(target.ivs?.hp??31)+Math.floor((target.evs?.hp??0)/4))/2)+60;
  return Math.min(damage/maxhp,target.current_hp_fraction+0.1);
}
function baseline(snapshot, kind, random, memory) {
  const {template,state}=snapshot, obs=state.observation;
  if (template.type==='select_lineup') {
    const roster=[...template.roster];
    if (kind==='random_legal') for (let i=roster.length-1;i>0;i--) {
      const j=Math.floor(random()*(i+1));[roster[i],roster[j]]=[roster[j],roster[i]];
    }
    return {type:'select_lineup',bring:roster.slice(0,4),leads:roster.slice(0,2)};
  }
  const pairs=legalPairs(template);
  if (kind==='random_legal') return pairs[Math.floor(random()*pairs.length)];
  for (const user of obs.active_pokemon.filter(Boolean)) {
    const last=memory.get(user.species);
    user.firstTurn=!last || last.turn<obs.turn-1 || !last.active;
  }
  let best=pairs[0],bestScore=-Infinity;
  for (const pair of pairs) {
    let total=0;
    for (let slot=0;slot<2;slot++) {
      const a=pair[`slot_${slot}`], user=obs.active_pokemon[slot];
      if (a.type==='pass') continue;
      if (a.type==='switch') {total-=template.slots[slot].force_switch?0:0.25;continue;}
      const move=Dex.moves.get(a.move_id), spread=['allAdjacent','allAdjacentFoes'].includes(move.target);
      if (spread) {
        total+=obs.opponent_active_pokemon.reduce((sum,p)=>sum+greedyDamage(move,user,p,obs,true),0);
        if (move.target==='allAdjacent') total-=greedyDamage(move,user,obs.active_pokemon[1-slot],obs,true);
      } else if (a.target>0) total+=greedyDamage(move,user,obs.opponent_active_pokemon[a.target-1],obs,false);
      else if (a.target<0) total-=greedyDamage(move,user,obs.active_pokemon[-a.target-1],obs,false);
      if (move.id==='fakeout'&&user.firstTurn&&a.target>0&&obs.opponent_active_pokemon[a.target-1]?.types.every(t=>t!=='GHOST')) total+=0.1;
    }
    if (total>bestScore) {best=pair;bestScore=total;}
  }
  for (const p of obs.active_pokemon.filter(Boolean)) memory.set(p.species,{turn:obs.turn,active:true});
  return best;
}

async function playGame(agent,index) {
  const group=Math.floor(index/2),reverse=index%2,botSide=reverse;
  const baselineKind=group%3===2?'random_legal':'greedy_damage';
  const teamA=teams[group%4],teamB=teams[(group+1+Math.floor(group/4))%4];
  const seed=[2701+group+seedOffset,4102+group*7+seedOffset,3701+group*11+seedOffset,701+group*19+seedOffset].map(n=>n%65536);
  const selected=reverse?[teamB,teamA]:[teamA,teamB];
  const battle=new Battle({formatid:engineFormat,seed});
  battle.setPlayer('p1',{name:botSide===0?'Bot':'Baseline',team:copy(selected[0].team)});
  battle.setPlayer('p2',{name:botSide===1?'Bot':'Baseline',team:copy(selected[1].team)});
  const session=`local-benchmark-${index}`;
  const adapter=new ObservationAdapter(battle,selected.map(t=>t.team),session);
  const result={index,baseline:baselineKind,bot_side:botSide,bot_team:teamA.name,opponent_team:teamB.name,seed,
    winner:null,turns:0,decisions:0,latencies_seconds:[],bot_invalid_actions:[],baseline_invalid_actions:[],bridge_errors:[],evaluation_warnings:[],forced_switch_decisions:0};
  const random=rng(9137+group+seedOffset),memory=new Map();
  const traces=[];
  for (let iteration=0;!battle.ended && iteration<400 && battle.turn<=100;iteration++) {
    const decisions=[];
    for (const sideIndex of [0,1]) {
      const side=battle.sides[sideIndex];
      if (!side.activeRequest || side.activeRequest.wait || !side.requestState || side.isChoiceDone()) continue;
      const snapshot=adapter.snapshot(sideIndex);
      let action;
      if (sideIndex===botSide) {
        const reply=await agent.send({state:snapshot.state,seat_position:sideIndex});
        if (reply.error) {result.bridge_errors.push(reply.error);action=baseline(snapshot,'greedy_damage',random,memory);}
        else {action=reply.action;result.latencies_seconds.push(reply.seconds);result.evaluation_warnings.push(...(reply.warnings||[]));}
        result.decisions++;
        if (snapshot.state.observation.force_switch?.some(Boolean)) result.forced_switch_decisions++;
      } else action=baseline(snapshot,baselineKind,random,memory);
      decisions.push({sideIndex,action,snapshot});
    }
    if (!decisions.length) throw new Error(`No pending decisions at turn ${battle.turn}, request ${battle.requestState}`);
    for (const {sideIndex,action,snapshot} of decisions) {
      const side=battle.sides[sideIndex];
      let command;
      try {command=convert(action,side);} catch(error) {command='invalid';}
      const accepted=battle.choose(side.id,command);
      traces.push({turn:snapshot.state.observation.turn||0,side:side.id,action,command,accepted});
      if (!accepted) {
        const key=sideIndex===botSide?'bot_invalid_actions':'baseline_invalid_actions';
        result[key].push({turn:battle.turn,command,action,error:side.choice.error,template:snapshot.template});
        // Invalid output is counted even if the engine's default allows testing to continue.
        if (!battle.choose(side.id,'default')) throw new Error('Engine default fallback failed');
      }
    }
  }
  result.turns=battle.turn; result.winner=battle.ended?battle.winner:null;
  result.outcome=!battle.ended?'turn_limit':battle.winner==='Bot'?'win':battle.winner==='Baseline'?'loss':'tie';
  result.engine_log=battle.log;
  result.traces=traces;
  await agent.send({command:'reset',session_id:session});
  battle.destroy();
  return result;
}

async function main() {
  const results=[];
  const runStartedAt=new Date().toISOString();
  const sourceHashes=Object.fromEntries(['agent.py','battle.py','draft.py','dex.py','legal.py','dex_data.json'].map(name=>[name,
    createHash('sha256').update(fs.readFileSync(path.resolve(__dirname,'../pokemon_bot',name))).digest('hex')]));
  const agent=new PythonAgent();
  try {
    for (let i=0;i<gameCount;i++) {
      const result=await playGame(agent,i+startIndex);results.push(result);
      console.log(`${i+1}/${gameCount} ${result.baseline}: ${result.bot_team} vs ${result.opponent_team}, side ${result.bot_side+1}: ${result.outcome}, ${result.turns} turns, ${result.bot_invalid_actions.length} invalid, ${result.bridge_errors.length} errors`);
      const latencies=results.flatMap(r=>r.latencies_seconds).sort((a,b)=>a-b);
      const sourceUnchanged=Object.entries(sourceHashes).every(([name,hash])=>
        createHash('sha256').update(fs.readFileSync(path.resolve(__dirname,'../pokemon_bot',name))).digest('hex')===hash);
      const summary={engine:'pokemon-showdown',engine_version:require(path.join(enginePath,'package.json')).version,
        run_started_at:runStartedAt,seed_offset:seedOffset,start_index:startIndex,bot_source_sha256:sourceHashes,source_unchanged:sourceUnchanged,
        format:engineFormat,platform_regulation_supported:Dex.formats.get('gen9vgc2025regi').exists,
        description:'Local real-engine Gen 9 doubles 4v4 benchmark; representative curated teams, no Tera, no draft simulation; not a platform win-rate estimate.',
        completed_games:results.length,by_baseline:Object.fromEntries(['greedy_damage','random_legal'].map(kind=>{
          const sample=results.filter(r=>r.baseline===kind);return [kind,{games:sample.length,wins:sample.filter(r=>r.outcome==='win').length,losses:sample.filter(r=>r.outcome==='loss').length,ties:sample.filter(r=>r.outcome==='tie').length,turn_limits:sample.filter(r=>r.outcome==='turn_limit').length}];})),
        bot_invalid_actions:results.reduce((n,r)=>n+r.bot_invalid_actions.length,0),baseline_invalid_actions:results.reduce((n,r)=>n+r.baseline_invalid_actions.length,0),
        bridge_errors:results.reduce((n,r)=>n+r.bridge_errors.length,0),evaluation_warnings:results.reduce((n,r)=>n+r.evaluation_warnings.length,0),bot_decisions:results.reduce((n,r)=>n+r.decisions,0),
        forced_switch_decisions:results.reduce((n,r)=>n+r.forced_switch_decisions,0),
        latency_seconds:{median:latencies[Math.floor(latencies.length/2)],p95:latencies[Math.floor(latencies.length*.95)],max:latencies.at(-1)}};
      fs.writeFileSync(output,JSON.stringify({summary,results},null,2)+'\n');
    }
  } finally {agent.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
