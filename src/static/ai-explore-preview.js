/* Candidate preview only. No scraping, image API, credits or publication requests. */
(()=>{
 const names={amazon:'Amazon',ebay:'eBay',aliexpress:'AliExpress',mercadolibre:'Mercado Libre'};
 let dialog=null,selected=null,opener=null;
 const tr=text=>window.DPIAI18N?.translate(text)||text;
 function element(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
 function imageUrl(value){
  if(typeof value!=='string')return null;
  try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&url.hostname&&!url.username&&!url.password?url.href:null;}catch(_){return null;}
 }
 function addImage(parent,value,title){
  const url=imageUrl(value);if(!url)return;
  // A detached image loads without allocating any visible box or placeholder.
  const image=new Image();image.alt=title||'';image.referrerPolicy='no-referrer';image.decoding='async';
  image.onload=()=>{if(!image.naturalWidth||!parent.isConnected)return;const figure=element('figure',undefined,'ai-preview-image');figure.append(image);parent.prepend(figure);};
  image.onerror=()=>{const figure=image.closest('.ai-preview-image');if(figure)figure.remove();else image.remove();};image.src=url;
 }
 function metadata(context){
  const list=element('dl',undefined,'ai-suggestion-context');
  for(const [label,key] of [['Ámbito','ambito'],['Categoría','categoria'],['Ciudad','ciudad'],['Código postal','codigoPostal'],['País','pais'],['Usuario','usuario'],['Fecha','fecha'],['Idioma','idioma']]){
   const value=element('dd',String(context[key]??''));value.dataset.catalogName='';list.append(element('dt',tr(label)),value);
  }
  return list;
 }
 function close(){if(dialog?.open)dialog.close();}
 function ensureDialog(){
  if(dialog)return;
  dialog=element('dialog',undefined,'ai-preview-dialog');dialog.id='aiExplorePreview';dialog.setAttribute('aria-labelledby','aiPreviewTitle');
  dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)close();});
  dialog.addEventListener('keydown',event=>{
   if(event.key!=='Tab')return;
   const radios=[...dialog.querySelectorAll('input[type="radio"]')],activeRadio=radios.find(node=>node.checked)||radios[0];
   const targets=[...dialog.querySelectorAll('button:not([disabled]),input:not([disabled])')].filter(node=>node.type!=='radio'||node===activeRadio);
   const index=targets.indexOf(document.activeElement),next=(index+(event.shiftKey?-1:1)+targets.length)%targets.length;
   event.preventDefault();targets[next]?.focus();
  });
  dialog.addEventListener('close',()=>{selected=null;dialog.replaceChildren();if(opener?.isConnected)opener.focus();opener=null;});
  document.body.append(dialog);
  const user=document.querySelector('#userBtn');
  if(user)new MutationObserver(()=>{if(selected&&selected.email!==currentEmail)close();}).observe(user,{childList:true,subtree:true,characterData:true});
 }
 function open(snapshot,button){
  if(!currentEmail){openAuth();return;}
  ensureDialog();if(dialog.open)return;
  opener=button;selected={...structuredClone(snapshot),email:currentEmail};
  const {item,context}=selected;
  const header=element('header',undefined,'ai-preview-header'),heading=element('div');
  heading.append(element('span',tr('Sugerencia de IA'),'ai-preview-kicker'));
  const title=element('h2',item.producto);title.id='aiPreviewTitle';title.dataset.catalogName='';heading.append(title);
  const exit=element('button','×','ai-preview-close');exit.type='button';exit.setAttribute('aria-label',tr('Cerrar'));exit.onclick=close;header.append(heading,exit);
  const body=element('div',undefined,'ai-preview-body'),summary=element('section',undefined,'ai-preview-summary');
  const description=element('p',item.descripcion||'');description.dataset.catalogName='';summary.append(description);
  if(typeof item.precio_venta_sugerido==='number'){const price=element('p',tr('Precio sugerido:')+' '+item.precio_venta_sugerido+' '+(selected.constraints?.price?.currency||''));price.dataset.catalogName='';summary.append(price);}
  summary.append(metadata(context));addImage(summary,item.imagen,item.producto);
  const markets=element('section',undefined,'ai-preview-markets'),fieldset=element('fieldset');fieldset.append(element('legend',tr('Elegí un marketplace')));
  const options=element('div',undefined,'ai-preview-options');
  // Reuse the existing local integrations and Mercado Libre country restriction.
  // Live availability/permissions are checked only by the future execution step.
  for(const source of externalQuerySources){
   if(!names[source]||(source==='mercadolibre'&&!['Argentina','México'].includes(context.pais)))continue;
   const label=element('label',undefined,'ai-preview-market'),radio=element('input');radio.type='radio';radio.name='aiPreviewMarketplace';radio.value=source;
   radio.onchange=()=>{selected.marketplace=source;};label.append(radio,element('span',names[source]));options.append(label);
  }
  fieldset.append(options);markets.append(fieldset,element('p',tr('Integraciones existentes. La disponibilidad para tu país y los permisos se verificarán al habilitar la búsqueda.'),'hint'));
  const note=element('p',tr('Vista previa: elegir un marketplace no inicia scraping ni consume créditos.'),'ai-preview-note');
  body.append(summary,markets);const footer=element('footer');const done=element('button',tr('Cerrar'),'action-button');done.type='button';done.onclick=close;footer.append(note,done);
  dialog.append(header,body,footer);dialog.showModal();exit.focus();
 }
 function button(item,context,ids,details={}){
  const snapshot=structuredClone({item,context,ids:ids||{},constraints:details.constraints,query:details.query}),node=element('button',tr('Explorar'),'action-button ai-preview-trigger');node.type='button';node.setAttribute('aria-haspopup','dialog');node.onclick=()=>open(snapshot,node);return node;
 }
 window.DPIAExplorePreview={button,addImage};
})();
