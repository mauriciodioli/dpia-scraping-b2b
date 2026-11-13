/* Configuration-only UI. No scheduler, scraping, AI, notifications or point mutations. */
(()=>{
 const root=document.getElementById('agentContent');
 let taskAgentId=null,taskExpanded=false,refreshTaskList=null;
 const TASKS={products:'Productos nuevos',prices:'Cambios de precios',suppliers:'Proveedores',local:'Oportunidades locales',jobs:'Oportunidades laborales',trends:'Tendencias'};
 const FREQUENCIES={daily:'Diario',twice:'Dos veces por semana',weekly:'Semanal'};
 const STATES={unconfigured:'No configurado',inactive:'Configurado e inactivo',active:'Activo',running:'Ejecutando',paused:'Pausado',admin_paused:'Pausado por administrador',disabled:'Deshabilitado',insufficient:'Créditos insuficientes',error:'Error'};
 const STEPS=['Qué monitorear','Dónde y sobre qué','Cuándo','Límites y notificaciones','Confirmación'];
 let waitingForSession=null;
 let pendingQueryContext=null,queryContext=null,wizard=false,index=0,draft=null,record=null,identity=null,scopes=[],categories=[],cities=[],loading=false,loadSerial=0,controller=null,error='',engineRevision=0,pauseReady=false,pendingPause=null,pendingDelete=null,agentPoints=null,availablePoints=null,budgetReadSerial=0,serverState='inactive',serverRevision=0,serverReady=false,serverBusy=false,readSerial=0;
 function pauseOperationId(){
  if(typeof crypto.randomUUID==='function')return crypto.randomUUID();
  const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');
  return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
 }
 const tr=text=>window.DPIAI18N?.translate(text)||text;
 const who=()=>typeof currentEmail==='string'?currentEmail:null;
 const key=()=> 'dpia-agent-config:v1:'+ (who()||'guest');
 function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined){el.textContent=tr(text);el.dataset.i18n=text;}if(className)el.className=className;return el;}
 function raw(tag,text,className){const el=document.createElement(tag);el.textContent=text;el.dataset.catalogName='';if(className)el.className=className;return el;}
 function button(text,handler,className='action-button'){const el=node('button',text,className);el.type='button';if(handler)el.onclick=handler;return el;}
 function inputLabel(text,control){control.setAttribute('aria-label',tr(text));control.setAttribute('data-i18n-aria-label',text);const label=node('label',undefined,'agent-field');label.append(node('span',text),control);return label;}
 function select(items,value,change){const el=document.createElement('select');for(const [id,text,translate=true] of items){const option=translate?node('option',text):raw('option',text);option.value=id;el.append(option);}el.value=value;el.onchange=()=>change(el.value);return el;}
 function timeZone(){return Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';}
 function validZone(value){try{new Intl.DateTimeFormat('en',{timeZone:value});return typeof value==='string';}catch(_){return false;}}
 function validLabels(value){return value===undefined||(Array.isArray(value)&&value.length<=500&&value.every(row=>row&&Number.isSafeInteger(row.id)&&row.id>0&&typeof row.name==='string'&&row.name.length<=500));}
 function valid(value){return value&&validLabels(value.scopeLabels)&&validLabels(value.categoryLabels)&&value.version===1&&Array.isArray(value.tasks)&&value.tasks.length>0&&value.tasks.every(t=>Object.hasOwn(TASKS,t))&&typeof value.country==='string'&&value.country.trim().length>0&&value.country.length<=100&&typeof value.city==='string'&&value.city.trim().length>0&&value.city.length<=100&&Array.isArray(value.scopes)&&(value.scopes.length>0||['explorar','novedades'].includes(value.query_context?.mode)&&value.categories?.length===0)&&value.scopes.length<=500&&value.scopes.every(v=>Number.isSafeInteger(v)&&v>0)&&Array.isArray(value.categories)&&(value.categories.length>0||['explorar','novedades'].includes(value.query_context?.mode)&&value.scopes?.length===0)&&value.categories.length<=500&&value.categories.every(v=>Number.isSafeInteger(v)&&v>0)&&Object.hasOwn(FREQUENCIES,value.frequency)&&Array.isArray(value.days)&&value.days.every(v=>Number.isInteger(v)&&v>=0&&v<=6)&&new Set(value.days).size===value.days.length&&(value.frequency==='daily'||value.days.length===(value.frequency==='twice'?2:1))&&/^\d{2}:\d{2}$/.test(value.time)&&Number(value.time.slice(0,2))<24&&Number(value.time.slice(3))<60&&validZone(value.timezone)&&Number.isSafeInteger(value.points)&&value.points>=0&&value.points<=1000000&&['week','month'].includes(value.period)&&typeof value.notifications==='boolean';}
 function readLocalDraft(){try{const result=JSON.parse(localStorage.getItem(key())||'null');return valid(result)?result:null;}catch(_){return null;}}
 function defaults(){return {version:1,tasks:[],country:typeof country==='string'?country:'',city:typeof city==='string'?city:'',scopes:[...selected].map(Number),categories:[],frequency:'weekly',days:[1],time:'09:00',timezone:timeZone(),points:0,period:'month',notifications:false};}
 function weekday(day){return new Intl.DateTimeFormat(window.DPIAI18N?.language||'es',{weekday:'long',timeZone:'UTC'}).format(new Date(Date.UTC(2026,10,1+day)));}
 function feedback(parent){if(error){const el=node('p',error,'agent-feedback');el.setAttribute('role','alert');parent.append(el);}}
 function statusBadge(state){const el=node('span',STATES[state]||STATES.error,'agent-status');el.dataset.state=state;return el;}
 function storageNotice(){return node('p','La configuración se guarda en tu cuenta DPIA. Guardarla no activa el agente.','agent-notice');}
 function engineNotice(){const el=node('p','La activación vincula tu agente con el servicio. Las búsquedas automáticas y los cargos siguen deshabilitados.','agent-notice');el.id='agentEngineNotice';return el;}
 function summary(config){
  const dl=document.createElement('dl');
  const names=(ids,list,field,saved)=>ids.map(id=>list.find(row=>row[field]===id)?.nombre||(saved||[]).find(row=>row.id===id)?.name||String(id)).join(', ');
  const rows=[['Tareas configuradas',config.tasks.map(id=>tr(TASKS[id])).join(', ')],['Ubicación',[config.city,config.country].filter(Boolean).join(', ')],['Ámbitos',names(config.scopes,scopes,'ambito_id',config.scopeLabels)],['Categorías',names(config.categories,categories,'categoria_id',config.categoryLabels)],['Frecuencia',tr(FREQUENCIES[config.frequency])],['Días',config.frequency==='daily'?tr('Todos los días'):config.days.map(weekday).join(', ')],['Horario',config.time+' · '+config.timezone],['Límite de puntos',String(config.points)+' / '+tr(config.period==='week'?'Por semana':'Por mes')],['Avisos de novedades',tr(config.notifications?'Solicitados, aún no disponibles':'Desactivados')]];
  for(const [label,value] of rows.filter(([label])=>!config.query_context||!['Ámbitos','Categorías'].includes(label)||config.scopes.length))dl.append(node('dt',label),raw('dd',value));return dl;
 }
 function pointIndicator(){
  const wrap=node('div',undefined,'agent-point-summary');wrap.setAttribute('aria-live','polite');
  const p=record?agentPoints:null;
  if(!record&&Number.isSafeInteger(availablePoints)){
   const status=node('span',undefined,'agent-point-status'),dot=node('span',undefined,'agent-point-dot');
   dot.dataset.color=availablePoints>0?'green':'red';dot.setAttribute('aria-hidden','true');
   status.append(dot,raw('span',availablePoints+' '+tr('puntos restantes')));wrap.append(status);return wrap;
  }
  if(!p||!Number.isSafeInteger(p.effective_remaining)||!Number.isSafeInteger(p.budget)||!Number.isSafeInteger(p.budget_consumed)||!Number.isSafeInteger(p.budget_reserved)){wrap.append(node('span','Puntos no disponibles'));return wrap;}
  const status=node('span',undefined,'agent-point-status'),dot=node('span',undefined,'agent-point-dot');
  dot.dataset.color=p.color;dot.setAttribute('aria-hidden','true');status.append(dot,raw('span',p.effective_remaining+' '+tr('puntos restantes')));
  wrap.append(status);return wrap;
 }
 function executionControl(state){
  const text=state==='paused'?'Reanudar agente':['active','running'].includes(state)?'Pausar agente':'Activar agente';
  const control=button(state==='admin_paused'?'Pausado por administrador':text,state==='inactive'?activate:togglePause,'primary');control.disabled=wizard||!record||!serverReady||serverBusy||!['inactive','active','paused'].includes(state)||(state!=='inactive'&&!pauseReady);if(wizard||!record)control.setAttribute('aria-describedby','agentEngineNotice');return control;
 }
 function dashboard(){
  root.replaceChildren();refreshTaskList=null;wizard=false;queryContext=null;
  const panel=node('div',undefined,who()?'agent-summary':'agent-intro');
  if(who()&&!serverReady){
   if(serverBusy)panel.append(node('p','Cargando configuración del agente…','hint'));
   else panel.append(button('Reintentar',open));
   feedback(panel);root.append(panel);return;
  }
  if(!who()){
   panel.append(statusBadge('unconfigured'));
   panel.append(node('h3','DPIA busca por vos'),node('p','Encontrá productos nuevos, cambios de precios, proveedores y oportunidades sin buscar todos los días'),button('Configurar mi agente',()=>who()?start():openAuth(),'primary'));
   if(who()&&readLocalDraft())panel.append(button('Recuperar borrador local',()=>start(readLocalDraft())));
   if(!who())panel.append(node('p','Iniciá sesión para guardar tu agente.','agent-notice'));
  }
  else{
   const header=node('div',undefined,'agent-identity'),logo=node('div',undefined,'consult-art agent-logo'),symbol=document.createElement('img');
   logo.dataset.active=String(!!record&&['active','running'].includes(serverState));
   symbol.className='dpia-symbol';symbol.src='/static/branding/favicon.png';symbol.alt='';symbol.setAttribute('aria-hidden','true');logo.append(symbol);
   const info=node('div',undefined,'agent-identity-info');info.append(raw('h3',who()),statusBadge(record?serverState:'unconfigured'),pointIndicator());header.append(logo,info);panel.append(header);
   panel.append(button('＋ Crear tarea',()=>window.DPIACrearTarea?.open(),'primary'));
    panel.append(taskPanel());
   if(record){
   const actions=node('div',undefined,'agent-actions');if(serverState==='inactive')actions.append(button('Editar configuración',()=>start()));
   actions.append(executionControl(serverState));const remove=button('Eliminar agente',deleteAgent,'agent-delete');remove.disabled=serverBusy||!!record.engine_binding&&!pauseReady;actions.append(remove);if(record.engine_binding)actions.append(button('Actualizar estado',()=>refreshPause()));panel.append(actions);
   }
  }
  if(!who())panel.append(engineNotice(),storageNotice());feedback(panel);root.append(panel);window.DPIAI18N?.refresh();
 }
 async function activate(){
  if(serverBusy||!record||serverState!=='inactive'||wizard)return;
  const owner=who(),serial=++readSerial;if(!owner){openAuth();return;}
  serverBusy=true;error='';dashboard();
  try{
   const response=await fetch('/api/agente/activar',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-DPIA-Action':'activate-agent'},body:JSON.stringify({expected_revision:serverRevision}),signal:AbortSignal.timeout(60000)});
   const data=await response.json();if(owner!==who()||serial!==readSerial)return;
   if(response.status===401)openAuth();
   if(!response.ok||data.success!==true)throw Error(data.error||'No se confirmó la activación del agente. Reintentá.');
   if(!data.agent||data.agent.state!=='active'||data.agent.revision!==serverRevision||!valid(data.agent.configuration)||!data.agent.configuration.engine_binding?.id||data.execution_available!==false)throw Error('La respuesta del agente no es válida. Volvé a cargar su configuración.');
   record=data.agent.configuration;serverState='active';engineRevision=record.engine_binding.revision;pauseReady=false;
  }catch(e){if(owner===who()&&serial===readSerial)error=e.name==='Error'?e.message:'No se confirmó la activación del agente. Reintentá.';}
  finally{if(owner===who()&&serial===readSerial){serverBusy=false;dashboard();if(serverState==='active')refreshPause();}}
 }
 async function deleteAgent(){
  if(serverBusy||!record||record.engine_binding&&!pauseReady)return;
  if(!pendingDelete&&!window.confirm('¿Eliminar tu agente? Se conservará el historial y se cancelarán los trabajos no iniciados.'))return;
  const owner=who(),serial=readSerial;
  pendingDelete=pendingDelete||{confirm:true,expected_revision:serverRevision,engine_revision:record.engine_binding?engineRevision:null,operation_id:pauseOperationId()};
  serverBusy=true;error='';dashboard();
  try{
   const response=await fetch('/api/agente/eliminar',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-DPIA-Action':'delete-agent'},body:JSON.stringify(pendingDelete),signal:AbortSignal.timeout(20000)});
   const data=await response.json();if(owner!==who()||serial!==readSerial)return;
   if(!response.ok||data.success!==true){if([400,401,403,404,409].includes(response.status))pendingDelete=null;throw Error(data.error||'No se confirmó la eliminación. Reintentá.');}
   if(data.execution_available!==false||data.agent!==null)throw Error('Volvé a cargar la configuración antes de continuar.');
   record=null;serverRevision=0;engineRevision=0;pauseReady=false;pendingPause=null;pendingDelete=null;serverState='inactive';
  }catch(e){if(owner===who()&&serial===readSerial)error=e.name==='Error'?e.message:'No se confirmó la eliminación. Reintentá.';}
  finally{if(owner===who()&&serial===readSerial){serverBusy=false;dashboard();}}
 }
 function acceptPause(data){
  const agent=data.agent;agentPoints=data.points||null;
  if(data.success===true&&data.execution_available===false&&agent===null){record=null;serverRevision=0;engineRevision=0;pauseReady=false;pendingPause=null;pendingDelete=null;serverState='inactive';return;}
  if(data.success!==true||data.execution_available!==false||!agent||!['active','paused','admin_paused','disabled'].includes(agent.state)||agent.revision!==serverRevision||agent.configuration?.engine_binding?.id!==record?.engine_binding?.id||!Number.isSafeInteger(agent.engine_revision)||agent.engine_revision<1)throw Error('No se confirmó el estado del agente.');
  serverState=agent.state;engineRevision=agent.engine_revision;pauseReady=true;
 }
 async function refreshPause(){
  if(!record||serverBusy||wizard||!who()||pendingPause)return;
  const owner=who(),serial=readSerial,before=JSON.stringify([record,serverState,engineRevision,pauseReady,agentPoints,error]);serverBusy=true;
  try{
   const response=await fetch(record.engine_binding?'/api/agente/pausa':'/api/agente/configuracion',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(20000)});
   const data=await response.json();if(owner!==who()||serial!==readSerial)return;
   if(!response.ok||data.success!==true)throw Error(data.error||'No se confirmó el estado del agente.');
   if(record.engine_binding||data.agent===null)acceptPause(data);else{if(data.agent.revision!==serverRevision)throw Error('La configuración cambió. Volvé a cargarla.');agentPoints=data.points||null;}error='';
  }catch(e){if(owner===who()&&serial===readSerial){pauseReady=false;error=e.name==='Error'?e.message:'No se confirmó el estado del agente.';}}
  finally{if(owner===who()&&serial===readSerial){serverBusy=false;
   if(before!==JSON.stringify([record,serverState,engineRevision,pauseReady,agentPoints,error]))dashboard();
   else refreshTaskList?.();}}
 }
 async function togglePause(){
  if(serverBusy||!pauseReady||!['active','paused'].includes(serverState))return;
  const owner=who(),serial=readSerial;
  pendingPause=pendingPause||{paused:serverState==='active',expected_revision:engineRevision,operation_id:pauseOperationId()};
  serverBusy=true;error='';dashboard();
  try{
   const response=await fetch('/api/agente/pausa',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-DPIA-Action':'pause-agent'},body:JSON.stringify(pendingPause),signal:AbortSignal.timeout(20000)});
   const data=await response.json();if(owner!==who()||serial!==readSerial)return;
   if(!response.ok||data.success!==true){if([401,403,409].includes(response.status)){pendingPause=null;pauseReady=false;}throw Error(data.error||'No se confirmó la pausa. Reintentá.');}
   acceptPause(data);pendingPause=null;
  }catch(e){if(owner===who()&&serial===readSerial)error=e.name==='Error'?e.message:'No se confirmó la pausa. Reintentá.';}
  finally{if(owner===who()&&serial===readSerial){serverBusy=false;dashboard();}}
 }
 async function json(url){const r=await fetch(url,{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error('catalog');const data=await r.json();if(data.success!==true)throw Error('catalog');return data;}
 async function loadLocation(reloadCities=true){
  const serial=++loadSerial,owner=who();controller?.abort();controller=new AbortController();loading=true;error='';
  if(index===1&&wizard)renderStep();
  try{
   if(reloadCities){const data=await json('/api/catalogos/ciudades?'+new URLSearchParams({pais:draft.country}));if(serial!==loadSerial||owner!==who())return;cities=(data.ciudades||[]).map(row=>row.nombre);if(!cities.includes(draft.city))draft.city='';}
   if(draft.city){
    const data=await json('/api/catalogos/ubicacion?'+new URLSearchParams({pais:draft.country,ciudad:draft.city,idioma:window.DPIAI18N?.language||'es'}));
    if(serial!==loadSerial||owner!==who())return;
    scopes=data.ambitos||[];categories=data.categorias||[];
    draft.scopes=draft.scopes.filter(id=>scopes.some(row=>row.ambito_id===id));pruneCategories();
   }else{scopes=[];categories=[];draft.scopes=[];draft.categories=[];}
  }catch(e){if(e.name!=='AbortError'&&serial===loadSerial)error='No se pudo cargar el catálogo del agente. Reintentá.';}
  finally{if(serial===loadSerial&&owner===who()){loading=false;if(wizard&&index===1)renderStep();}}
 }
 function pruneCategories(){draft.categories=draft.categories.filter(id=>categories.some(row=>row.categoria_id===id&&row.ambito_ids.some(scope=>draft.scopes.includes(scope))));}
 function start(imported=null){
  if(!who()){openAuth();return;}
  if(!serverReady||serverBusy)return;
  queryContext=null;identity=who();draft=record?structuredClone(record):imported?structuredClone(imported):defaults();wizard=true;index=0;error='';
  scopes=structuredClone(catalogAmbitos);categories=structuredClone(catalogCategorias);cities=draft.city?[draft.city]:[];
  refreshBudgetLimit();renderStep();if(draft.country)loadLocation();
 }
 function fromQuery(context){
  if(!who()||context?.owner!==who()){openAuth();return false;}
  if(serverBusy){notify('Esperá a que termine la carga del agente.');return false;}
  pendingQueryContext=structuredClone(context);show('agentPage');return true;
 }
 function startQueryContext(context){
  queryContext=context;identity=who();wizard=true;index=2;error='';
  draft={...defaults(),...(record||{}),version:1,tasks:[context.taskType||((context.category?.name?.toLowerCase().includes('laboral')||context.prompt?.toLowerCase().includes('empleo'))?'jobs':'products')],query_context:structuredClone(context.query_context),country:context.country,city:context.city,scopes:context.scope?[context.scope.id]:[],categories:context.category?[context.category.id]:[],language:context.language,scopeLabels:context.scope?[context.scope]:[],categoryLabels:context.category?[context.category]:[]};
  scopes=structuredClone(catalogAmbitos);categories=structuredClone(catalogCategorias);cities=[context.city];

  refreshBudgetLimit();renderStep();root.querySelector('h3')?.focus();
 }
 function choice(parent,text,checked,change,translated=true){const label=node('label',undefined,'agent-choice'),check=document.createElement('input');check.type='checkbox';check.checked=checked;check.onchange=()=>change(check.checked);label.append(check,translated?node('span',text):raw('span',text));parent.append(label);}
 function listHeading(parent,text){parent.append(node('h4',text,'agent-label'));const choices=node('div',undefined,'agent-choices agent-catalog');parent.append(choices);return choices;}
 function toggle(list,value,checked){if(checked&&!list.includes(value))list.push(value);if(!checked){const at=list.indexOf(value);if(at>=0)list.splice(at,1);}}
 function stepLocation(panel){
  const fields=node('div',undefined,'agent-fields');
  const countries=[...document.querySelectorAll('#countryList [data-country]')].map(el=>[el.dataset.country,el.textContent,false]);
  fields.append(inputLabel('País',select([['','Elegí un país'],...countries],draft.country,value=>{draft.country=value;draft.city='';draft.scopes=[];draft.categories=[];scopes=[];categories=[];cities=[];if(value)loadLocation();else renderStep();})),inputLabel('Ciudad',select([['','Elegí tu ciudad'],...cities.map(name=>[name,name,false])],draft.city,value=>{draft.city=value;draft.scopes=[];draft.categories=[];scopes=[];categories=[];loadLocation(false);})));
  panel.append(fields);
  if(loading){panel.append(node('p','Cargando catálogo…','hint'));return;}
  if(error){panel.append(button('Reintentar',()=>loadLocation()));return;}
  if(!draft.city){panel.append(node('p','Elegí un país y una ciudad para cargar las opciones.','hint'));return;}
  const scopeList=listHeading(panel,'Ámbitos');for(const item of scopes)choice(scopeList,item.nombre,draft.scopes.includes(item.ambito_id),checked=>{toggle(draft.scopes,item.ambito_id,checked);pruneCategories();renderStep();},false);
  const categoryList=listHeading(panel,'Categorías');const available=categories.filter(item=>item.ambito_ids.some(id=>draft.scopes.includes(id)));
  for(const item of available)choice(categoryList,item.nombre,draft.categories.includes(item.categoria_id),checked=>toggle(draft.categories,item.categoria_id,checked),false);
  if(!scopes.length||!available.length)panel.append(node('p','No hay opciones disponibles para esta selección.','hint'));
 }
 function stepWhen(panel){
  const fields=node('div',undefined,'agent-fields');const time=document.createElement('input');time.type='time';time.value=draft.time;time.oninput=()=>draft.time=time.value;
  const zones=[...new Set([timeZone(),draft.timezone,'UTC',...(Intl.supportedValuesOf?Intl.supportedValuesOf('timeZone'):[])])];
  fields.append(inputLabel('Frecuencia',select(Object.entries(FREQUENCIES),draft.frequency,value=>{draft.frequency=value;draft.days=value==='twice'?[1,4]:[1];renderStep();})),inputLabel('Horario',time),inputLabel('Zona horaria',select(zones.map(z=>[z,z,false]),draft.timezone,z=>draft.timezone=z)));panel.append(fields);
  if(draft.frequency!=='daily'){
   const days=listHeading(panel,draft.frequency==='twice'?'Elegí dos días':'Elegí un día');
   for(const day of [1,2,3,4,5,6,0])choice(days,weekday(day),draft.days.includes(day),checked=>toggle(draft.days,day,checked),false);
  }
  panel.append(node('p',queryContext&&record?'La tarea se agrega pausada. Podés activarla desde Mis tareas después de guardarla.':'El horario es una preferencia. No hay tareas programadas todavía.','agent-notice'));
 }
 async function refreshBudgetLimit(){
  const owner=who(),serial=++budgetReadSerial;availablePoints=null;
  if(wizard&&index===3)renderStep();
  try{
   const response=await fetch('/api/consultas/creditos',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15000)});
   const data=await response.json();if(owner!==who()||serial!==budgetReadSerial)return;
   if(!response.ok||data.success!==true||!Number.isSafeInteger(data.credits?.available)||data.credits.available<0)throw Error('credits');
   availablePoints=data.credits.available;
  }catch(e){if(owner===who()&&serial===budgetReadSerial)availablePoints=null;}
  finally{if(owner===who()&&serial===budgetReadSerial){
   if(wizard&&index===3)renderStep();
   else if(!record&&serverReady&&!serverBusy&&!document.getElementById('agentPage').hidden&&!wizard)dashboard();
  }}
 }
 function stepLimits(panel){
  const maximum=availablePoints===null?0:Math.min(1000000,availablePoints);
  if(availablePoints!==null&&draft.points>maximum)draft.points=maximum;
  const fields=node('div',undefined,'agent-fields'),points=document.createElement('input');points.type='number';points.min='0';points.max=String(maximum);points.step='1';points.disabled=availablePoints===null;points.value=draft.points;
  points.oninput=()=>{draft.points=points.value===''?null:Number(points.value);if(draft.points>maximum){draft.points=maximum;points.value=String(maximum);}};
  if(availablePoints===null)panel.append(node('p','Consultá el saldo para configurar el presupuesto.','hint'),button('Consultar saldo',refreshBudgetLimit));
  else panel.append(raw('p',tr('Puntos disponibles')+': '+availablePoints,'hint'));
  fields.append(inputLabel('Presupuesto máximo de puntos',points),inputLabel('Período',select([['week','Por semana'],['month','Por mes']],draft.period,value=>draft.period=value)));panel.append(fields);
  choice(panel,'Recibir avisos de novedades',draft.notifications,value=>draft.notifications=value);
  panel.append(node('p','Las búsquedas externas pueden consumir puntos. Guardar esta configuración no descuenta puntos ni reserva saldo.','agent-notice'),node('p','Los avisos se guardan como preferencia; no se solicitará permiso ni se enviarán notificaciones en esta etapa.','agent-notice'));
 }
 function check(step){

  if(step===0&&!draft.tasks.length)return 'Seleccioná al menos una tarea.';
  if(step===1&&(loading||(!queryContext&&error)||!draft.country||!draft.city||(!queryContext&&(!draft.scopes.length||!draft.categories.length))))return 'Elegí ubicación, ámbitos y categorías disponibles.';
  if(step===2&&(!/^\d{2}:\d{2}$/.test(draft.time)||!validZone(draft.timezone)||(draft.frequency!=='daily'&&draft.days.length!==(draft.frequency==='twice'?2:1))))return 'Revisá el horario y los días seleccionados.';
  if(step===3&&!(queryContext&&record)&&availablePoints===null)return 'No se pudo consultar tu saldo. Reintentá antes de guardar.';
  if(step===3&&!(queryContext&&record)&&draft.points>availablePoints)return 'El presupuesto supera tus puntos disponibles.';
  if(step===3&&(!Number.isSafeInteger(draft.points)||draft.points<0||draft.points>1000000))return 'Ingresá un límite de puntos entero y no negativo.';
  return '';
 }
 async function save(){
  if(serverBusy)return;
  if(identity!==who()){error='La cuenta cambió. Volvé a abrir la configuración.';renderStep();return;}
  if(!who()){openAuth();return;}
  for(let step=0;step<4;step++){const issue=check(step);if(issue){index=step;error=issue;renderStep();return;}}
  const value={...structuredClone(draft),version:1,language:window.DPIAI18N?.language||'es'};
  const fields=new Set(['version','tasks','country','city','scopes','categories','frequency','days','time','timezone','points','period','notifications','language','query_context']);
  for(const field of Object.keys(value))if(!fields.has(field))delete value[field];
  if(!valid(value)){error='La configuración guardada no es válida. Revisala antes de guardar.';renderStep();return;}
  const owner=who(),serial=++readSerial;serverBusy=true;error='';renderStep();
  try{
   const adding=!!(queryContext&&record);
   const response=await fetch(adding?'/api/agente/tareas':'/api/agente/configuracion',{method:adding?'POST':'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json','X-DPIA-Action':adding?'create-task':'configure-agent'},body:JSON.stringify(adding?{configuration:value}:{configuration:value,expected_revision:serverRevision}),signal:AbortSignal.timeout(60000)});
   const data=await response.json();
   if(owner!==who()||serial!==readSerial)return;
   if(response.status===401)openAuth();
   if(!response.ok||data.success!==true)throw Error(data.error||'No se confirmó el guardado del agente. Volvé a cargar su configuración.');
   if(adding){serverBusy=false;queryContext=null;dashboard();refreshPause();return;}
   if(!data.agent||!valid(data.agent.configuration)||!Number.isSafeInteger(data.agent.revision)||data.agent.revision<1||data.agent.state!=='inactive'||data.execution_available!==false)throw Error('La respuesta del agente no es válida. Volvé a cargar su configuración.');
   taskAgentId=data.agent.id;serverState=data.agent.state;record=data.agent.configuration;serverRevision=data.agent.revision;serverReady=true;loadSerial++;controller?.abort();
   agentPoints=null;serverBusy=false;dashboard();refreshPause();
  }catch(e){
   if(owner===who()&&serial===readSerial){error=e.message&&e.name==='Error'?e.message:'No se confirmó el guardado del agente. Volvé a cargar su configuración.';serverBusy=false;renderStep();}
  }finally{if(owner===who()&&serial===readSerial)serverBusy=false;}
 }
 function renderStep(){
  root.replaceChildren();const panel=node('div',undefined,'agent-wizard'),progress=document.createElement('ol');progress.className='agent-progress';progress.setAttribute('aria-label',tr('Pasos'));
  for(let i=0;i<5;i++){const li=document.createElement('li');li.setAttribute('aria-label',(i+1)+' · '+tr(STEPS[i]));if(i===index)li.setAttribute('aria-current','step');if(i<index)li.className='agent-complete';progress.append(li);}panel.append(progress,raw('small',(index+1)+' / 5'));const heading=node('h3',STEPS[index]);heading.tabIndex=-1;panel.append(heading);
  if(queryContext){const context=node('details',undefined,'agent-query-context');context.open=true;context.append(node('summary','Consulta preparada'),raw('pre',queryContext.summary));if(queryContext.issue)context.append(node('p',queryContext.issue,'agent-feedback'));panel.append(context);}
  if(index===0){const tasks=node('div',undefined,'agent-choices');for(const [id,text] of Object.entries(TASKS))choice(tasks,text,draft.tasks.includes(id),checked=>toggle(draft.tasks,id,checked));panel.append(tasks);}
  if(index===1)stepLocation(panel);if(index===2)stepWhen(panel);if(index===3)stepLimits(panel);
  if(index===4){panel.classList.add('agent-summary');panel.append(summary(draft),engineNotice(),storageNotice());}
  if(serverBusy){const status=node('p','Guardando configuración…','hint');status.setAttribute('role','status');panel.append(status);}
  feedback(panel);const actions=node('div',undefined,'agent-actions');
  actions.append(button('Cancelar',()=>{loadSerial++;controller?.abort();dashboard();}));
  if(index>(queryContext?2:0))actions.append(button('Anterior',()=>{index--;error='';renderStep();}));
  const next=button(index===4?(queryContext?(record?'Agregar tarea a mi agente':'Crear tarea'):'Crear agente'):'Siguiente',()=>{if(index===4){save();return;}const issue=check(index);if(issue){error=issue;renderStep();return;}error='';index++;renderStep();root.querySelector('h3').focus();},'primary');next.disabled=(index===1&&loading);actions.append(next);
  if(index===4)actions.append(executionControl('inactive'));
  if(error&&index===4)actions.append(button('Volver a cargar configuración',open));
  panel.append(actions);if(serverBusy)panel.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);root.append(panel);window.DPIAI18N?.refresh();
 }
 async function open(){
  // show() can run before this module or before /auth/me completes on reload.
  // Coalesce navigation and the identity observer while restoring that session.
  if(window.DPIAAuthReady){
   const ready=window.DPIAAuthReady;
   if(waitingForSession===ready)return;
   waitingForSession=ready;
   const status=node('p','Restaurando sesión…','hint');status.setAttribute('role','status');
   if(!serverBusy)root.replaceChildren(status);
   try{await ready;}
   catch(e){
    if(window.DPIAAuthReady===ready&&!document.getElementById('agentPage').hidden){
     const message=node('p','No se pudo restaurar la sesión. Reintentá.','agent-feedback');message.setAttribute('role','alert');
     root.replaceChildren(message,button('Reintentar',()=>{initAuth();open();}));
    }
    return;
   }finally{if(waitingForSession===ready)waitingForSession=null;}
   if(document.getElementById('agentPage').hidden)return;
  }
  if(serverBusy&&identity===who())return;
  identity=who();const owner=who(),serial=++readSerial;agentPoints=null;availablePoints=null;budgetReadSerial++;engineRevision=0;pauseReady=false;pendingPause=null;pendingDelete=null;serverState='inactive';record=null;serverRevision=0;serverReady=false;error='';
  loadSerial++;controller?.abort();loading=false;
  if(!owner){serverBusy=false;dashboard();return;}
  serverBusy=true;dashboard();
  try{
   const response=await fetch('/api/agente/configuracion',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15000)});
   const data=await response.json();if(owner!==who()||serial!==readSerial)return;
   if(response.status===401)openAuth();
   if(!response.ok||data.success!==true)throw Error(data.error||'No se pudo cargar la configuración del agente.');
   if(data.execution_available!==false)throw Error('La respuesta del agente no es válida. Volvé a cargar su configuración.');
   if(data.agent!==null){
   if(!data.agent||!valid(data.agent.configuration)||!Number.isSafeInteger(data.agent.revision)||data.agent.revision<1||!['inactive','active'].includes(data.agent.state))throw Error('La respuesta del agente no es válida. Volvé a cargar su configuración.');
    taskAgentId=data.agent.id;serverState=data.agent.state;record=data.agent.configuration;serverRevision=data.agent.revision;
   }
   agentPoints=data.points||null;serverReady=true;
  }catch(e){if(owner===who()&&serial===readSerial)error=e.name==='Error'?e.message:'No se pudo cargar la configuración del agente.';}
  finally{if(owner===who()&&serial===readSerial){serverBusy=false;dashboard();const context=pendingQueryContext;pendingQueryContext=null;if(serverReady&&context?.owner===owner)startQueryContext(context);else if(record?.engine_binding)refreshPause();else if(serverReady&&!record&&owner)refreshBudgetLimit();}}
 }
 setInterval(()=>{if(!document.hidden&&!document.getElementById('agentPage').hidden)refreshPause();},15000);
 new MutationObserver(()=>{if(identity!==who()){
  loadSerial++;readSerial++;controller?.abort();serverBusy=false;serverReady=false;serverRevision=0;
  pendingQueryContext=null;queryContext=null;identity=who();agentPoints=null;availablePoints=null;budgetReadSerial++;engineRevision=0;pauseReady=false;pendingPause=null;pendingDelete=null;record=null;draft=null;wizard=false;root.replaceChildren();
  if(!document.getElementById('agentPage').hidden)open();
 }}).observe(document.getElementById('userBtn'),{childList:true,subtree:true,characterData:true});
 window.addEventListener('dpia:credits-updated',()=>{if(wizard)refreshBudgetLimit();else if(!document.getElementById('agentPage').hidden){if(record)refreshPause();else if(who()&&serverReady)refreshBudgetLimit();}else agentPoints=null;});
 document.getElementById('languageSelect').addEventListener('change',()=>setTimeout(()=>{if(wizard){renderStep();if(draft.country&&draft.city)loadLocation(false);}else if(!document.getElementById('agentPage').hidden)dashboard();},0));
 function taskPanel(){
  const details=node('details',undefined,'agent-task-list'),heading=node('summary'),body=node('div');
  details.open=taskExpanded;details.ontoggle=()=>{taskExpanded=details.open;};
  heading.append(node('span','Mis tareas'),raw('span',record?' (…) ▾':' (0) ▾'));details.append(heading,body);
  if(!record){body.append(node('p','No hay tareas configuradas.'));return details;}
  const owner=who(),agentId=taskAgentId;
  let busy=false,editing=false,lastTasks=null;
  const current=()=>owner===who()&&agentId===taskAgentId&&details.isConnected;
  async function load(taskId=null,action=null,silent=false){
   if(busy||editing||!agentId)return;busy=true;body.setAttribute('aria-busy','true');
   const disabled=new Map();
   if(!silent)body.querySelectorAll('button').forEach(el=>{disabled.set(el,el.disabled);el.disabled=true;});
   const status=node('p','Cargando tareas…');status.setAttribute('role','status');if(!silent)body.append(status);
   try{
    const suffix=action?'/'+taskId+(action==='eliminar'?'':'/'+action):'';
    const response=await fetch('/api/agentes/'+agentId+'/tareas'+suffix,{method:action?(action==='eliminar'?'DELETE':'PATCH'):'GET',credentials:'same-origin',cache:'no-store',headers:{'X-DPIA-Action':'manage-task'},signal:AbortSignal.timeout(20000)});
    const data=await response.json();if(!current())return;
    if(!response.ok||data.success!==true)throw Error(data.error||'No se confirmó el cambio de tareas. Reintentá.');
    const tasks=[...data.tasks].sort((a,b)=>Number(b.state==='active')-Number(a.state==='active')||(b.created_at||'').localeCompare(a.created_at||'')||b.id-a.id);
    const fingerprint=JSON.stringify(tasks);if(fingerprint===lastTasks)return;
    lastTasks=fingerprint;
    heading.replaceChildren(node('span','Mis tareas'),raw('span',' ('+data.count+') ▾'));body.replaceChildren();
    if(!data.tasks.length)body.append(node('p','No hay tareas configuradas.'));
    const date=value=>value?new Intl.DateTimeFormat(window.DPIAI18N?.language||'es',{dateStyle:'short',timeStyle:'short'}).format(new Date(value+'Z')):tr('Sin datos');
    const types={PRODUCTOS_NUEVOS:'products',PRECIOS:'prices',PROVEEDORES:'suppliers',OPORTUNIDADES_LOCALES:'local',EMPLEOS:'jobs',TENDENCIAS:'trends'};
    const frequencies={DIARIA:'Diario',DAILY:'Diario',SEMANAL:'Semanal',WEEKLY:'Semanal',DOS_POR_SEMANA:'Dos veces por semana'};
    for(const task of tasks){
     const card=node('article',undefined,'agent-task-card');
     const title=raw('h4',task.name||tr(TASKS[types[task.type]]||task.type)),titleRow=node('div',undefined,'agent-task-title');
     const pencil=button('✎',()=>{
      if(editing||busy)return;editing=true;
      const editor=node('div',undefined,'agent-task-name-editor'),input=document.createElement('input'),error=node('p');
      input.type='text';input.maxLength=120;input.required=true;input.value=task.name||title.textContent;
      input.setAttribute('aria-label',tr('Nombre de la tarea'));error.setAttribute('role','alert');
      const counter=raw('small',''),updateCounter=()=>{counter.textContent=Array.from(input.value).length+' / 120';};
      input.oninput=()=>{input.setCustomValidity('');error.textContent='';updateCounter();};updateCounter();
      let saving=false;
      const close=async()=>{
       if(saving||!current())return;
       const name=input.value.trim();
       if(name===task.name){editor.remove();titleRow.hidden=false;editing=false;pencil.focus();return;}
       if(!name||Array.from(name).length>120){error.textContent=tr('El nombre debe tener entre 1 y 120 caracteres.');return;}
       saving=true;input.disabled=true;done.disabled=true;
       try{
        const response=await fetch('/api/agentes/'+agentId+'/tareas/'+task.id+'/renombrar',{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json','X-DPIA-Action':'manage-task'},body:JSON.stringify({name,expected_revision:task.revision||1}),signal:AbortSignal.timeout(20000)});
        const data=await response.json();if(!current())return;
        if(!response.ok||data.success!==true)throw Error(data.error||'No se guardó el nombre. Reintentá.');
        const saved=data.tasks.find(item=>item.id===task.id);task.name=saved.name;task.revision=saved.revision;title.textContent=saved.name;
        lastTasks=null;editor.remove();titleRow.hidden=false;editing=false;pencil.focus();
       }catch(e){if(current())error.textContent=e.message||tr('No se guardó el nombre. Reintentá.');}
       finally{saving=false;input.disabled=false;done.disabled=false;}
      };
      const done=button('Cerrar',close);input.onblur=close;
      input.onkeydown=event=>{if(event.key==='Enter'||event.key==='Escape'){event.preventDefault();close();}};
      editor.append(input,counter,done,error);titleRow.hidden=true;titleRow.after(editor);input.focus();input.select();
     });
     pencil.setAttribute('aria-label',tr('Cambiar nombre de la tarea'));pencil.title=tr('Cambiar nombre de la tarea');
     titleRow.append(title,pencil);card.append(titleRow,node('p',TASKS[types[task.type]]||task.type),statusBadge(task.state));
     const dl=document.createElement('dl');
     for(const timing of task.schedules){
      const rows=[['Frecuencia',tr(frequencies[timing.frequency]||timing.frequency||'Sin datos')],['Días',(timing.days||[]).map(day=>weekday(day%7)).join(', ')||tr('Sin datos')],['Horario',timing.time||tr('Sin datos')],['Zona horaria',timing.timezone||tr('Sin datos')],['Próxima ejecución',date(timing.next_run_at)]];
      for(const [label,value] of rows.filter(([label])=>!config.query_context||!['Ámbitos','Categorías'].includes(label)||config.scopes.length))dl.append(node('dt',label),raw('dd',value));
     }
     dl.append(node('dt','Última ejecución'),raw('dd',date(task.last_run_at)));
     if(task.points_consumed!==null)dl.append(node('dt','Puntos consumidos'),raw('dd',String(task.points_consumed)));
     const actions=node('div',undefined,'agent-actions');
     for(const [action,label] of [['activar','Activar'],['pausar','Pausar'],['eliminar','Eliminar']]){
      const control=button(label,()=>{if(action==='eliminar'&&!window.confirm(tr('¿Eliminar esta tarea? Se conservará el historial.')))return;load(task.id,action);});
      control.disabled=action==='activar'&&task.state==='active'||action==='pausar'&&task.state==='paused';actions.append(control);
     }
     card.append(dl,actions);body.append(card);
    }
   }catch(e){if(current()&&!silent){const message=node('p',e.message||'No se confirmó el cambio de tareas. Reintentá.');message.setAttribute('role','alert');body.append(message,button('Reintentar',()=>load()));}}
   finally{busy=false;status.remove();for(const [el,value] of disabled)if(el.isConnected)el.disabled=value;body.removeAttribute('aria-busy');}
  }
  refreshTaskList=()=>{if(current())load(null,null,true);};
  // Read once mounted; detached responses are discarded on account or dashboard changes.
  setTimeout(()=>{if(current())load();},0);
  return details;
 }
 // Future service may reuse these visual state definitions. No state can activate a task here.
 window.DPIAAgent={open,fromQuery,presentationFor:state=>({label:tr(STATES[state]||STATES.error),canEdit:state!=='running',showPause:['active','running'].includes(state),showResume:state==='paused',executionControlsEnabled:false})};
 // The initial show() may have preceded registration of DPIAAgent.
 if(!document.getElementById('agentPage').hidden)open();
 if(typeof syncQueryConversation==='function')syncQueryConversation();
})();
