/* Single-button clarification flow for start/jobs. No new send control. */
(()=>{'use strict';
 const button=document.getElementById('preparePrompt'),input=document.getElementById('promptText'),root=document.getElementById('queryConversation');
 if(!button||!input||!root)return;
 const relevant=()=>typeof queryJourney!=='undefined'&&['start','jobs'].includes(queryJourney);
 const action=()=>({explorar:'explore',novedades:'novel',local:'local',buscar:'search'})[typeof queryMode!=='undefined'?queryMode:'buscar']||'search';
 const identity=()=>JSON.stringify([queryJourney,action(),typeof currentEmail!=='undefined'?currentEmail:null]);
 const messages=document.createElement('div');messages.id='intentChatMessages';messages.className='intent-chat-messages';messages.setAttribute('role','log');messages.setAttribute('aria-live','polite');
 const preview=document.createElement('section');preview.id='intentTaskPreview';preview.className='intent-task-preview';preview.setAttribute('aria-live','polite');
 const field=input.closest('.query-chat-field')||input.parentElement;
 field.insertBefore(messages,input);const ready=document.getElementById('queryReadyPanel');ready?.parentElement?.insertBefore(preview,ready);
 let conversation=[],history=[],phase='DRAFT',objective='',fingerprint=identity(),busy=false,initial='',lastReply='';
 function bubble(role,text){const node=document.createElement('div');node.className='intent-bubble intent-'+role;node.textContent=text;messages.append(node);messages.scrollTop=messages.scrollHeight;}
 function render(){const active=relevant();messages.hidden=!active;preview.hidden=!active;input.placeholder=active?'Escribí tu mensaje a DPIA…':'¿Qué necesitás encontrar?';
  if(!active){window.DPIAConfirmedObjective=null;return;}
  const title=document.createElement('strong');title.textContent='Vista previa de la tarea';
  const state=document.createElement('span');state.className='intent-preview-state';state.textContent=phase==='CONFIRMED'?'Confirmada':phase==='READY_TO_CONFIRM'?'Pendiente de confirmación':'En preparación';
  const description=document.createElement('p');description.textContent=objective||'DPIA está definiendo el objetivo a partir de tu situación y tus respuestas.';
  const pending=document.createElement('p');pending.className='intent-preview-pending';pending.textContent=phase==='NEEDS_CLARIFICATION'?'Falta aclarar: '+(lastReply||'el objetivo de la búsqueda'):phase==='READY_TO_CONFIRM'?'Falta tu confirmación para continuar.':phase==='CONFIRMED'?'Objetivo confirmado. El próximo envío permite continuar.':'Escribí tu pedido para empezar.';
  preview.replaceChildren(title,state,description,pending);
  const label=phase==='CONFIRMED'?'Continuar con la tarea':'Enviar mensaje al chat';button.title=label;button.setAttribute('aria-label',label);button.disabled=busy;
 }
 function reset(){conversation=[];history=[];phase='DRAFT';objective='';initial='';lastReply='';window.DPIAConfirmedObjective=null;messages.replaceChildren();input.value='';fingerprint=identity();render();}
 async function request(confirmed){const response=await fetch('/api/consultas/resolver-intencion',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({situation:queryJourney,action:action(),message:initial,answers:history.slice(1),messages:conversation,confirmed}),signal:AbortSignal.timeout(20000)});const result=await response.json();if(!response.ok)throw Error(result.error||'No se pudo interpretar el pedido');return result;}
 async function submit(){if(busy)return;if(fingerprint!==identity())reset();const text=input.value.trim();if(!text)return;
  const oldPhase=phase;busy=true;render();
  try{
   if(oldPhase==='READY_TO_CONFIRM'&&/^(s[ií]|confirmo|confirmar|empez[aá]|adelante|ok|dale)$/i.test(text)){
    const data=await request(true);if(data.state!=='CONFIRMED')throw Error('El objetivo aún no está confirmado');
    bubble('user',text);input.value='';phase='CONFIRMED';objective=data.objective||objective;window.DPIAConfirmedObjective=objective;bubble('assistant','Objetivo confirmado. Usá la misma flecha para continuar.');render();return;
   }
   if(oldPhase==='READY_TO_CONFIRM'&&/^(no|cancelar)$/i.test(text)){bubble('user',text);input.value='';phase='NEEDS_CLARIFICATION';lastReply='¿Qué querés cambiar del objetivo?';bubble('assistant',lastReply);render();return;}
   const proposed=[...history,text],first=proposed[0];const response=await fetch('/api/consultas/resolver-intencion',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({situation:queryJourney,action:action(),message:first,answers:proposed.slice(1),messages:[...conversation,{role:'user',content:text}],confirmed:false}),signal:AbortSignal.timeout(20000)});const data=await response.json();if(!response.ok)throw Error(data.error||'No se pudo interpretar el pedido');
   history=proposed;initial=first;input.value='';bubble('user',text);conversation.push({role:'user',content:text});phase=data.state;objective=data.objective||objective;lastReply=data.question||'';const assistantMessage=phase==='NEEDS_CLARIFICATION'?(data.question||'¿Podés contarme un poco más?'):(data.confirmation||`${objective} ¿Querés que empiece?`);bubble('assistant',assistantMessage);conversation.push({role:'assistant',content:assistantMessage});render();
  }catch(error){input.value=text;bubble('assistant','No se pudo procesar el mensaje. '+error.message);}
  finally{busy=false;render();}
 }
 button.addEventListener('click',event=>{if(!relevant())return;if(fingerprint!==identity())reset();if(phase==='CONFIRMED'){if(input.value.trim()){event.preventDefault();event.stopImmediatePropagation();bubble('assistant','Para cambiar el objetivo, escribí tu nuevo pedido antes de confirmarlo nuevamente.');reset();return;}return;}
  event.preventDefault();event.stopImmediatePropagation();submit();},true);
 input.addEventListener('keydown',event=>{if(relevant()&&event.key==='Enter'&&!event.shiftKey){event.preventDefault();button.click();}});
 document.getElementById('consultAgent')?.addEventListener('click',event=>{if(relevant()&&phase!=='CONFIRMED'){event.preventDefault();event.stopImmediatePropagation();bubble('assistant','Primero confirmá el objetivo en el chat.');}},true);
 // Legacy auto-drafts must not appear as a user's reply.
 document.addEventListener('click',()=>{if(fingerprint!==identity())reset();else render();},true);
 window.DPIAIntentGateState=()=>relevant()?phase:'NOT_APPLICABLE';window.DPIAConfirmedObjective=null;render();
})();
