// Generate the five factory drafts and SDK sources without embedding secret values.
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const supabase = "https://uobeshcvmtawjxibciuy.supabase.co/rest/v1";
const kanban = "https://kanban-api.okehc.com/api/tasks";
const headerCredential = { httpHeaderAuth: { id: "WXW1Qq0Mn5l5wcDr", name: "openai-radar-header" } };
const kanbanCredential = { httpBearerAuth: { id: "MhO6jMfbdNT6QcOg", name: "N8N_RADARES_KANBAN" } };
const supabaseCredential = { supabaseApi: { id: "6tc6sprc6stOuXbn", name: "RADARS_SUPABASE" } };
const evolutionCredential = { httpHeaderAuth: { id: "pRyb5MlyNAjEuDud", name: "Evolution Factory" } };
const first = (name) => `$('${name}').first().json`;
const expression = (value) => `={{ ${value} }}`;

function node(id, name, type, version, parameters, credentials) {
  return { id, name, type: `n8n-nodes-base.${type}`, typeVersion: version, parameters,
    ...(credentials ? { credentials } : {}) };
}
const code = (id, name, jsCode) => node(id, name, "code", 2, { jsCode });
const webhook = (path) => node("start", "Entrada", "webhook", 2,
  { httpMethod: "POST", path: `factory/${path}`, authentication: "headerAuth", responseMode: "lastNode", options: {} }, headerCredential);
const http = (id, name, method, url, jsonBody, api = "kanban") => node(id, name, "httpRequest", 4.2, {
  method, url, ...(api === "supabase" ? { authentication: "predefinedCredentialType", nodeCredentialType: "supabaseApi" }
    : { authentication: "genericCredentialType", genericAuthType: "httpBearerAuth" }),
  ...(jsonBody ? { sendBody: true, specifyBody: "json", jsonBody } : {}), options: { timeout: 15000 },
}, api === "kanban" ? kanbanCredential : supabaseCredential);
const rpc = (id, name, fn, body) => http(id, name, "POST", `${supabase}/rpc/${fn}`, expression(`JSON.stringify(${body})`), "supabase");
const files = (id, name, operation, payload) => http(id, name, "POST",
  `https://kanban-api.okehc.com/api/factory/files/${operation}`, expression(`JSON.stringify(${payload})`));
const checkFiles = (id, name) => code(id, name, `const p=$input.first().json; if (!p.event_id || !(p.bytes>0 || p.specs_ready || p.file_ready || p.release_ready)) throw new Error('Falló la operación de archivos.');\nreturn [{json:p}];`);
const condition = (id, name, left, right) => node(id, name, "if", 2.4, {
  conditions: { options: { caseSensitive: true, leftValue: "", typeValidation: "strict", version: 2 },
    conditions: [{ leftValue: expression(left), rightValue: right, operator: { type: "string", operation: "equals" } }], combinator: "and" }, options: {},
});
const whatsapp = (id, name, text, recipient) => http(id, name, "POST",
  "http://192.168.100.86:8080/message/sendText/anyo",
  expression(`JSON.stringify({number: ${recipient}, text: ${text}})`));
function waNode(id, name, text, recipient) {
  const n = whatsapp(id, name, text, recipient);
  n.parameters.genericAuthType = "httpHeaderAuth";
  n.credentials = evolutionCredential;
  n.notes = 'Selecciona Evolution Factory (Header Auth, nombre apikey), la instancia y el destinatario reales.';
  return n;
}
const payload = first("Validar entrada");
const pipeline = first("Consultar pipeline");
const approve = http("approve", "Aprobar tarjeta", "POST", expression(`'${kanban}/' + ${payload}.task_id + '/review'`),
  '{"verdict":"APPROVE","feedback":"Entrega validada por el workflow de la fábrica."}');
const validate = (extra) => code("validate", "Validar entrada", `const p = $input.first().json.body ?? $input.first().json;
if (typeof p.event_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(p.event_id)) throw new Error('event_id inválido');
${extra}
return [{json:p}];`);
const getPipeline = () => rpc("get-pipeline", "Consultar pipeline", "factory_get", `{p_event_id:${payload}.event_id}`);
const getTask = () => http("get-task", "Consultar tarjeta", "GET", expression(`'${kanban}/' + ${payload}.task_id`));

export const workflows = [
  {
    key: "01", name: "01_Radar_Ready_To_Brio", existingId: "NWIvkLOXKPe3yUZa",
    description: "Registra el pipeline, prepara paquete.zip, despacha a Brio y envía su aviso por WhatsApp.",
    nodes: [webhook("package-ready"), validate(`if (!['radar_gobierno_nl','radar_compras_publicas','radar_regulacion_federal'].includes(p.radar_table) || !p.title || !p.package_path || !p.package_filename) throw new Error('Faltan datos del paquete');`),
      files("files", "Preparar paquete en WSL", "input", payload), checkFiles("files-ok", "Comprobar paquete"),
      rpc("start-pipeline", "Registrar pipeline", "factory_start", `{p_payload:${payload}}`),
      code("dispatch-data", "Preparar tarjeta Brio", `const p=$input.first().json;
if (p.stage !== 'RESEARCH') return [];
return [{json:{project_id:1,title:'Investigar: '+p.title,description:'Investiga el paquete y entrega research.zip. Después de entregar, consulta la siguiente tarjeta asignada a brio.',assigned_to:'brio',metadata:{event_id:p.event_id,factory_dispatch_key:p.event_id+':research',muse_zip:{path:p.base_folder+'/01_input',input_file:'paquete.zip',output_path:p.base_folder+'/02_research',output_file:'research.zip'}}}}];`),
      http("dispatch", "Despachar tarjeta Brio", "POST", `${kanban}/dispatch`, expression(`JSON.stringify(${first("Preparar tarjeta Brio")})`)),
      rpc("save-task", "Guardar tarjeta Brio", "factory_record_task", `{p_event_id:${payload}.event_id,p_branch:'brio',p_task_id:String(${first("Despachar tarjeta Brio")}.id)}`),
      waNode("wake-brio", "Despertar Brio", `'WAKEUP BRIO | Event: '+${payload}.event_id+' | Task: #'+${first("Despachar tarjeta Brio")}.id+' | Reclama, investiga y entrega research.zip. Después consulta la siguiente tarjeta a tu nombre.'`, "'CONFIGURAR_NUMERO_BRIO'"),
    ], chain: ".add(start).to(validate).to(files).to(files_ok).to(start_pipeline).to(dispatch_data).to(dispatch).to(save_task).to(wake_brio)",
    groups: [["Preparar investigación", ["validate","files","files-ok","start-pipeline","dispatch-data"]]],
  },
  {
    key: "02", name: "02_Brio_Done_To_Nod_Eval", existingId: "JlsGr3jYEd5tmoJj",
    description: "Comprueba la entrega de Brio, registra research.zip y despierta a Nod para evaluar GO o NO_GO.",
    nodes: [webhook("brio-done"), validate(`p.task_id=Number(p.brio_task_id); if (!Number.isSafeInteger(p.task_id) || p.task_id<1 || p.research_zip_path!==p.event_id+'/02_research/research.zip') throw new Error('Entrega inválida');`),
      getPipeline(), getTask(),
      code("check-task", "Validar entrega Brio", `const t=$input.first().json,p=${payload},f=${pipeline};
if (String(t.id)!==String(f.brio_task_id) || t.id!==p.task_id || t.project_id!==1 || t.claimed_by!=='brio' || t.status!=='review' || t.metadata_payload?.event_id!==p.event_id) throw new Error('La tarjeta no corresponde a la entrega en revisión');
return [{json:p}];`),
      files("verify", "Verificar research.zip", "verify", `{event_id:${payload}.event_id,zip_path:${payload}.research_zip_path}`), checkFiles("verify-ok", "Comprobar research.zip"),
      rpc("save-research", "Registrar investigación", "factory_research_done", `{p_payload:${payload}}`),
      waNode("wake-nod", "Despertar Nod evaluador", `'WAKEUP NOD [EVALUACION] | Event: '+${payload}.event_id+' | Task Brio: #'+${payload}.brio_task_id+' | Revisa research.zip y envía tu decisión a https://anyo.okehc.com/webhook/factory/nod-decision. Al terminar consulta tu siguiente tarjeta.'`, "'528145925005'"),
    ], chain: ".add(start).to(validate).to(get_pipeline).to(get_task).to(check_task).to(verify).to(verify_ok).to(save_research).to(wake_nod)",
    groups: [["Validar entrega",["validate","get-pipeline","get-task","check-task","verify","verify-ok"]]],
  },
  {
    key: "03", name: "03_Nod_Decision_Router", existingId: "anHYNSMXip5G2ze3",
    description: "Recibe la decisión de Nod, aprueba la investigación y prepara únicamente las ramas activas.",
    nodes: [webhook("nod-decision"), validate(`p.task_id=Number(p.brio_task_id);
if (!Number.isSafeInteger(p.task_id) || p.task_id<1 || !['GO','NO_GO'].includes(p.decision)) throw new Error('Decisión inválida');
for (const b of ['mvp','prospection','landing']) {
 if (typeof p.branches?.['run_'+b]!=='boolean') throw new Error('Las banderas deben ser booleanas');
 if (p.decision==='NO_GO' && p.branches['run_'+b]) throw new Error('NO_GO no activa ramas');
 const key=b==='prospection'?'icp_prompt':b+'_prompt';
 if (p.branches['run_'+b] && !p.specs?.[key]?.trim()) throw new Error('Falta el prompt de una rama activa');
}
if (p.decision==='GO' && !Object.values(p.branches).some(v=>v===true)) throw new Error('GO necesita una rama activa');`),
      getPipeline(), getTask(),
      code("check-task", "Validar investigación", `const t=$input.first().json,p=${payload},f=${pipeline};
if (String(t.id)!==String(f.brio_task_id) || t.id!==p.task_id || t.project_id!==1 || t.claimed_by!=='brio' || !['review','done'].includes(t.status) || t.metadata_payload?.event_id!==p.event_id || !['EVALUATING','BUILDING','REJECTED'].includes(f.stage)) throw new Error('Investigación o pipeline incorrectos');
return [{json:t}];`),
      condition("needs-review", "¿Requiere aprobación?", "$json.status", "review"), structuredClone(approve),
      rpc("decision", "Registrar decisión", "factory_decide", `{p_payload:${payload}}`),
      condition("go", "¿Decisión GO?", "$json.decision", "GO"),
      files("specs", "Preparar especificaciones", "specs", payload), checkFiles("specs-ok", "Comprobar especificaciones"),
      code("branches", "Preparar ramas activas", `const p=${payload};
const defs=[['mvp','codex','04_mvp','mvp.zip','mvp_prompt'],['prospection','nod','05_prospects','prospects.zip','icp_prompt'],['landing','nod','06_landing','landing.zip','landing_prompt']];
return defs.filter(([b])=>p.branches['run_'+b]).map(([branch,agent,folder,output,prompt])=>({json:{event_id:p.event_id,branch,agent,card:{project_id:1,title:branch+': '+p.event_id,description:p.specs[prompt],assigned_to:agent,metadata:{event_id:p.event_id,branch,factory_dispatch_key:p.event_id+':'+branch,muse_zip:{path:p.event_id+'/03_specs',input_file:branch+'-input.zip',output_path:p.event_id+'/'+folder,output_file:output}}}},pairedItem:{item:0}}));`),
      http("dispatch", "Despachar rama", "POST", `${kanban}/dispatch`, "={{ JSON.stringify($json.card) }}"),
      rpc("save-task", "Guardar tarjeta de rama", "factory_record_task", `{p_event_id:$('Preparar ramas activas').item.json.event_id,p_branch:$('Preparar ramas activas').item.json.branch,p_task_id:String($json.id)}`),
      condition("mvp", "¿Rama MVP?", "$('Preparar ramas activas').item.json.branch", "mvp"),
      files("wakeup", "Preparar archivo de Codex", "wakeup", `{event_id:$('Preparar ramas activas').item.json.event_id,task_id:String($('Despachar rama').item.json.id)}`),
      checkFiles("wakeup-ok", "Comprobar archivo de Codex"),
      waNode("wake-branch", "Despertar agente de rama", `'WAKEUP '+($('Preparar ramas activas').item.json.branch==='landing'?'NOD [LANDING]':'NOD [PROSPECCION]')+' | Event: '+$('Preparar ramas activas').item.json.event_id+' | Task: #'+$('Despachar rama').item.json.id+' | Lee la tarjeta, entrega su ZIP, envía a revisión, llama WF4 y continúa con la siguiente tarjeta a tu nombre.'`, "'528145925005'"),
    ], chain: ".add(start).to(validate).to(get_pipeline).to(get_task).to(check_task).to(needs_review.onTrue(approve.to(decision)).onFalse(decision)).add(decision).to(go.onTrue(specs.to(specs_ok.to(branches.to(dispatch.to(save_task.to(mvp.onTrue(wakeup.to(wakeup_ok)).onFalse(wake_branch))))))))",
    groups: [["Validar decisión",["validate","get-pipeline","get-task","check-task"]],["Registrar veredicto",["needs-review","approve","decision"]],["Preparar ramas",["specs","specs-ok","branches","dispatch","save-task"]],["Activar ramas",["mvp","wakeup","wakeup-ok","wake-branch"]]],
  },
  {
    key: "04", name: "04_Branch_Collector_And_Join", existingId: "8zG48MWjzi5VTYEL",
    description: "Valida cada entrega y despierta a Nod al completar todas las ramas activas mediante una transición atómica.",
    nodes: [webhook("branch-done"), validate(`p.task_id=Number(p.task_id); if (!Number.isSafeInteger(p.task_id) || p.task_id<1 || !['mvp','prospection','landing'].includes(p.branch)) throw new Error('Rama inválida');`),
      getPipeline(), getTask(),
      code("check-task", "Validar entrega de rama", `const t=$input.first().json,p=${payload},f=${pipeline};
const defs={mvp:['codex','04_mvp/mvp.zip'],prospection:['nod','05_prospects/prospects.zip'],landing:['nod','06_landing/landing.zip']};
const [agent,path]=defs[p.branch];
if (!f['run_'+p.branch] || String(f[p.branch+'_task_id'])!==String(p.task_id) || t.id!==p.task_id || t.project_id!==1 || t.claimed_by!==agent || !['review','done'].includes(t.status) || t.metadata_payload?.event_id!==p.event_id || p.zip_path!==p.event_id+'/'+path || !['BUILDING','FINAL_REVIEW'].includes(f.stage)) throw new Error('Entrega no corresponde a una rama activa');
return [{json:t}];`),
      files("verify", "Verificar ZIP de rama", "verify", payload), checkFiles("verify-ok", "Comprobar ZIP de rama"),
      condition("needs-review", "¿Requiere aprobación?", `${first("Validar entrega de rama")}.status`, "review"), structuredClone(approve),
      rpc("collect", "Registrar entrega y conteo", "factory_branch_done", `{p_payload:${payload}}`),
      condition("ready", "¿Todas las ramas listas?", "String($json.wake_final_review)", "true"),
      waNode("wake-final", "Despertar Nod para cierre", `'WAKEUP NOD [CIERRE FINAL] | Event: '+${payload}.event_id+' | Ramas activas completas. MVP='+${first("Registrar entrega y conteo")}.mvp_zip_path+' | Prospects='+${first("Registrar entrega y conteo")}.prospection_zip_path+' | Landing='+${first("Registrar entrega y conteo")}.landing_zip_path+' | Entrega el resumen por WF5 y continúa con tu siguiente tarjeta.'`, "'528145925005'"),
    ], chain: ".add(start).to(validate).to(get_pipeline).to(get_task).to(check_task).to(verify).to(verify_ok).to(needs_review.onTrue(approve.to(collect)).onFalse(collect)).add(collect).to(ready.onTrue(wake_final))",
    groups: [["Validar entregable",["validate","get-pipeline","get-task","check-task","verify","verify-ok"]],["Cerrar rama",["needs-review","approve","collect"]]],
  },
  {
    key: "05", name: "05_Final_Delivery_To_User", existingId: "gwu7uCq8i3sTAaeH",
    description: "Guarda el resumen final, cierra Supabase y entrega al usuario las rutas de las ramas ejecutadas.",
    nodes: [webhook("final-close"), validate(`if (typeof p.executive_summary!=='string' || !p.executive_summary.trim() || p.bundle_path!=='/mnt/c/_mcp/muse-packages/'+p.event_id+'/') throw new Error('Cierre inválido');`),
      getPipeline(), code("check-stage", "Comprobar cierre", `const p=$input.first().json;if (!['FINAL_REVIEW','DONE'].includes(p.stage)) throw new Error('Faltan ramas por completar'); return [{json:p}];`),
      files("release", "Guardar resumen ejecutivo", "release", payload), checkFiles("release-ok", "Comprobar resumen"),
      rpc("close", "Cerrar pipeline y radar", "factory_final_close", `{p_payload:${payload}}`),
      node("notify-user", "Entregar al usuario por Telegram", "telegram", 1.2, {resource:"message",operation:"sendMessage",chatId:"CONFIGURAR_CHAT_CHEKO",text:"={{ $json.title + '\\n\\n' + $json.final_summary + '\\n\\nMVP: ' + ($json.mvp_zip_path ?? 'SKIPPED') + '\\nProspectos: ' + ($json.prospection_zip_path ?? 'SKIPPED') + '\\nLanding: ' + ($json.landing_zip_path ?? 'SKIPPED') + '\\nCarpeta: ' + $json.final_bundle_path }}",additionalFields:{appendAttribution:false}}),
    ], chain: ".add(start).to(validate).to(get_pipeline).to(check_stage).to(release).to(release_ok).to(close).to(notify_user)",
    groups: [["Cerrar oportunidad",["validate","get-pipeline","check-stage","release","release-ok","close"]]],
  },
];

export function sdk(wf) {
  const variable = (id) => id.replaceAll("-", "_");
  const declarations = wf.nodes.map((n, index) => {
    const config = { name:n.name, parameters:n.parameters, position:[index*240,0], notes:n.notes };
    let configText = JSON.stringify(config);
    if (n.credentials) {
      const entries=Object.entries(n.credentials).map(([type,c])=>`${JSON.stringify(type)}:newCredential(${JSON.stringify(c.name)},${JSON.stringify(c.id)})`);
      configText=configText.slice(0,-1)+`,credentials:{${entries.join(",")}}}`;
    }
    const constructor=n.type.endsWith(".webhook")?"trigger":n.type.endsWith(".if")?"ifElse":"node";
    return `const ${variable(n.id)}=${constructor}({type:${JSON.stringify(n.type)},version:${n.typeVersion},config:${configText}});`;
  });
  const groups=wf.groups.map(([name,ids])=>`.group(${JSON.stringify(name)},[${ids.map(variable).join(",")}],{description:${JSON.stringify(name+" dentro del ciclo de oportunidad.")}})`).join("");
  return `import {workflow,node,trigger,ifElse,newCredential} from '@n8n/workflow-sdk';\n${declarations.join("\n")}\nexport default workflow(${JSON.stringify(wf.existingId??"factory-"+wf.key)},${JSON.stringify(wf.name)})${wf.chain}${groups};`;
}

if (process.argv[1]===fileURLToPath(import.meta.url)) {
  const directory=new URL("./generated/",import.meta.url);
  mkdirSync(directory,{recursive:true});
  for(const wf of workflows) writeFileSync(new URL(wf.key+".js",directory),sdk(wf));
  console.log("Five SDK drafts generated without secret values.");
}
