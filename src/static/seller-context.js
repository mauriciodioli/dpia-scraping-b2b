/* Optional seller context, selected explicitly from authenticated existing records. */
(()=>{
 const panel=document.createElement('section');panel.className='query-chat-reply';panel.hidden=true;
 const heading=document.createElement('strong');heading.textContent='Tu negocio · contexto opcional';
 const help=document.createElement('p');help.textContent='Elegí ámbito y categoría arriba. Podés sumar publicaciones o búsquedas anteriores para ampliar tu catálogo.';
 const load=document.createElement('button');load.type='button';load.className='action-button';load.textContent='Elegir publicaciones o búsquedas anteriores';
 const list=document.createElement('div'),summary=document.createElement('p'),status=document.createElement('p');status.setAttribute('role','status');
 const history=document.createElement('button');history.type='button';history.className='quiet';history.textContent='Ver historial de búsquedas';history.onclick=()=>document.getElementById('queryHistoryTab').click();
 panel.append(heading,help,load,list,summary,history,status);document.getElementById('promptText').before(panel);
 const selected=new Map();let owner=null,serial=0;
 window.DPIASellerContext=()=>owner===currentEmail?[...selected.values()].join('\n'):'';
 function refresh(){
  const visible=queryJourney==='online';panel.hidden=!visible;
  if(owner!==currentEmail){owner=currentEmail;serial++;selected.clear();list.replaceChildren();summary.textContent='';}
  if(visible)for(const id of ['queryScope','queryCategory'])document.getElementById(id).closest('label').hidden=false;
 }
 function changed(){summary.textContent=window.DPIASellerContext();
  // Rebuild only an automatically suggested prompt, preserving manually edited requests.
  if(document.getElementById('promptText').value===exploreAutoDraft)updateExploreDraft(true);
  else {const prompt=document.getElementById('promptText');const base=prompt.value.split('\nContexto seleccionado:')[0];prompt.value=base+'\nContexto seleccionado:\n'+window.DPIASellerContext();}
  invalidateQuery();
 }
 load.onclick=async()=>{
  if(!currentEmail){openAuth();return;}refresh();const email=currentEmail,version=++serial;load.disabled=true;list.replaceChildren();status.textContent='Cargando…';
  const results=await Promise.allSettled([
   fetch('/api/publicaciones/mias?offset=0',{cache:'no-store'}).then(async r=>{const d=await r.json();if(!r.ok||!d.success)throw Error('No se pudieron cargar las publicaciones.');return(d.publicaciones||[]).map(p=>({key:'p'+p.id,text:'Publicación: '+p.titulo+' · '+(p.descripcion||'').slice(0,200)}));}),
   fetch('/api/consultas/historial?offset=0',{cache:'no-store'}).then(async r=>{const d=await r.json();if(!r.ok||!d.success)throw Error('No se pudo cargar el historial.');return(d.operations||[]).map(p=>({key:'h'+p.operation_id,text:'Búsqueda anterior: '+(p.query||p.category||'Búsqueda guardada').slice(0,240),operation:p.operation_id}));})
  ]);
  if(email!==currentEmail||version!==serial){load.disabled=false;return;}
  let count=0;const errors=[];
  for(const result of results){if(result.status==='rejected'){errors.push(result.reason.message);continue;}
   for(const item of result.value){count++;const row=document.createElement('p'),label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=selected.has(item.key);input.onchange=()=>{if(input.checked)selected.set(item.key,item.text);else selected.delete(item.key);changed();};label.append(input,document.createTextNode(item.text));row.append(label);
    if(item.operation){const link=document.createElement('button');link.type='button';link.className='quiet';link.textContent='Consultar resultados →';link.onclick=()=>loadQueryOperation(item.operation);row.append(link);}list.append(row);
   }
  }
  status.textContent=errors.join(' ')||(!count?'Todavía no tenés publicaciones ni búsquedas guardadas.':'Se muestran los registros recientes. Podés consultar el historial completo.');load.disabled=false;
 };
 document.addEventListener('click',refresh);new MutationObserver(refresh).observe(document.getElementById('consultPage'),{attributes:true,attributeFilter:['hidden']});refresh();
})();
