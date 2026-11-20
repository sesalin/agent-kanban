// Pure scheduled coordination. No AI nodes and no agent wakeups.
import {writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const kanban='https://kanban-api.okehc.com/api/factory';
const bearer=`credentials:{httpBearerAuth:newCredential('N8N_RADARES_KANBAN','MhO6jMfbdNT6QcOg')}`;
const head=`import {workflow,node,trigger,newCredential} from '@n8n/workflow-sdk';\n`;
const request=(name,method,url,body)=>`node({type:'n8n-nodes-base.httpRequest',version:4.2,config:{name:${JSON.stringify(name)},parameters:{method:${JSON.stringify(method)},url:${JSON.stringify(url)},authentication:'genericCredentialType',genericAuthType:'httpBearerAuth',${body?`sendBody:true,specifyBody:'json',jsonBody:${JSON.stringify(body)},`:''}options:{timeout:240000}},${bearer},retryOnFail:true,maxTries:2,waitBetweenTries:5000}})`;
const schedule=(name,expressions)=>`trigger({type:'n8n-nodes-base.scheduleTrigger',version:1.2,config:${JSON.stringify({name,parameters:{rule:{interval:expressions.map(expression=>({field:'cronExpression',expression}))}}})}})`;

export const workflows=[
 {key:'errors',name:'Fábrica secuencial - Registrar fallos',description:'Registra workflow y ejecución fallidos en factory_runtime. No envía prompts ni expone cuerpos o claves de proveedores.',
  code:head+`const start=trigger({type:'n8n-nodes-base.errorTrigger',version:1,config:{name:'Fallo de fábrica'}});\nconst save=${request('Registrar fallo','POST',kanban+'/error',"={{ JSON.stringify({workflow_id:String($json.workflow?.id ?? 'unknown'),execution_id:String($json.execution?.id ?? 'activation')}) }}")};\nexport default workflow('seq-errors','Fábrica secuencial - Registrar fallos').add(start).to(save);`},
 {key:'coordinator',name:'Fábrica secuencial - Conciliar cada 5 minutos',description:'De 12:20 a 22:00 en Ciudad de México, concilia tarjetas, valida ZIP y despacha MVP, prospección y landing en paralelo tras GO y avanza estados en radars-n8n. Sin LLM ni avisos de arranque.',
  code:head+`const start=${schedule('Cada 5 minutos, 12:20–22:00',['0 20-59/5 12 * * *','0 */5 13-21 * * *','0 0 22 * * *'])};\nconst run=${request('Conciliar tarjetas y estados','POST',kanban+'/reconcile')};\nexport default workflow('seq-coordinator','Fábrica secuencial - Conciliar cada 5 minutos').add(start).to(run);`},
 {key:'telegram',name:'Fábrica secuencial - Entregar informe Telegram',description:'De 19:30 a 22:00 consulta el informe pendiente, lo entrega y confirma su message_id. Un fallo de Telegram conserva el informe para reintentar.',
  code:head+`const start=${schedule('Informes pendientes, 19:30–22:00',['0 30-59/5 19 * * *','0 */5 20-21 * * *','0 0 22 * * *'])};\nconst pending=node({type:'n8n-nodes-base.httpRequest',version:4.2,config:{name:'Leer informe pendiente',parameters:{method:'GET',url:'https://uobeshcvmtawjxibciuy.supabase.co/rest/v1/factory_daily_reports?sent_at=is.null&order=report_date.asc&limit=1',authentication:'predefinedCredentialType',nodeCredentialType:'supabaseApi',options:{timeout:15000}},credentials:{supabaseApi:newCredential('RADARS_SUPABASE','6tc6sprc6stOuXbn')},retryOnFail:true,maxTries:2,waitBetweenTries:5000}});\nconst send=node({type:'n8n-nodes-base.telegram',version:1.2,config:{name:'Enviar informe a Cheko',parameters:{resource:'message',operation:'sendMessage',chatId:'7946431920',text:'={{ $json.message.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;") }}',additionalFields:{appendAttribution:false,parse_mode:'HTML'}},credentials:{telegramApi:newCredential('Telegram Cheko','PBFnJlQqPiAUFCsH')}}});\nconst ack=${request('Confirmar entrega','POST',"={{ '"+kanban+"/reports/' + $('Leer informe pendiente').item.json.report_date + '/sent' }}","={{ JSON.stringify({message_id:Number($json.result?.message_id ?? $json.message_id)}) }}")};\nexport default workflow('seq-telegram','Fábrica secuencial - Entregar informe Telegram').add(start).to(pending).to(send).to(ack);`},
];
if(process.argv[1]===fileURLToPath(import.meta.url)){
 const out=new URL('./generated/',import.meta.url);mkdirSync(out,{recursive:true});
 for(const wf of workflows)writeFileSync(new URL('sequential-'+wf.key+'.js',out),wf.code);
 console.log('Generated three scheduled workflow sources; credentials are references only.');
}
