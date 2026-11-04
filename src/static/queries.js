// The original user request is preserved; context and identity are verified by Flask.
let queryMode='buscar', queryPrepared=null, queryBusy=false, queryRequestId=null, pendingSourcesGeneration=false;
const querySources=['amazon','ebay','aliexpress','local','dpia','historial'];
function refreshQuerySelectors(category=null, scopeId=null){
 const scopeSelect=document.querySelector('#queryScope'), categorySelect=document.querySelector('#queryCategory'), postalSelect=document.querySelector('#queryPostal');
 const oldScope=scopeSelect.value,oldCategory=categorySelect.value,oldPostal=postalSelect.value;
 scopeSelect.replaceChildren(new Option('Elegí un ámbito',''));
 for(const scope of catalogAmbitos){const option=new Option(scope.nombre,String(scope.ambito_id));option.dataset.catalogName='';scopeSelect.add(option);}
 const desired=scopeId||category?.ambito_ids.find(id=>catalogAmbitos.some(scope=>scope.ambito_id===id))||oldScope;
 if([...scopeSelect.options].some(option=>option.value===String(desired)))scopeSelect.value=String(desired);
 categorySelect.replaceChildren(new Option('Elegí una categoría',''));
 for(const item of catalogCategorias.filter(item=>item.ambito_ids.includes(Number(scopeSelect.value)))){
  const option=new Option(item.nombre,String(item.categoria_id));option.dataset.catalogName='';categorySelect.add(option);
 }
 const categoryId=category?.categoria_id||(oldScope===scopeSelect.value?oldCategory:'');
 if([...categorySelect.options].some(option=>option.value===String(categoryId)))categorySelect.value=String(categoryId);
 document.querySelector('#queryCity').value=city;
 postalSelect.replaceChildren();
 for(const record of catalogPostalCodes)postalSelect.add(new Option(city,String(record.id)));
 if([...postalSelect.options].some(option=>option.value===oldPostal))postalSelect.value=oldPostal;
 invalidateQuery();
}
function invalidateQuery(){queryPrepared=null;queryRequestId=null;document.querySelector('#generateQuery').hidden=true;document.querySelector('#queryResults').replaceChildren();document.querySelector('#promptResult').hidden=true;}
function chooseQueryCategory(item, scopeId=null){queryMode='buscar';refreshQuerySelectors(item,scopeId);localCategory={id:String(item.categoria_id),name:item.nombre};}
function openNovelQuery(){queryMode='novedades';show('consultPage');document.querySelector('#promptText').value=document.querySelector('#searchText').value.trim();invalidateQuery();}
function queryBody(){return {pais:country,ciudad:city,idioma:catalogLanguage(),ambito_id:Number(document.querySelector('#queryScope').value),categoria_id:Number(document.querySelector('#queryCategory').value),codigo_postal_id:Number(document.querySelector('#queryPostal').value),mode:queryMode,user_message:document.querySelector('#promptText').value.trim(),attachments:media};}
function startHomeQuery(){
 document.querySelector('#promptText').value=document.querySelector('#searchText').value.trim();queryMode='buscar';invalidateQuery();show('consultPage');prepareDPIAQuery();
}
async function prepareDPIAQuery(){
 if(queryBusy)return;show('consultPage');
 if(!currentEmail){openAuth();return;}
 await queryMediaPending;if(queryBusy)return;
 const status=document.querySelector('#queryStatus'),body=queryBody();
 if(!body.ambito_id||!body.categoria_id){status.textContent='Elegí un ámbito y una categoría para continuar.';document.querySelector(body.ambito_id?'#queryCategory':'#queryScope').focus();return;}
 if(!body.user_message&&!body.attachments.length){status.textContent='Escribí tu pedido o adjuntá una imagen o video.';return;}
 queryBusy=true;invalidateQuery();status.textContent='Preparando tu consulta…';
 try{
  const response=await fetch('/api/consultas/preparar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
  const data=await response.json();if(response.status===401)openAuth();if(!response.ok||!data.success)throw new Error(data.error||'No se pudo preparar la consulta.');
  queryPrepared={body:structuredClone(body),fingerprint:JSON.stringify(body)};
  document.querySelector('#promptResult').textContent=data.summary;document.querySelector('#promptResult').hidden=false;
  document.querySelector('#generateQuery').hidden=false;document.querySelector('#generateQuery').disabled=false;
  status.textContent='Revisá el resumen y elegí los orígenes de búsqueda.';
 }catch(error){status.textContent=error.name==='TimeoutError'?'La preparación tardó demasiado. Reintentá.':error.message;}
 finally{queryBusy=false;}
}
function sourcePreferenceKey(){return 'dpia-query-sources:'+currentEmail;}
function savedQuerySources(){
 try{const saved=JSON.parse(localStorage.getItem(sourcePreferenceKey()));return Array.isArray(saved)&&saved.length&&saved.every(s=>querySources.includes(s))?[...new Set(saved)]:null;}catch(_){return null;}
}
function openSourceModal(generateAfter=false){
 if(queryBusy)return;
 pendingSourcesGeneration=generateAfter;
 const selected=savedQuerySources()||querySources.slice(0,3);
 document.querySelector('#allQuerySources').checked=selected.length===querySources.length;
 for(const checkbox of document.querySelectorAll('[name="querySource"]'))checkbox.checked=selected.includes(checkbox.value);
 document.querySelector('#querySourceError').textContent='';document.querySelector('#querySourcesModal').hidden=false;
 document.querySelector('#confirmQuerySources').focus();
}
function closeSourceModal(){document.querySelector('#querySourcesModal').hidden=true;pendingSourcesGeneration=false;}
function renderQueryResult(data){
 const container=document.querySelector('#queryResults');container.replaceChildren();
 for(const [source,outcome] of Object.entries(data.sources||{})){
  const article=document.createElement('article');article.className='prompt-result';
  const title=document.createElement('strong');title.textContent=source;article.append(title);
  if(outcome.error){const p=document.createElement('p');p.textContent=outcome.error;article.append(p);}
  else if(!outcome.data?.length){const p=document.createElement('p');p.textContent='Sin resultados para este origen.';article.append(p);}
  else for(const row of outcome.data){
   const detail=document.createElement('p');
   detail.textContent=row.titulo||row.producto||row.Producto||row.search_query||JSON.stringify(row);
   const description=document.createElement('small');description.textContent=row.descripcion||'';article.append(detail,description);
   for(const product of row.items||[]){const p=document.createElement('p');p.textContent=[product.titulo,product.precio].filter(v=>v!=null).join(' · ');article.append(p);}
  }
  container.append(article);
 }
 for(const row of data.rows||[]){
  const card=document.createElement('article');card.className='prompt-result';const title=document.createElement('strong');title.textContent=row.Producto;
  const detail=document.createElement('p');detail.textContent=row.descripcion;card.append(title,detail);container.append(card);
 }
 const download=document.createElement('button');download.type='button';download.textContent='Descargar JSON';
 download.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='dpia-results.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};container.append(download);
}
async function generateDPIAQuery(){
 if(queryBusy||!queryPrepared)return;
 if(!currentEmail){openAuth();return;}
 if(JSON.stringify(queryBody())!==queryPrepared.fingerprint){invalidateQuery();document.querySelector('#queryStatus').textContent='El pedido cambió. Prepará nuevamente la consulta.';return;}
 const sources=savedQuerySources();if(!sources){openSourceModal(true);return;}
 queryBusy=true;const button=document.querySelector('#generateQuery'),status=document.querySelector('#queryStatus');button.disabled=true;
 status.textContent='Buscando en los orígenes seleccionados…';queryRequestId ||= crypto.randomUUID();
 try{
  const response=await fetch('/api/consultas/generar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...queryPrepared.body,sources,request_id:queryRequestId}),signal:AbortSignal.timeout(650000)});
  const data=await response.json();if(response.status===401)openAuth();if(!response.ok||!data.success)throw new Error(data.error||'No se pudo generar la consulta.');
  if(!queryPrepared||JSON.stringify(queryBody())!==queryPrepared.fingerprint){status.textContent='El pedido cambió. Prepará nuevamente la consulta.';return;}
  if(data.result.needs_clarification){status.textContent=data.result.clarifying_question;return;}
  renderQueryResult(data);status.textContent='Consulta completada. Revisá los resultados de cada origen.';
 }catch(error){status.textContent=error.name==='TimeoutError'?'La consulta sigue pendiente. No se reenviará automáticamente.':error.message;}
 finally{queryBusy=false;button.disabled=false;}
}
document.querySelector('#queryScope').addEventListener('change',()=>{refreshQuerySelectors();syncLocalCategory();});
for(const id of ['queryCategory','queryPostal','promptText','searchText'])document.querySelector('#'+id).addEventListener('input',invalidateQuery);
document.querySelector('#generateQuery').onclick=generateDPIAQuery;
document.querySelector('#changeQuerySources').onclick=()=>openSourceModal(false);
document.querySelector('#closeQuerySources').onclick=closeSourceModal;
document.querySelector('#querySourcesModal').onclick=e=>{if(e.target.id==='querySourcesModal')closeSourceModal();};
document.querySelector('#allQuerySources').onchange=e=>{for(const box of document.querySelectorAll('[name="querySource"]'))box.checked=e.target.checked;};
document.querySelector('#confirmQuerySources').onclick=()=>{
 const sources=[...document.querySelectorAll('[name="querySource"]:checked')].map(box=>box.value);
 if(!sources.length){document.querySelector('#querySourceError').textContent='Seleccioná al menos un origen de búsqueda.';return;}
 try{localStorage.setItem(sourcePreferenceKey(),JSON.stringify(sources));}catch(_){document.querySelector('#querySourceError').textContent='No se pudieron guardar los orígenes.';return;}
 const generate=pendingSourcesGeneration;queryRequestId=null;closeSourceModal();if(generate)generateDPIAQuery();
};
function syncLocalCategory(){const option=document.querySelector('#queryCategory').selectedOptions[0];localCategory=option?.value?{id:option.value,name:option.textContent}:null;}
document.querySelector('#queryCategory').addEventListener('change',syncLocalCategory);

document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!document.querySelector('#querySourcesModal').hidden)closeSourceModal();});
for(const box of document.querySelectorAll('[name="querySource"]'))box.addEventListener('change',()=>{document.querySelector('#allQuerySources').checked=[...document.querySelectorAll('[name="querySource"]')].every(item=>item.checked);});
