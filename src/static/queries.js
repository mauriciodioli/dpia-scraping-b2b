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
function invalidateQuery(){if(queryBusy)return;queryPrepared=null;queryRequestId=null;document.querySelector('#generateQuery').hidden=true;document.querySelector('#queryResults').replaceChildren();document.querySelector('#promptResult').hidden=true;}
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
  document.querySelector('#generateQuery').textContent=body.mode==='buscar'&&!body.attachments.length?'Iniciar búsqueda':'Generar candidatos';
  status.textContent='Revisá el resumen y elegí los orígenes de búsqueda.';
 }catch(error){status.textContent=error.name==='TimeoutError'?'La preparación tardó demasiado. Reintentá.':error.message;}
 finally{queryBusy=false;}
}
function sourcePreferenceKey(){return 'dpia-query-sources:'+currentEmail;}
function savedQuerySources(){
 try{const saved=JSON.parse(localStorage.getItem(sourcePreferenceKey()));return Array.isArray(saved)&&saved.length&&saved.every(s=>querySources.includes(s))&&saved.filter(s=>['amazon','ebay','aliexpress'].includes(s)).length<=1?[...new Set(saved)]:null;}catch(_){return null;}
}
function openSourceModal(generateAfter=false){
 if(queryBusy)return;
 pendingSourcesGeneration=generateAfter;
 const selected=savedQuerySources()||['amazon'];
 document.querySelector('#allQuerySources').checked=['local','dpia','historial'].every(source=>selected.includes(source));
 for(const checkbox of document.querySelectorAll('[name="querySource"]'))checkbox.checked=selected.includes(checkbox.value);
 document.querySelector('#querySourceError').textContent='';document.querySelector('#querySourcesModal').hidden=false;
 document.querySelector('#confirmQuerySources').focus();
}
function closeSourceModal(){document.querySelector('#querySourcesModal').hidden=true;pendingSourcesGeneration=false;}
let lastQueryOperationId=null;
function safeQueryUrl(value){
 try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username?url.href:null;}catch(_){return null;}
}
function renderQueryResult(data){
 const container=document.querySelector('#queryResults');container.replaceChildren();
 const states={complete:'Completado',partial:'Completado con advertencias',empty:'Completado sin productos',pending:'Pendiente de confirmación',failed:'Fallido',clarification_required:'Requiere aclaración'};
 for(const [source,outcome] of Object.entries(data.sources||{})){
  const section=document.createElement('section');section.className='source-result';section.dataset.source=source;
  const title=document.createElement('h3');title.textContent=source;section.append(title);
  const state=document.createElement('p');state.className='query-state';state.textContent=states[outcome.status]||'Pendiente de confirmación';section.append(state);
  if(outcome.error){const error=document.createElement('p');error.textContent=outcome.error;section.append(error);}
  const external=['amazon','ebay','aliexpress'].includes(source);
  if(external){
   const grid=document.createElement('div');grid.className='scraped-products';
   for(const [productIndex,product] of (outcome.products||[]).entries()){
    const card=document.createElement('article');card.className='scraped-product';card.dataset.realProduct='';
    const visual=document.createElement('div');visual.className='scraped-product-visual';
    const imageUrl=safeQueryUrl(product.image);
    if(imageUrl){const image=document.createElement('img');image.src=imageUrl;image.alt='';image.loading='lazy';image.onerror=()=>image.remove();visual.append(image);}
    const name=document.createElement('strong');name.textContent=product.title;
    const price=document.createElement('p');price.textContent=product.price==null?'Precio no informado':typeof product.price==='object'?JSON.stringify(product.price):String(product.price);
    const currency=document.createElement('small');currency.textContent=product.currency||'Moneda no informada';
    const marketplace=document.createElement('small');marketplace.textContent=product.marketplace||source;
    card.append(visual,name,price,currency,marketplace);
    const productUrl=safeQueryUrl(product.url);
    if(productUrl){const link=document.createElement('a');link.href=productUrl;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Ver producto';card.append(link);}
    if(source==='amazon'&&(data.request_id||lastQueryOperationId)&&window.DPIAHistory)card.append(window.DPIAHistory.imageButton(data.request_id||lastQueryOperationId,productIndex,product,outcome.image_stages?.[String(productIndex)]));
    grid.append(card);
   }
   section.append(grid);
   if(outcome.status==='pending'&&lastQueryOperationId){const refresh=document.createElement('button');refresh.type='button';refresh.textContent='Consultar estado';refresh.onclick=()=>loadQueryOperation(lastQueryOperationId);section.append(refresh);}
  }else{
   for(const row of outcome.data||[]){const article=document.createElement('article');article.className='prompt-result';const name=document.createElement('strong');name.textContent=row.titulo||row.producto||row.Producto||'';const description=document.createElement('p');description.textContent=row.descripcion||'';article.append(name,description);section.append(article);}
   if(!outcome.data?.length){const empty=document.createElement('p');empty.textContent='Sin resultados para este origen.';section.append(empty);}
  }
  container.append(section);
 }
 if(data.rows?.length){
  const candidates=document.createElement('details'),heading=document.createElement('summary');
  candidates.className='query-candidates';heading.textContent='Candidatos de OpenAI · sin verificar';candidates.append(heading);
  for(const row of data.rows){const card=document.createElement('article');card.className='prompt-result';const title=document.createElement('strong');title.textContent=row.Producto;const detail=document.createElement('p');detail.textContent=row.descripcion;card.append(title,detail);candidates.append(card);}
  container.append(candidates);
 }
 const download=document.createElement('button');download.type='button';download.textContent='Descargar JSON';
 download.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='dpia-results.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};container.append(download);
}
async function loadQueryOperation(id){
 const status=document.querySelector('#queryStatus');show('consultPage');
 try{
  const response=await fetch('/api/consultas/operaciones/'+encodeURIComponent(id),{cache:'no-store'}),data=await response.json();
  if(!response.ok||!data.success)throw new Error(data.error||'No se pudo consultar el estado.');
  lastQueryOperationId=id;renderQueryResult(data.payload);window.DPIACredits?.refresh();
  status.textContent=data.state==='pending'?'La ejecución sigue pendiente. No se reenviará.':data.state==='failed'?'La ejecución falló.':'Estado recuperado del servidor.';
 }catch(error){status.textContent=error.message;}
}
function setScrapingStatus(state,text){
 const badge=document.querySelector('#scrapingActivity');
 badge.hidden=false;badge.dataset.state=state;
 badge.querySelector('span:last-child').textContent=text;
}
function updateScrapingStatus(data){
 const outcomes=Object.values(data.sources||{});
 if(outcomes.some(row=>row.status==='pending'))setScrapingStatus('pending','Scraping pendiente de confirmación · Consultar');
 else if(outcomes.some(row=>row.status==='failed'))setScrapingStatus('failed','La búsqueda informó un error · Consultar');
 else {
  const count=outcomes.reduce((sum,row)=>sum+(row.products?.length||0),0);
  setScrapingStatus('complete',count?`${count} resultados disponibles · Consultar`:'Búsqueda completada sin resultados · Consultar');
 }
}
document.querySelector('#scrapingActivity').onclick=()=>{document.querySelector('#scrapingActivity').hidden=true;show('consultPage');document.querySelector('#queryResults').scrollIntoView({behavior:'smooth',block:'start'});};
async function generateDPIAQuery(){
 if(queryBusy||!queryPrepared)return;
 if(!currentEmail){openAuth();return;}
 if(JSON.stringify(queryBody())!==queryPrepared.fingerprint){invalidateQuery();document.querySelector('#queryStatus').textContent='El pedido cambió. Prepará nuevamente la consulta.';return;}
 const sources=savedQuerySources();if(!sources){openSourceModal(true);return;}
 queryBusy=true;const button=document.querySelector('#generateQuery'),status=document.querySelector('#queryStatus');button.disabled=true;
 const direct=queryPrepared.body.mode==='buscar'&&!queryPrepared.body.attachments.length&&sources.length===1&&['amazon','ebay','aliexpress'].includes(sources[0]);
 if(direct)setScrapingStatus('running','Scrapeando…');
 status.textContent='Buscando en los orígenes seleccionados…';queryRequestId ||= crypto.randomUUID();
 try{
  const response=await fetch(direct?'/api/consultas/scraping-directo':'/api/consultas/generar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...queryPrepared.body,sources,request_id:queryRequestId}),signal:AbortSignal.timeout(650000)});
  const data=await response.json();if(response.status===401)openAuth();
  if(response.status===402&&data.code==='insufficient_credit'){if(direct)setScrapingStatus('failed','No se inició: ejecuciones insuficientes · Consultar');window.DPIACredits?.insufficient(data);return;}
  if(!response.ok||!data.success){const confirmedRejection=response.status<500||data.code==='persistence_not_configured';if(direct&&confirmedRejection)setScrapingStatus('failed','No se inició la búsqueda · Consultar');const error=new Error(data.error||'No se pudo generar la consulta.');error.confirmedRejection=confirmedRejection;throw error;}
  lastQueryOperationId=data.request_id||queryRequestId;window.DPIACredits?.refresh();
  if(!direct&&(!queryPrepared||JSON.stringify(queryBody())!==queryPrepared.fingerprint)){status.textContent='El pedido cambió. Prepará nuevamente la consulta.';return;}
  if(data.result.needs_clarification){status.textContent=data.result.clarifying_question;return;}
  renderQueryResult(data);if(direct)updateScrapingStatus(data);
  const outcomes=Object.values(data.sources||{});
  status.textContent=outcomes.some(row=>row.status==='pending')?'La ejecución sigue pendiente. No se reenviará.':outcomes.some(row=>row.status==='failed')?'La ejecución falló.':'Consulta completada. Revisá los resultados de cada origen.';
 }catch(error){if(direct&&!error.confirmedRejection)setScrapingStatus('pending','Scraping pendiente de confirmación · Consultar');status.textContent=error.name==='TimeoutError'?'La consulta sigue pendiente. No se reenviará automáticamente.':error.message;if(queryRequestId){lastQueryOperationId=queryRequestId;const refresh=document.createElement('button');refresh.textContent='Consultar estado';refresh.onclick=()=>loadQueryOperation(lastQueryOperationId);document.querySelector('#queryResults').append(refresh);}}
 finally{queryBusy=false;button.disabled=false;window.DPIACredits?.refresh();}
}
document.querySelector('#queryScope').addEventListener('change',()=>{refreshQuerySelectors();syncLocalCategory();});
for(const id of ['queryCategory','queryPostal','promptText','searchText'])document.querySelector('#'+id).addEventListener('input',invalidateQuery);
document.querySelector('#generateQuery').onclick=generateDPIAQuery;
document.querySelector('#changeQuerySources').onclick=()=>openSourceModal(false);
document.querySelector('#closeQuerySources').onclick=closeSourceModal;
document.querySelector('#querySourcesModal').onclick=e=>{if(e.target.id==='querySourcesModal')closeSourceModal();};
document.querySelector('#allQuerySources').onchange=e=>{for(const box of document.querySelectorAll('[name="querySource"]'))if(['local','dpia','historial'].includes(box.value))box.checked=e.target.checked;};
document.querySelector('#confirmQuerySources').onclick=()=>{
 const sources=[...document.querySelectorAll('[name="querySource"]:checked')].map(box=>box.value);
 if(!sources.length){document.querySelector('#querySourceError').textContent='Seleccioná al menos un origen de búsqueda.';return;}
 try{localStorage.setItem(sourcePreferenceKey(),JSON.stringify(sources));}catch(_){document.querySelector('#querySourceError').textContent='No se pudieron guardar los orígenes.';return;}
 const generate=pendingSourcesGeneration;queryRequestId=null;closeSourceModal();if(generate)generateDPIAQuery();
};
function syncLocalCategory(){const option=document.querySelector('#queryCategory').selectedOptions[0];localCategory=option?.value?{id:option.value,name:option.textContent}:null;}
document.querySelector('#queryCategory').addEventListener('change',syncLocalCategory);

document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!document.querySelector('#querySourcesModal').hidden)closeSourceModal();});
for(const box of document.querySelectorAll('[name="querySource"]'))box.addEventListener('change',()=>{if(box.checked&&['amazon','ebay','aliexpress'].includes(box.value)){for(const other of document.querySelectorAll('[name="querySource"]'))if(other!==box&&['amazon','ebay','aliexpress'].includes(other.value))other.checked=false;}document.querySelector('#allQuerySources').checked=[...document.querySelectorAll('[name="querySource"]')].filter(item=>['local','dpia','historial'].includes(item.value)).every(item=>item.checked);});
