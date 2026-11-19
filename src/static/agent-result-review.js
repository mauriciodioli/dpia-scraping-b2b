/* Display only: Agents owns classification, review and all task decisions. */
(()=>{'use strict';
 if(window.DPIAAgentResultUI)return;
 const labels={SATISFIED:'Objetivo satisfecho',PARTIAL:'Resultado parcial',DIVERGENT:'Resultado divergente',INSUFFICIENT_EVIDENCE:'Evidencia insuficiente',NO_MATCH:'Sin coincidencias',TECHNICAL_ERROR:'Error técnico'};
 const reviews={PENDING_REVIEW:'Pendiente de tu revisión',ACCEPTED:'Aceptado por vos',REJECTED:'Rechazado por vos',NOT_REQUIRED:'No requiere revisión humana'};
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
 const button=(text,action,cls='action-button')=>{const b=el('button',text,cls);b.type='button';b.onclick=action;return b;};
 const dialog=el('dialog',null,'agent-result-dialog'),header=el('div',null,'agent-result-header'),title=el('h2','Resultado'),content=el('div');dialog.id='result-dialog';title.id='result-title';content.id='result-content';dialog.setAttribute('aria-labelledby',title.id);
 const close=button('Cerrar',()=>dialog.close());close.id='close-result';const copy=button('Copiar contenido',async()=>{try{await navigator.clipboard.writeText(content.innerText);copy.textContent='Copiado';}catch(_){copy.textContent='Seleccioná el texto para copiarlo';}});copy.id='copy-result';header.append(title,copy,close);dialog.append(header,content);document.body.append(dialog);
 let owner=null,serial=0;dialog.addEventListener('close',()=>{serial++;content.replaceChildren();});
 const path=id=>'/api/consultas/historial/agentes/'+encodeURIComponent(id);
 async function request(url,method,body){const response=await fetch(url,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-DPIA-Action':'review-agent-result'},...(body?{body:JSON.stringify(body)}:{})});const data=await response.json();if(!response.ok||!data.success)throw Error(data.error||'No se pudo confirmar la acción. Reintentá.');return data;}
 function date(value){if(!value)return 'Sin fecha';const stamp=new Date(value);return Number.isNaN(stamp.getTime())?'Sin fecha':new Intl.DateTimeFormat(window.DPIAI18N?.language||'es',{dateStyle:'medium',timeStyle:'short'}).format(stamp);}
 function open(data,cards,reload,taskAction){owner=currentEmail;const run=++serial;copy.textContent='Copiar contenido';if(!dialog.open)dialog.showModal();
  const active=()=>run===serial&&dialog.open&&owner===currentEmail;
  function draw(value){if(!active())return;content.replaceChildren();const title=el('h3',labels[value.result_classification]||'Resultado guardado','agent-result-classification');title.dataset.classification=value.result_classification||'UNCLASSIFIED';
   const details=el('dl');const technical={FAILED:'Fallida',DELIVERED:'Entregada',REVIEWING:'En revisión',APPROVED:'Aprobada',READY_FOR_DELIVERY:'Lista para entrega'};
   const pairs=[['Estado técnico',technical[value.job_status]||value.job_status],['Clasificación',labels[value.result_classification]],['Motivo',value.classification_reason],['Decisión del Manager',value.manager_decision],['Objetivo original',value.objective],['Revisión humana',reviews[value.review_status]],['Revisado por',value.reviewed_by],['Fecha de revisión',value.reviewed_at?date(value.reviewed_at):null],['Motivo de revisión',value.review_reason]];
   for(const [label,text] of pairs)if(text)details.append(el('dt',label),el('dd',text));
   if(cards.some(card=>card.classList?.contains('agent-video-result'))){const disclosure=el('details',null,'agent-result-summary');disclosure.append(el('summary',title.textContent),details);content.append(disclosure);}
   else content.append(title,details);
   if(value.result_classification==='TECHNICAL_ERROR'){
    content.append(el('p',value.error_message,'agent-result-error'));const execution=value.execution||{};
    for(const [label,text] of [['Trabajo',value.job_id],['Código',value.error_code],['Creación',date(execution.created_at)],['Inicio',date(execution.started_at)],['Finalización',date(execution.finished_at)],['Fecha límite',date(execution.deadline_at)],['Progreso',execution.progress==null?'No disponible':execution.progress+'%']])details.append(el('dt',label),el('dd',text||'No registrado'));
    content.append(el('p','Esta corrida no se completó. No hay una respuesta final entregada.'));
   }
   for(const [key,label] of [['requirements_satisfied','Requisitos satisfechos'],['requirements_pending','Requisitos pendientes']])if(value[key]?.length){content.append(el('h4',label));for(const text of value[key])content.append(el('p',text));}
   content.append(...cards);
   const status=el('p',null,'agent-result-error');status.setAttribute('role','status');
   if(value.review_required&&value.review_status==='PENDING_REVIEW'){
    const label=el('label','Motivo del rechazo (opcional)'),reason=el('textarea');reason.maxLength=1000;label.append(reason);const actions=el('div',null,'agent-result-actions');
    const submit=async decision=>{actions.querySelectorAll('button').forEach(b=>b.disabled=true);status.textContent='Guardando revisión…';
     try{const saved=await request(path(value.job_id)+'/revision','POST',{result_id:value.result_id,decision,reason:decision==='REJECTED'?reason.value:''});if(!active())return;window.dispatchEvent(new CustomEvent('dpia:agent-result-reviewed',{detail:saved}));draw(saved);}
     catch(error){if(active()){status.textContent=error.message;actions.querySelectorAll('button').forEach(b=>b.disabled=false);}}
    };
    actions.append(button('Aceptar resultado',()=>submit('ACCEPTED'),'primary'),button('Rechazar resultado',()=>submit('REJECTED')));content.append(label,actions);
   }
   if(['PARTIAL','DIVERGENT','INSUFFICIENT_EVIDENCE','NO_MATCH','TECHNICAL_ERROR'].includes(value.result_classification)){
    if(value.result_classification==='NO_MATCH')content.append(el('p','No encontramos coincidencias para los criterios de esta tarea.'));
    if(value.task_id){const actions=el('div',null,'agent-result-actions');actions.append(button('Modificar tarea',async()=>{try{const info=await request(path(value.job_id)+'/tarea','GET');if(!active())return;const form=el('form'),nameLabel=el('label','Nombre de la tarea'),name=el('input'),instructionsLabel=el('label','Criterios e instrucciones'),instructions=el('textarea');name.value=info.task.configuration.name||info.task.name;name.maxLength=120;instructions.value=info.task.configuration.instructions||'';instructions.maxLength=8000;nameLabel.append(name);instructionsLabel.append(instructions);const save=button('Guardar cambios',async()=>{save.disabled=true;try{const configuration={...info.task.configuration,name:name.value,instructions:instructions.value,expected_revision:info.task.revision};await request(path(value.job_id)+'/tarea','PATCH',{configuration});if(active()){form.remove();status.textContent='Tarea actualizada. El historial de esta corrida se conserva.';}}catch(e){if(active()){status.textContent=e.message;save.disabled=false;}}});form.append(nameLabel,instructionsLabel,save,button('Cancelar',()=>form.remove()));content.append(form);}catch(e){if(active())status.textContent=e.message;}}),button('Eliminar tarea',async()=>{if(!window.confirm('¿Eliminar esta tarea y deshabilitar sus programaciones? Se conservará el historial.'))return;actions.querySelectorAll('button').forEach(b=>b.disabled=true);try{await request(path(value.job_id)+'/tarea','DELETE',{confirm:true});if(active()){actions.remove();status.textContent='Tarea eliminada. El historial se conserva.';}}catch(e){if(active()){status.textContent=e.message;actions.querySelectorAll('button').forEach(b=>b.disabled=false);}}}));content.append(actions);}
   }
   content.append(button('Actualizar estado',()=>{if(active())reload();}),status);
  }
  draw(data);
  if(taskAction){const name=taskAction==='edit'?'Modificar tarea':'Eliminar tarea';const target=[...content.querySelectorAll('button')].find(b=>b.textContent===name);if(target)target.click();}
 }
 new MutationObserver(()=>{if(dialog.open&&owner!==currentEmail)dialog.close();}).observe(document.getElementById('userBtn'),{childList:true,characterData:true,subtree:true});
 window.DPIAAgentResultUI={open,classificationLabel:key=>labels[key]||'Sin clasificación registrada',reviewLabel:key=>reviews[key]||'Estado no registrado'};
})();
