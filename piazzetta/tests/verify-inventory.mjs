// Test runtime della logica magazzino/riordino (pura, senza DB).
let passed = 0, failed = 0;
function eq(a, e, msg){ const A=JSON.stringify(a),E=JSON.stringify(e); if(A===E)passed++; else {failed++; console.error(`FAIL: ${msg}\n  atteso ${E}\n  ottenuto ${A}`);} }
function ok(c,msg){ if(c)passed++; else {failed++; console.error(`FAIL: ${msg}`);} }

// ---- movementSign + applicazione delta ----
function movementSign(t){ return (t==='LOAD'||t==='RETURN'||t==='RECEIPT'||t==='PHYSICAL')?1:-1; }
function applyMovement(current, type, qty){
  const signed = type==='PHYSICAL'? Math.trunc(qty) : movementSign(type)*Math.abs(Math.trunc(qty));
  let after = current + signed, applied = signed;
  if(after<0){ if(type==='SALE'){ applied=-current; after=0; } else { return {error:true, current}; } }
  return { after, applied };
}
eq(applyMovement(10,'LOAD',5),{after:15,applied:5},'carico +5');
eq(applyMovement(10,'WASTE',3),{after:7,applied:-3},'scarto -3');
eq(applyMovement(10,'SALE',4),{after:6,applied:-4},'vendita -4');
eq(applyMovement(2,'SALE',5),{after:0,applied:-2},'vendita oltre giacenza: azzera, log reale -2');
ok(applyMovement(2,'WASTE',5).error===true,'scarto oltre giacenza rifiutato');
eq(applyMovement(10,'PHYSICAL',-4),{after:6,applied:-4},'inventario fisico delta -4');
eq(applyMovement(10,'PHYSICAL',3),{after:13,applied:3},'inventario fisico delta +3');

// ---- computeReorder (par level + confezioni) ----
function computeReorder({quantity,reorderLevel,parLevel,packSize}){
  const ps=Math.max(1,Math.trunc(packSize||1));
  const target=parLevel>0?parLevel:reorderLevel;
  const triggered=reorderLevel>0&&quantity<=reorderLevel;
  const deficit=Math.max(0,target-quantity);
  if(!triggered||deficit<=0) return {needed:false,targetLevel:target,deficitBase:0,packSize:ps,packs:0,orderedBase:0};
  const packs=Math.ceil(deficit/ps);
  return {needed:true,targetLevel:target,deficitBase:deficit,packSize:ps,packs,orderedBase:packs*ps};
}
// sopra soglia -> niente
eq(computeReorder({quantity:20,reorderLevel:10,parLevel:30,packSize:1}).needed,false,'sopra soglia: nessun riordino');
// sotto soglia, unità singola: target 30, giacenza 8 -> 22
eq(computeReorder({quantity:8,reorderLevel:10,parLevel:30,packSize:1}),{needed:true,targetLevel:30,deficitBase:22,packSize:1,packs:22,orderedBase:22},'unità singola deficit 22');
// confezioni: bottiglia da 75cl, target 300cl, giacenza 40cl -> deficit 260 -> ceil(260/75)=4 conf = 300cl
eq(computeReorder({quantity:40,reorderLevel:75,parLevel:300,packSize:75}),{needed:true,targetLevel:300,deficitBase:260,packSize:75,packs:4,orderedBase:300},'confezioni 75cl: 4 bottiglie');
// parLevel 0 -> usa reorderLevel come target
eq(computeReorder({quantity:5,reorderLevel:10,parLevel:0,packSize:1}).targetLevel,10,'parLevel 0 usa reorderLevel');
// reorderLevel 0 -> mai riordino
eq(computeReorder({quantity:0,reorderLevel:0,parLevel:50,packSize:1}).needed,false,'senza soglia nessun riordino');
// esattamente a soglia -> scatta (<=)
ok(computeReorder({quantity:10,reorderLevel:10,parLevel:20,packSize:1}).needed===true,'a soglia (=) scatta');

// scelta listino più economico per unità base
function cheapestPerBase(listings){ return listings.slice().sort((a,b)=> a.packPriceCents/Math.max(1,a.packSize) - b.packPriceCents/Math.max(1,b.packSize))[0]; }
eq(cheapestPerBase([{id:'a',packSize:75,packPriceCents:750},{id:'b',packSize:100,packPriceCents:900}]).id,'b','9c/base < 10c/base -> b');

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed?1:0);
