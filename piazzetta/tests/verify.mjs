// Test runtime della logica pura (Node type-stripping non necessario: qui ricopio
// le funzioni in JS per verificarle in isolamento, senza dipendenze esterne né DB).
// Verifica: mapping station, percentili/summary tempi, contabilità crediti, macchina a stati.

let passed = 0, failed = 0;
function eq(actual, expected, msg) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { passed++; }
  else { failed++; console.error(`FAIL: ${msg}\n  atteso ${e}\n  ottenuto ${a}`); }
}
function ok(cond, msg) { if (cond) passed++; else { failed++; console.error(`FAIL: ${msg}`); } }

// ---------- stations ----------
const TAV = new Set(['pizza','primo','secondo','contorno','panino','piadina','toast','insalata','dolce','piatto','tavola_calda','griglia','frittura']);
const BAR = new Set(['aperitivo','bevanda','analcolico','cocktail','birra','vino','caffe','caffetteria','liquore','distillato']);
function stationForCategory(c){ c=(c||'').trim().toLowerCase(); if(TAV.has(c))return'TAVOLA_CALDA'; if(BAR.has(c))return'BAR'; return'BAR'; }
eq(stationForCategory('pizza'),'TAVOLA_CALDA','pizza -> cucina');
eq(stationForCategory('Aperitivo'),'BAR','aperitivo (case) -> bar');
eq(stationForCategory('caffe'),'BAR','caffe -> bar');
eq(stationForCategory('sconosciuto'),'BAR','fallback -> bar');

// ---------- prep-time ----------
function diffSec(a,b){ if(!a||!b)return null; const s=(Date.parse(b)-Date.parse(a))/1000; return s>=0?s:null; }
function percentile(vals,p){ const xs=vals.filter(Number.isFinite).sort((x,y)=>x-y); if(!xs.length)return null; if(xs.length===1)return xs[0]; const r=(p/100)*(xs.length-1),lo=Math.floor(r),hi=Math.ceil(r); if(lo===hi)return xs[lo]; const w=r-lo; return xs[lo]*(1-w)+xs[hi]*w; }
function mean(v){ const xs=v.filter(Number.isFinite); return xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null; }

eq(diffSec('2026-07-22T10:00:00Z','2026-07-22T10:02:30Z'),150,'diffSec 2:30');
eq(diffSec('2026-07-22T10:02:00Z','2026-07-22T10:00:00Z'),null,'diffSec negativo -> null');
eq(diffSec(null,'2026-07-22T10:00:00Z'),null,'diffSec con null');
eq(percentile([10,20,30,40,50],50),30,'mediana 5 valori');
eq(percentile([10,20,30,40],50),25,'mediana 4 valori (interp)');
eq(percentile([1,2,3,4,5,6,7,8,9,10],90),9.1,'p90 interp');
eq(mean([60,120,180]),120,'media 120');
eq(mean([]),null,'media vuota -> null');

// aggregazione per category
const items=[
  {productId:'a',productName:'Spritz',category:'aperitivo',station:'BAR',sentAt:'2026-07-22T10:00:00Z',startedAt:'2026-07-22T10:00:30Z',readyAt:'2026-07-22T10:02:00Z'},
  {productId:'a',productName:'Spritz',category:'aperitivo',station:'BAR',sentAt:'2026-07-22T10:05:00Z',startedAt:'2026-07-22T10:05:30Z',readyAt:'2026-07-22T10:08:00Z'},
  {productId:'b',productName:'Pizza',category:'pizza',station:'TAVOLA_CALDA',sentAt:'2026-07-22T10:00:00Z',startedAt:'2026-07-22T10:02:00Z',readyAt:'2026-07-22T10:12:00Z'},
];
function summarize(v){ const xs=v.filter(Number.isFinite); return {count:xs.length,avg:xs.length?Math.round(mean(xs)):null,median:xs.length?Math.round(percentile(xs,50)):null}; }
const barTotals=items.filter(i=>i.station==='BAR').map(i=>diffSec(i.sentAt,i.readyAt));
eq(summarize(barTotals),{count:2,avg:150,median:150},'BAR sent->ready: 120s e 180s -> media 150');
const pizzaPrep=items.filter(i=>i.category==='pizza').map(i=>diffSec(i.startedAt,i.readyAt));
eq(summarize(pizzaPrep),{count:1,avg:600,median:600},'pizza prep 10min');

// ---------- credit logic ----------
function applyTransaction({currentBalanceCents:bal,limitCents:lim,type,amountCents:amt}){
  if((type==='CHARGE'||type==='PAYMENT')&&(!(amt>0)))return{ok:false,newBalanceCents:bal,error:'Importo non valido'};
  let delta = type==='CHARGE'?amt:type==='PAYMENT'?-amt:amt;
  const nb=bal+delta;
  if(type==='PAYMENT'&&nb<0)return{ok:false,newBalanceCents:bal,error:'Pagamento superiore al dovuto'};
  if((type==='CHARGE'||type==='ADJUST')&&delta>0&&lim>0&&nb>lim)return{ok:false,newBalanceCents:bal,error:'Limite superato'};
  return{ok:true,newBalanceCents:nb};
}
eq(applyTransaction({currentBalanceCents:0,limitCents:0,type:'CHARGE',amountCents:1500}),{ok:true,newBalanceCents:1500},'addebito su saldo 0');
eq(applyTransaction({currentBalanceCents:1500,limitCents:0,type:'PAYMENT',amountCents:500}),{ok:true,newBalanceCents:1000},'pagamento parziale');
ok(applyTransaction({currentBalanceCents:1000,limitCents:0,type:'PAYMENT',amountCents:2000}).ok===false,'pagamento eccessivo rifiutato');
ok(applyTransaction({currentBalanceCents:4000,limitCents:5000,type:'CHARGE',amountCents:2000}).ok===false,'addebito oltre limite rifiutato');
eq(applyTransaction({currentBalanceCents:4000,limitCents:5000,type:'CHARGE',amountCents:1000}),{ok:true,newBalanceCents:5000},'addebito fino al limite ok');
ok(applyTransaction({currentBalanceCents:0,limitCents:0,type:'CHARGE',amountCents:0}).ok===false,'importo zero rifiutato');
eq(applyTransaction({currentBalanceCents:100,limitCents:0,type:'ADJUST',amountCents:-100}),{ok:true,newBalanceCents:0},'rettifica negativa');

// ---------- macchina a stati ----------
const T={DRAFT:['SENT','CANCELLED'],SENT:['IN_PREPARATION','CANCELLED'],IN_PREPARATION:['READY','CANCELLED'],READY:['SERVED','CANCELLED'],SERVED:['PAID','CANCELLED'],PAID:[],CANCELLED:[]};
const canT=(f,t)=>(T[f]||[]).includes(t);
ok(canT('SENT','IN_PREPARATION'),'SENT->IN_PREPARATION ok');
ok(canT('READY','SERVED'),'READY->SERVED ok');
ok(!canT('SENT','SERVED'),'SENT->SERVED vietato');
ok(!canT('PAID','SENT'),'PAID terminale');
ok(canT('SERVED','PAID'),'SERVED->PAID ok');

// ---------- ciclo di stato per riga (KDS) ----------
function nextItemStatus(s){ return s==='PENDING'?'IN_PREPARATION':s==='IN_PREPARATION'?'READY':s==='READY'?'SERVED':null; }
eq(nextItemStatus('PENDING'),'IN_PREPARATION','riga: coda -> in prep');
eq(nextItemStatus('IN_PREPARATION'),'READY','riga: in prep -> pronto');
eq(nextItemStatus('READY'),'SERVED','riga: pronto -> consegnato');
eq(nextItemStatus('SERVED'),null,'riga: consegnato terminale');

// timestamp scritti a ogni step della riga
function itemTimestampsFor(status){ return status==='SENT'?['sentAt']:status==='IN_PREPARATION'?['startedAt']:status==='READY'?['readyAt']:status==='SERVED'?['servedAt']:[]; }
eq(itemTimestampsFor('IN_PREPARATION'),['startedAt'],'IN_PREPARATION scrive startedAt (coda misurabile)');
eq(itemTimestampsFor('READY'),['readyAt'],'READY scrive readyAt (prep misurabile)');
eq(itemTimestampsFor('SERVED'),['servedAt'],'SERVED scrive servedAt');

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
