/* Seller context stays compact; changes are applied only on explicit confirmation. */
(()=>{
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
 const panel=el('section',null,'seller-context');panel.hidden=true;
 const heading=el('strong','Tu negocio'),help=el('p','Sumá referencias de lo que ya vendés o buscaste. Es opcional.','hint');
 const load=el('button','Elegir referencias','action-button');load.type='button';
 const summary=el('div',null,'seller-selected');
 panel.append(heading,help,summary,load);document.getElementById('promptText').before(panel);
 const dialog=el('dialog',null,'seller-picker');dialog.setAttribute('aria-labelledby','sellerPickerTitle');
 const header=el('div',null,'seller-picker-head'),title=el('h3','Referencias para tu búsqueda');title.id='sellerPickerTitle';
 const close=el('button','×','quiet');close.type='button';close.setAttribute('aria-label','Cerrar');header.append(title,close);
 const tabs=el('div',null,'seller-picker-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label','Tipo de referencia');
 const search=el('input');search.type='search';search.placeholder='Buscar entre los registros cargados';search.setAttribute('aria-label',search.placeholder);
 const list=el('div',null,'seller-picker-list'),status=el('p',null,'hint');status.setAttribute('role','status');
 const pager=el('div',null,'seller-picker-pages'),prev=el('button','Anterior','action-button'),next=el('button','Siguiente','action-button'),pageLabel=el('span');pager.append(prev,pageLabel,next);
 const more=el('button','Cargar más registros','quiet');more.type='button';
 const footer=el('div',null,'seller-picker-footer'),count=el('span'),cancel=el('button','Cancelar','action-button'),apply=el('button','Usar selección','primary');footer.append(count,cancel,apply);
 dialog.append(header,tabs,search,status,list,pager,more,footer);document.body.append(dialog);
 const selected=new Map();let draft=new Map(),owner=null,serial=0,kind='publications',page=0,busy=false;
 const stores={};const resetStores=()=>{for(const k of ['publications','history'])stores[k]={items:[],offset:0,more:true,loaded:false};};resetStores();
 window.DPIASellerContext=()=>owner===currentEmail?[...selected.values()].map(x=>x.text).join('\n'):'';
 function compact(){summary.replaceChildren();if(!selected.size)return;
  const label=el('p',`${selected.size} referencia${selected.size===1?'':'s'} seleccionada${selected.size===1?'':'s'}`);summary.append(label);
  for(const [key,item] of selected){const chip=el('span',null,'seller-reference'),name=el('span',item.title),remove=el('button','×','quiet');remove.type='button';remove.setAttribute('aria-label','Quitar '+item.title);remove.onclick=()=>{selected.delete(key);changed();};chip.append(name,remove);summary.append(chip);}
  load.textContent='Cambiar referencias';
 }
 function refresh(){panel.hidden=queryJourney!=='online';
  if(owner!==currentEmail){owner=currentEmail;serial++;busy=false;selected.clear();draft.clear();resetStores();compact();load.textContent='Elegir referencias';if(dialog.open)dialog.close();}
  if(!panel.hidden)for(const id of ['queryScope','queryCategory'])document.getElementById(id).closest('label').hidden=false;
 }
 function changed(){compact();const prompt=document.getElementById('promptText');
  if(prompt.value===exploreAutoDraft)updateExploreDraft(true);
  else if(prompt.value===novelAutoDraft)updateNovelDraft(true);
  else {const base=prompt.value.split('\nContexto seleccionado:')[0];prompt.value=base+(selected.size?'\nContexto seleccionado:\n'+window.DPIASellerContext():'');}
  invalidateQuery();
 }
 const tabButtons={};for(const [key,label] of [['publications','Publicaciones'],['history','Búsquedas anteriores']]){const b=el('button',label);b.type='button';b.onclick=()=>{kind=key;page=0;search.value='';status.textContent='';render();if(!stores[kind].loaded)fetchRows();};tabs.append(b);tabButtons[key]=b;}
 function render(){const store=stores[kind],term=search.value.trim().toLocaleLowerCase(),rows=store.items.filter(x=>(x.title+' '+x.detail).toLocaleLowerCase().includes(term));
  const pages=Math.max(1,Math.ceil(rows.length/5));page=Math.min(page,pages-1);list.replaceChildren();
  for(const item of rows.slice(page*5,page*5+5)){const row=el('article',null,'seller-picker-row'),label=el('label'),input=el('input'),text=el('span'),name=el('strong',item.title),detail=el('small',item.detail);input.type='checkbox';input.checked=draft.has(item.key);input.onchange=()=>{if(input.checked)draft.set(item.key,item);else draft.delete(item.key);count.textContent=`${draft.size} seleccionadas`;};text.append(name,detail);label.append(input,text);row.append(label);
   if(item.operation){const link=el('button','Ver resultado','quiet');link.type='button';link.onclick=()=>{dialog.close();loadQueryOperation(item.operation);};row.append(link);}list.append(row);
  }
  if(!rows.length)list.append(el('p',busy?'Cargando…':term?'No hay coincidencias entre los registros cargados.':'Todavía no hay referencias guardadas.','hint'));
  pageLabel.textContent=`${page+1} / ${pages}`;prev.disabled=page===0;next.disabled=page+1>=pages;more.hidden=!store.more;more.disabled=busy;apply.disabled=busy;count.textContent=`${draft.size} seleccionadas`;
  for(const [key,b] of Object.entries(tabButtons)){b.setAttribute('aria-pressed',String(key===kind));b.disabled=busy;}
 }
 async function fetchRows(){if(busy)return;const target=kind,store=stores[target],email=currentEmail,version=++serial;busy=true;status.textContent='';render();
  try{const response=await fetch((target==='publications'?'/api/publicaciones/mias?offset=':'/api/consultas/historial?offset=')+store.offset,{cache:'no-store'}),data=await response.json();if(email!==currentEmail||version!==serial)return;
   if(!response.ok||!data.success)throw Error('No se pudieron cargar las referencias. Reintentá.');
   const raw=target==='publications'?data.publicaciones:data.operations;if(!Array.isArray(raw))throw Error('No se pudieron cargar las referencias.');
   const known=new Set(store.items.map(x=>x.key));for(const p of raw){const title=String(target==='publications'?p.titulo||'Publicación':p.query||p.category||'Búsqueda guardada'),detail=String(target==='publications'?p.descripcion||'':[p.city,p.category,p.created_at?.slice(0,10)].filter(Boolean).join(' · ')),key=(target==='publications'?'p':'h')+(p.id??p.operation_id);if(!known.has(key)){store.items.push({key,title,detail,text:(target==='publications'?'Publicación: ':'Búsqueda anterior: ')+title.slice(0,240)+(detail?' · '+detail.slice(0,200):''),operation:target==='history'?p.operation_id:null});known.add(key);}}
   store.offset=Number.isSafeInteger(data.next_offset)?data.next_offset:store.offset+raw.length;store.more=!!data.has_more&&raw.length>0;store.loaded=true;
  }catch(_){if(version===serial)status.textContent='No se pudieron cargar las referencias. Volvé a intentar con «Cargar más registros».';}
  finally{if(version===serial){busy=false;render();}}
 }
 load.onclick=()=>{if(!currentEmail){openAuth();return;}refresh();draft=new Map(selected);page=0;search.value='';status.textContent='';render();dialog.showModal();search.focus();if(!stores[kind].loaded)fetchRows();};
 close.onclick=cancel.onclick=()=>dialog.close();apply.onclick=()=>{selected.clear();for(const [k,v] of draft)selected.set(k,v);changed();dialog.close();};
 search.oninput=()=>{page=0;render();};prev.onclick=()=>{page--;render();};next.onclick=()=>{page++;render();};more.onclick=fetchRows;
 document.addEventListener('click',refresh);new MutationObserver(refresh).observe(document.getElementById('consultPage'),{attributes:true,attributeFilter:['hidden']});refresh();
})();
