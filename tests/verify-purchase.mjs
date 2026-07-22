// Test runtime del ciclo ordine d'acquisto + ricezione (logica pura, senza DB).
let passed = 0, failed = 0;
function eq(a,e,msg){ const A=JSON.stringify(a),E=JSON.stringify(e); if(A===E)passed++; else {failed++; console.error(`FAIL: ${msg}\n  atteso ${E}\n  ottenuto ${A}`);} }
function ok(c,msg){ if(c)passed++; else {failed++; console.error(`FAIL: ${msg}`);} }

// ---- transizioni PO ----
const T={DRAFT:['SENT','CANCELLED'],SENT:['PARTIAL','RECEIVED','CANCELLED'],PARTIAL:['PARTIAL','RECEIVED','CANCELLED'],RECEIVED:[],CANCELLED:[]};
const canT=(f,t)=>T[f].includes(t);
ok(canT('DRAFT','SENT'),'bozza->inviato');
ok(canT('SENT','RECEIVED'),'inviato->ricevuto');
ok(canT('SENT','PARTIAL'),'inviato->parziale');
ok(canT('PARTIAL','RECEIVED'),'parziale->ricevuto');
ok(!canT('DRAFT','RECEIVED'),'bozza non ricevibile direttamente');
ok(!canT('RECEIVED','PARTIAL'),'ricevuto terminale');
ok(!canT('CANCELLED','SENT'),'annullato terminale');

// ---- applyReceipt ----
function applyReceipt(items, received){
  const byId=new Map(received.map(r=>[r.itemId,Math.max(0,Math.trunc(r.packs))]));
  const lines=[]; let complete=true;
  for(const [itemId,st] of Object.entries(items)){
    const add=byId.get(itemId)??0;
    const residual=Math.max(0,st.packsOrdered-st.packsReceived);
    const accepted=Math.min(add,residual);
    const nr=st.packsReceived+accepted;
    if(nr<st.packsOrdered)complete=false;
    lines.push({itemId,acceptedPacks:accepted,newPacksReceived:nr});
  }
  return {lines,status:complete?'RECEIVED':'PARTIAL'};
}

// ricezione totale in una volta
eq(applyReceipt({a:{packsOrdered:4,packsReceived:0},b:{packsOrdered:2,packsReceived:0}},[{itemId:'a',packs:4},{itemId:'b',packs:2}]),
  {lines:[{itemId:'a',acceptedPacks:4,newPacksReceived:4},{itemId:'b',acceptedPacks:2,newPacksReceived:2}],status:'RECEIVED'},'ricezione totale -> RECEIVED');

// ricezione parziale
eq(applyReceipt({a:{packsOrdered:4,packsReceived:0},b:{packsOrdered:2,packsReceived:0}},[{itemId:'a',packs:2}]),
  {lines:[{itemId:'a',acceptedPacks:2,newPacksReceived:2},{itemId:'b',acceptedPacks:0,newPacksReceived:0}],status:'PARTIAL'},'ricezione parziale -> PARTIAL');

// over-receive clampato al residuo ordinato
eq(applyReceipt({a:{packsOrdered:4,packsReceived:1}},[{itemId:'a',packs:10}]),
  {lines:[{itemId:'a',acceptedPacks:3,newPacksReceived:4}],status:'RECEIVED'},'over-receive clampato a residuo 3');

// seconda ricezione completa un parziale
eq(applyReceipt({a:{packsOrdered:4,packsReceived:2}},[{itemId:'a',packs:2}]),
  {lines:[{itemId:'a',acceptedPacks:2,newPacksReceived:4}],status:'RECEIVED'},'completamento parziale -> RECEIVED');

// unità base aggiunte al magazzino = packs accettati * packSize
function baseAdded(acceptedPacks, packSize){ return acceptedPacks*packSize; }
eq(baseAdded(4,75),300,'4 bottiglie da 75cl -> 300 unità base');

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed?1:0);
