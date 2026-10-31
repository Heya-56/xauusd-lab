const $ = (id) => document.getElementById(id);
const API_BASE = () => ($("api-base").value.trim() || window.HINOVA_ACCOUNTS_API || window.HINOVA_API_BASE || "").replace(/\/$/, "");
const now = () => new Date().toISOString();
const knownTypes = new Set(["market.tick","market.bar_closed","strategy.signal","risk.decision","research.result","system.health"]);
const validEvent = {
  schema_version:"1.0", event_id:"evt-demo-001", event_type:"system.health",
  occurred_at_ms:Date.now(), source:"kernel-test-bench", correlation_id:"test-run-001",
  causation_id:null, payload:{status:"ok", mode:"diagnostic", execution_allowed:false}
};
const log = (message, type="info") => {
  const empty = $("log").querySelector(".muted"); if (empty) empty.remove();
  const row = document.createElement("div"); row.className="log-row";
  const stamp = document.createElement("span"); stamp.style.color = type==="error" ? "var(--red)" : type==="ok" ? "var(--green)" : "var(--gold)";
  stamp.textContent = "["+now()+"] "+type.toUpperCase()+" ";
  const msg = document.createElement("span"); msg.textContent = message;
  row.append(stamp,msg); $("log").prepend(row);
};
const showChecks = (items) => {
  $("checks").replaceChildren();
  for (const item of items) {
    const row=document.createElement("div");row.className="check";
    const status=document.createElement("span");status.className="status "+(item.state==="PASS"?"pass":item.state==="FAIL"?"fail":"skip");status.textContent=item.state;
    const body=document.createElement("div");const title=document.createElement("strong");title.textContent=item.title;
    const note=document.createElement("small");note.textContent=item.note;body.append(title,note);row.append(status,body);$("checks").append(row);
  }
  const fails=items.filter(x=>x.state==="FAIL").length, passes=items.filter(x=>x.state==="PASS").length;
  $("suite-badge").textContent=fails?fails+" échec(s)":passes+"/"+items.length+" contrôles";
  $("suite-badge").className="pill "+(fails?"warn":"ok");
};
function validateEnvelope(raw) {
  const errors=[];
  if (!raw || typeof raw!=="object" || Array.isArray(raw)) return ["L’enveloppe doit être un objet JSON."];
  const required=["schema_version","event_id","event_type","occurred_at_ms","source","correlation_id","payload"];
  for(const key of required) if(!(key in raw)) errors.push("Champ obligatoire manquant : "+key);
  for(const key of Object.keys(raw)) if(!required.includes(key)&&key!=="causation_id") errors.push("Champ inconnu : "+key);
  if(raw.schema_version!=="1.0") errors.push("schema_version doit être 1.0.");
  for(const key of ["event_id","source","correlation_id"]) if(typeof raw[key]!=="string"||!raw[key].trim()) errors.push(key+" doit être une chaîne non vide.");
  if(!knownTypes.has(raw.event_type)) errors.push("Type d’événement non autorisé : "+String(raw.event_type));
  if(!Number.isSafeInteger(raw.occurred_at_ms)||raw.occurred_at_ms<0) errors.push("occurred_at_ms doit être un entier epoch ms positif.");
  if(!raw.payload||typeof raw.payload!=="object"||Array.isArray(raw.payload)) errors.push("payload doit être un objet.");
  if(raw.causation_id!==undefined&&raw.causation_id!==null&&(typeof raw.causation_id!=="string"||!raw.causation_id.trim())) errors.push("causation_id doit être null ou une chaîne non vide.");
  if(raw.event_type==="system.health"&&raw.payload?.execution_allowed===true) errors.push("Un événement de santé ne peut jamais autoriser l’exécution.");
  return errors;
}
function checkEvent() {
  try {
    const raw=JSON.parse($("event-json").value), errors=validateEnvelope(raw);
    $("event-result").textContent=errors.length?"REFUSÉ —\n"+errors.map(e=>"• "+e).join("\n"):"ACCEPTÉ — enveloppe conforme au contrat UI 1.0.\n"+JSON.stringify(raw,null,2);
    log(errors.length?"Envelope refusée : "+errors.join(" | "):"Envelope conforme au contrat UI 1.0.",errors.length?"error":"ok");
    return errors.length===0;
  } catch(e) {
    $("event-result").textContent="REFUSÉ — JSON invalide : "+e.message;log("JSON invalide : "+e.message,"error");return false;
  }
}
async function request(path) {
  const base=API_BASE(); if(!base) throw new Error("URL API absente. Renseigne une URL de Worker déployé.");
  const response=await fetch(base+path,{headers:{Accept:"application/json"},credentials:"include"});
  const text=await response.text();let body;try{body=JSON.parse(text)}catch{body={raw:text.slice(0,1000)}}
  return {ok:response.ok,status:response.status,body};
}
async function ping() {
  const target=$("test-target").value, result={base:API_BASE()||"(non configurée)",tests:[]};
  $("ping-api").disabled=true;
  try {
    for(const [name,path] of (target==="both"?[["health","/v1/health"],["dashboard","/v1/dashboard"]]:[[target,target==="health"?"/v1/health":"/v1/dashboard"]])) {
      try { const r=await request(path);result.tests.push({name,...r});log(name+" HTTP "+r.status,r.ok?"ok":"error"); }
      catch(e){result.tests.push({name,error:e.message});log(name+" : "+e.message,"error");}
    }
    $("api-result").textContent=JSON.stringify(result,null,2);
    const health=result.tests.find(x=>x.name==="health");$("api-status").textContent=health?(health.ok?"OK · "+health.status:"Erreur · "+health.status):"Non testé";
    const dash=result.tests.find(x=>x.name==="dashboard");if(dash)$("snapshot-status").textContent=dash.ok?"API · "+dash.status:dash.status===401?"Session requise":"Erreur · "+(dash.status||"réseau");
  } finally {$("ping-api").disabled=false;}
}
async function runSuite() {
  $("run-suite").disabled=true;const checks=[];
  try {
    const res=await fetch("data/demo-snapshot.json",{headers:{Accept:"application/json"}});
    if(!res.ok) throw new Error("Snapshot HTTP "+res.status);
    const snap=await res.json();
    checks.push({state:"PASS",title:"Snapshot de démonstration lisible",note:"data/demo-snapshot.json chargé ("+res.status+")."});
    const hasSignal=!!snap.latest_signal&&typeof snap.latest_signal==="object";
    checks.push({state:hasSignal?"PASS":"FAIL",title:"Structure du signal présent",note:hasSignal?"latest_signal présent.":"latest_signal absent ou invalide."});
    const executionDisabled=snap.latest_signal?.risk?.execution_allowed===false || snap.latest_signal?.execution_allowed===false;
    checks.push({state:executionDisabled?"PASS":"FAIL",title:"Garde-fou : aucune exécution réelle",note:executionDisabled?"execution_allowed=false dans le snapshot.":"Impossible de confirmer l’arrêt de l’exécution dans le snapshot."});
    const synthetic=String(snap.provenance?.instrument_type||snap.latest_signal?.instrument_type||"").toLowerCase().includes("synthetic");
    checks.push({state:synthetic?"PASS":"SKIP",title:"Provenance synthétique explicitée",note:synthetic?"Le snapshot marque les données comme synthétiques.":"Le snapshot ne fournit pas ce marqueur à l’emplacement attendu; ne pas interpréter comme données marché."});
    $("snapshot-status").textContent="Chargé · démo";
    log("Snapshot local chargé; aucune performance marché ne sera déduite.","ok");
  } catch(e) {
    checks.push({state:"FAIL",title:"Chargement du snapshot",note:e.message});$("snapshot-status").textContent="Indisponible";log(e.message,"error");
  }
  const good=validateEnvelope(validEvent).length===0;
  checks.push({state:good?"PASS":"FAIL",title:"Envelope valide acceptée",note:"Test du contrat d’événement version 1.0."});
  const bad={...validEvent,event_type:"trade.execute"};
  const rejects=validateEnvelope(bad).length>0;
  checks.push({state:rejects?"PASS":"FAIL",title:"Type d’ordre interdit rejeté",note:"trade.execute n’existe pas dans le contrat d’événement."});
  const unknown={...validEvent,unexpected_field:true};
  checks.push({state:validateEnvelope(unknown).length?"PASS":"FAIL",title:"Champ inconnu rejeté",note:"Le contrat refuse les champs non déclarés."});
  const boolTs={...validEvent,occurred_at_ms:true};
  checks.push({state:validateEnvelope(boolTs).length?"PASS":"FAIL",title:"Timestamp invalide rejeté",note:"Le timestamp doit être un entier epoch millisecondes."});
  const noExec={...validEvent,payload:{execution_allowed:true}};
  checks.push({state:validateEnvelope(noExec).length?"PASS":"FAIL",title:"Autorisation d’exécution impossible via health",note:"Le test refuse execution_allowed=true sur system.health."});
  showChecks(checks);
  const failed=checks.filter(x=>x.state==="FAIL").length;
  log("Suite terminée : "+(checks.length-failed)+" contrôles non échoués sur "+checks.length+".",failed?"error":"ok");
  $("run-suite").disabled=false;
}
$("event-json").value=JSON.stringify(validEvent,null,2);
$("run-suite").addEventListener("click",runSuite);
$("validate-event").addEventListener("click",checkEvent);
$("load-valid").addEventListener("click",()=>{$("event-json").value=JSON.stringify({...validEvent,occurred_at_ms:Date.now()},null,2);$("event-result").textContent="Envelope de test chargée.";});
$("load-invalid").addEventListener("click",()=>{$("event-json").value=JSON.stringify({...validEvent,event_type:"trade.execute"},null,2);$("event-result").textContent="Cas invalide chargé. Clique sur « Valider l’enveloppe ».";});
$("ping-api").addEventListener("click",ping);
$("clear-log").addEventListener("click",()=>{$("log").replaceChildren();log("Journal vidé.");});
if(window.HINOVA_ACCOUNTS_API||window.HINOVA_API_BASE)$("api-base").value=window.HINOVA_ACCOUNTS_API||window.HINOVA_API_BASE;
