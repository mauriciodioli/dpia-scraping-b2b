/* Shared selector for task creation and the query source dialog. */
(()=>{
 'use strict';
 const key=()=> 'dpia-task-sources:'+currentEmail;
 function preference(){
  try{const value=JSON.parse(localStorage.getItem(key()));if(value&&['all','selected'].includes(value.mode)&&Array.isArray(value.ids)&&value.ids.every(x=>typeof x==='string')&&(value.mode==='all'?value.ids.length===0:value.ids.length>0))return value;}catch(_){}
  return {mode:'all',ids:[]};
 }
 function createSelector(initial=preference(),onchange=()=>{}){
  const element=document.createElement('section');element.className='task-source-settings';
  const title=document.createElement('h3');title.textContent='Conexiones de la tarea';
  const hint=document.createElement('p');hint.className='hint';hint.textContent='Elegí dónde puede operar tu tarea. Con todos los disponibles, el motor elige las herramientas necesarias en cada ejecución.';
  const list=document.createElement('div');list.className='task-source-options';
  const status=document.createElement('p');status.className='hint';status.setAttribute('role','status');
  const retry=document.createElement('button');retry.type='button';retry.className='action-button';retry.textContent='Reintentar conexiones';retry.hidden=true;
  element.append(title,hint,list,status,retry);
  let owner=null,serial=0,loaded=false,selected=structuredClone(initial);
  function read(){
   if(!loaded||owner!==currentEmail)throw Error('Esperá la carga de conexiones o reintentá antes de continuar.');
   const all=list.querySelector('[data-all-task-sources]').checked;
   const ids=[...list.querySelectorAll('[name=taskExecutionSource]:checked')].map(box=>box.value);
   if(!all&&!ids.length)throw Error('Elegí una conexión o utilizar todos los disponibles.');
   return {mode:all?'all':'selected',ids:all?[]:ids};
  }
  function changed(){try{selected=read();onchange(structuredClone(selected));}catch(_){}}
  function choice(text,value,checked){
   const label=document.createElement('label'),input=document.createElement('input'),span=document.createElement('span');
   label.className='task-source-choice';input.type='checkbox';input.value=value;input.checked=checked;input.onchange=changed;span.textContent=text;label.append(input,span);list.append(label);return input;
  }
  async function load(value){
   if(value)selected=structuredClone(value);
   const generation=++serial;owner=currentEmail;loaded=false;list.replaceChildren();status.textContent='Cargando conexiones de Agents…';retry.hidden=true;
   try{
    const response=await fetch('/api/agente/conexiones',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(20000)}),data=await response.json();
    if(generation!==serial||owner!==currentEmail)return;
    if(!response.ok||data.success!==true||!Array.isArray(data.items))throw Error(data.error||'No se pudieron cargar las conexiones.');
    const all=choice('Utilizar todos los disponibles','all',selected.mode==='all');all.dataset.allTaskSources='';
    for(const item of data.items){const box=choice(item.name+(item.kind==='mcp'?' · MCP':''),item.id,selected.mode==='selected'&&selected.ids.includes(item.id));box.name='taskExecutionSource';box.disabled=all.checked;}
    for(const id of selected.ids.filter(id=>!data.items.some(item=>item.id===id))){const box=choice('Conexión no disponible ('+id+')',id,true);box.name='taskExecutionSource';box.disabled=all.checked;}
    all.onchange=()=>{for(const box of list.querySelectorAll('[name=taskExecutionSource]'))box.disabled=all.checked;changed();};
    loaded=true;status.textContent=data.items.length?'La preferencia se guarda con la tarea.':'No hay conexiones disponibles actualmente. El motor volverá a comprobarlas al ejecutar la tarea.';
   }catch(error){if(generation===serial&&owner===currentEmail){status.textContent=error.message||'No se pudieron cargar las conexiones.';retry.hidden=false;}}
  }
  retry.onclick=()=>load();return {element,load,read};
 }
 const modal=document.getElementById('querySourcesModal'),selector=createSelector();
 if(modal)modal.querySelector('#confirmQuerySources').before(selector.element);
 function save(){
  try{localStorage.setItem(key(),JSON.stringify(selector.read()));return true;}catch(error){document.getElementById('querySourceError').textContent=error.message||'No se pudo guardar la preferencia de conexiones.';return false;}
 }
 window.DPIATaskSources={createSelector,load:()=>selector.load(preference()),save,preference};
})();
