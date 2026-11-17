/* DPIA: preserve the suggested task prompt; use a separate composer for clarifications. */
(()=>{'use strict';
 const button=document.getElementById('preparePrompt'),prompt=document.getElementById('promptText'),root=document.getElementById('queryConversation');
 if(!button||!prompt||!root)return;
 const relevant=()=>typeof queryJourney!=='undefined'&&['start','jobs'].includes(queryJourney);
 const action=()=>({explorar:'explore',novedades:'novel',local:'local',buscar:'search'})[typeof queryMode!=='undefined'?queryMode:'buscar']||'search';
 const identity=()=>JSON.stringify([queryJourney,action(),typeof currentEmail!=='undefined'?currentEmail:null]);
 const section=document.getElementById('intentPromptSection'),display=document.getElementById('intentPromptDisplay'),messages=document.getElementById('intentChatMessages'),preview=document.getElementById('intentTaskPreview'),chatInput=document.getElementById('intentChatInput'),chatLabel=document.getElementById('intentChatInputLabel');
 if(!section||!display||!messages||!preview||!chatInput||!chatLabel)return;
 let conversation=[],history=[],phase='DRAFT',objective='',fingerprint=identity(),busy=false,initial='',lastReply='',savedPrompt='',taskFields=null,pendingMessage=null,pendingNode=null,loadingNode=null;
 const defaultPrompt=()=>queryJourney==='jobs'?'Quiero encontrar oportunidades laborales reales. Identificá vacantes verificables, requisitos y enlaces de postulación; no inventes ofertas.':action()==='novel'?'Quiero descubrir novedades y tendencias de productos con potencial de reventa. Indicá oportunidades fundamentadas, sin inventar precios.':action()==='local'?'Quiero encontrar oportunidades comerciales locales para empezar a revender productos.':'Quiero descubrir productos con potencial de reventa para iniciar mi negocio, identificar oportunidades comerciales y posibles proveedores.';
 function firstQuestion(){return queryJourney==='jobs'?'¿Qué tipo de trabajo o puesto estás buscando?':action()==='novel'?'¿Querés descubrir novedades de distintas categorías o tenés algún tipo de producto en mente?':action()==='local'?'¿Querés explorar oportunidades de reventa en tu zona o tenés algún producto en mente?':'¿Querés explorar productos de distintas categorías para revender o ya tenés alguno en mente?';}
 function bubble(role,value){const node=document.createElement('div');node.className='intent-bubble intent-'+role;node.textContent=value;messages.append(node);messages.scrollTop=messages.scrollHeight;return node;}
 function loading(show){if(loadingNode){loadingNode.remove();loadingNode=null;}if(show){loadingNode=document.createElement('div');loadingNode.className='intent-bubble intent-assistant intent-loading';loadingNode.setAttribute('role','status');loadingNode.setAttribute('aria-label','Conectando con DPIA');const spinner=document.createElement('span');spinner.className='intent-small-spinner';spinner.setAttribute('aria-hidden','true');loadingNode.append(spinner,document.createTextNode(' Conectando con DPIA…'));messages.append(loadingNode);messages.scrollTop=messages.scrollHeight;}}
 function retryError(error){const offline=typeof navigator!=='undefined'&&navigator.onLine===false;const msg=offline?'Sin conexión a Internet. Tu mensaje quedó guardado.':error.message==='openai_auth_failed'?'DPIA no pudo autenticarse con OpenAI. Tu mensaje quedó guardado.':error.message==='openai_not_configured'?'DPIA no tiene configurada la clave de OpenAI. Tu mensaje quedó guardado.':error.name==='AbortError'||error.name==='TimeoutError'?'La conexión tardó demasiado. Tu mensaje quedó guardado.':'No se pudo procesar tu respuesta. Tu mensaje quedó guardado.';const node=bubble('assistant',msg);const retry=document.createElement('button');retry.type='button';retry.className='intent-retry-button';retry.textContent='Reintentar';retry.addEventListener('click',()=>{node.remove();submit();});node.append(document.createTextNode(' '),retry);}
 function ensurePrompt(){if(!relevant())return;const value=prompt.value.trim();if(value&&!history.length&&value!==savedPrompt)savedPrompt=value;if(!savedPrompt)savedPrompt=defaultPrompt();display.textContent=(phase==='READY_TO_CONFIRM'||phase==='CONFIRMED')&&objective?objective:savedPrompt;}
 function render(){const active=relevant();section.hidden=!active;messages.hidden=!active;preview.hidden=!active;chatInput.hidden=!active;chatLabel.hidden=!active;prompt.hidden=active;
  if(!active){window.DPIAConfirmedObjective=null;return;}
  ensurePrompt();
  // Show only the next question while clarifying; reveal defined fields at confirmation.
  const heading=document.createElement('strong');heading.textContent='Vista previa de la tarea';
  const state=document.createElement('span');state.className='intent-preview-state';
  const fields=taskFields||{};
  const taskTitle=fields.task_title||(queryJourney==='jobs'?'Buscar oportunidades laborales':'Descubrir productos para empezar a revender');
  const content=document.createElement('div');content.className='intent-preview-content';
  const add=(label,value)=>{if(!value)return;const row=document.createElement('div');row.className='intent-preview-row';const name=document.createElement('strong');name.textContent=label;const detail=document.createElement('div');detail.className='intent-preview-value';detail.textContent=value;row.append(name,detail);content.append(row);};
  if(phase==='READY_TO_CONFIRM'||phase==='CONFIRMED'){
   state.textContent=phase==='CONFIRMED'?'CONFIRMED · Confirmada':'READY_TO_CONFIRM · Lista para confirmar';
   add('Título',taskTitle);add('Objetivo',objective);add('Tipo de investigación',fields.search_type);
   add('Mercado de búsqueda',fields.search_market);add('Categoría o producto',fields.product_category);
   add('Presupuesto',fields.budget);add('Resultado esperado',fields.expected_result);
   const note=document.createElement('p');note.className='intent-preview-pending';note.textContent=phase==='CONFIRMED'?'Objetivo confirmado. Podés continuar.':'¿La tarea está lista? Respondé «sí» o indicá qué querés agregar.';content.append(note);
  }else{
   state.textContent='NEEDS_CLARIFICATION · En preparación';
   const pending=document.createElement('p');pending.className='intent-preview-pending';pending.textContent='Objetivo por definir. La vista previa se completará con tus respuestas.';content.append(pending);
  }
  preview.replaceChildren(heading,state,content);
  if(!messages.childElementCount && phase==='DRAFT')bubble('assistant',firstQuestion());
  button.title=phase==='CONFIRMED'?'Continuar con la tarea':'Enviar mensaje al chat';button.setAttribute('aria-label',button.title);button.disabled=busy;
 }
 function reset(){loading(false);pendingMessage=null;pendingNode=null;conversation=[];history=[];phase='DRAFT';objective='';initial='';lastReply='';savedPrompt='';taskFields=null;window.DPIAConfirmedObjective=null;messages.replaceChildren();chatInput.value='';fingerprint=identity();render();}
 async function request(text,confirmed){const proposed=confirmed?history:[...history,text];const first=savedPrompt;const response=await fetch('/api/consultas/resolver-intencion',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({situation:queryJourney,action:action(),message:first,answers:proposed,messages:confirmed?conversation:[...conversation,{role:'user',content:text}],confirmed,proposed_objective:confirmed?objective:null}),signal:AbortSignal.timeout(12000)});const data=await response.json();if(!response.ok)throw Error(data.error||'No se pudo interpretar el pedido');return data;}
 async function submit(){
  if(busy)return;
  if(fingerprint!==identity())reset();
  const fresh=chatInput.value.trim();
  if(!pendingMessage&&!fresh)return;
  // Render the user's answer synchronously, before any network activity.
  if(!pendingMessage){pendingMessage=fresh;pendingNode=bubble('user',fresh);chatInput.value='';}
  const text=pendingMessage,previous=phase;
  busy=true;loading(true);render();
  try{
   if(previous==='READY_TO_CONFIRM'&&/^(no|cancelar)$/i.test(text)){
    phase='NEEDS_CLARIFICATION';lastReply='¿Qué querés cambiar del objetivo?';bubble('assistant',lastReply);
   }else{
    const confirming=previous==='READY_TO_CONFIRM'&&/^(s[ií]|confirmo|confirmar|empez[aá]|adelante|ok|dale|est[aá] lista|la tarea est[aá] lista|lista)$/i.test(text);
    const data=await request(text,confirming);
    if(confirming){if(data.state!=='CONFIRMED')throw Error('El objetivo todavía no está confirmado');phase='CONFIRMED';objective=data.objective||objective;taskFields=data.task_preview||taskFields;window.DPIAConfirmedObjective=objective;bubble('assistant','Objetivo confirmado. Elegí cómo querés continuar.');window.DPIAOpenConfirmedSubmit?.();}
    else{history.push(text);initial=history[0];conversation.push({role:'user',content:text});phase=data.state;objective=data.objective||objective;taskFields=data.task_preview||taskFields;lastReply=data.question||'';const reply=phase==='NEEDS_CLARIFICATION'?(data.question||'¿Podés contarme un poco más?'):(data.confirmation||`${objective} ¿La tarea está lista o querés agregar algo más?`);bubble('assistant',reply);conversation.push({role:'assistant',content:reply});}
   }
   pendingMessage=null;pendingNode=null;
  }catch(error){retryError(error);}
  finally{loading(false);busy=false;render();}
 }
 button.addEventListener('click',event=>{if(!relevant())return;if(fingerprint!==identity())reset();if(phase==='CONFIRMED'&&!chatInput.value.trim()&&!pendingMessage){event.preventDefault();event.stopImmediatePropagation();window.DPIAOpenConfirmedSubmit?.();return;}
  event.preventDefault();event.stopImmediatePropagation();if(phase==='CONFIRMED'&&chatInput.value.trim()){phase='NEEDS_CLARIFICATION';window.DPIAConfirmedObjective=null;}submit();},true);
 chatInput.addEventListener('keydown',event=>{if(relevant()&&event.key==='Enter'&&!event.shiftKey){event.preventDefault();button.click();}});
 document.getElementById('consultAgent')?.addEventListener('click',event=>{if(relevant()&&phase!=='CONFIRMED'){event.preventDefault();event.stopImmediatePropagation();bubble('assistant','Primero confirmá el objetivo en el chat.');}},true);
 // Only reset when the actual situation/action/account changes, never on ordinary clicks.
 document.addEventListener('click',()=>{if(fingerprint!==identity())reset();else render();},true);
 window.DPIAIntentGateState=()=>relevant()?phase:'NOT_APPLICABLE';window.DPIAConfirmedObjective=null;render();
})();
