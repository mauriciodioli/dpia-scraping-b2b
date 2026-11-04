// User message and summary are public; the generation instruction lives in Flask.
let queryMode='buscar', queryPrepared=null, queryBusy=false;
function refreshQuerySelectors(category=null, scopeId=null){
 const scopeSelect=document.querySelector('#queryScope'), categorySelect=document.querySelector('#queryCategory'), postalSelect=document.querySelector('#queryPostal');
 const oldScope=scopeSelect.value,oldCategory=categorySelect.value,oldPostal=postalSelect.value;
 scopeSelect.replaceChildren();
 for(const scope of catalogAmbitos){const option=new Option(scope.nombre,String(scope.ambito_id));scopeSelect.add(option);}
 const desired=scopeId||category?.ambito_ids.find(id=>catalogAmbitos.some(scope=>scope.ambito_id===id))||Number(oldScope)||Number([...selected][0]);
 if([...scopeSelect.options].some(option=>option.value===String(desired)))scopeSelect.value=String(desired);
 categorySelect.replaceChildren();
 for(const item of catalogCategorias.filter(item=>item.ambito_ids.includes(Number(scopeSelect.value))))categorySelect.add(new Option(item.nombre,String(item.categoria_id)));
 const categoryId=category?.categoria_id||Number(oldCategory);
 if([...categorySelect.options].some(option=>option.value===String(categoryId)))categorySelect.value=String(categoryId);
 document.querySelector('#queryCity').value=city;
 postalSelect.replaceChildren();
 for(const record of catalogPostalCodes)postalSelect.add(new Option(city,String(record.id)));
 if([...postalSelect.options].some(option=>option.value===oldPostal))postalSelect.value=oldPostal;
 invalidateQuery();
}
function invalidateQuery(){queryPrepared=null;document.querySelector('#generateQuery').hidden=true;document.querySelector('#queryResults').replaceChildren();document.querySelector('#promptResult').hidden=true;}
function chooseQueryCategory(item, scopeId=null){queryMode='buscar';refreshQuerySelectors(item, scopeId);}
function openNovelQuery(){queryMode='novedades';refreshQuerySelectors();show('consultPage');const category=document.querySelector('#queryCategory').selectedOptions[0]?.textContent||'';document.querySelector('#promptText').value=`Encontrar productos novedosos de ${category} en ${city}, ${country}. Priorizar tendencias y publicaciones locales.`;}
function queryBody(){return {pais:country,ciudad:city,idioma:catalogLanguage(),ambito_id:Number(document.querySelector('#queryScope').value),categoria_id:Number(document.querySelector('#queryCategory').value),codigo_postal_id:Number(document.querySelector('#queryPostal').value),mode:queryMode,user_message:(document.querySelector('#promptText').value||document.querySelector('#searchText').value).trim()};}
async function prepareDPIAQuery(){
 if(!currentEmail){openAuth();return;}
 if(queryBusy)return;
 show('consultPage');const status=document.querySelector('#queryStatus');
 if(media.length){status.textContent='La interpretación de adjuntos todavía no está disponible. Prepará una consulta de texto.';return;}
 const body=queryBody();if(!body.user_message){status.textContent='Escribí tu pedido.';return;}
 queryBusy=true;invalidateQuery();status.textContent='Preparando tu consulta…';
 try{
  const response=await fetch('/api/consultas/preparar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(45000)});
  const data=await response.json();if(!response.ok||!data.success)throw new Error(data.error||'No se pudo preparar la consulta.');
  queryPrepared={body,fingerprint:JSON.stringify(body)};document.querySelector('#promptResult').textContent=data.summary;document.querySelector('#promptResult').hidden=false;
  document.querySelector('#generateQuery').hidden=false;document.querySelector('#generateQuery').disabled=!data.generation_available;
  status.textContent=data.generation_available?'Revisá el resumen y generá los candidatos.':'La generación está temporalmente no disponible.';
 }catch(error){status.textContent=error.name==='TimeoutError'?'La preparación tardó demasiado. Reintentá.':(error.message||'No se pudo preparar la consulta.');}
 finally{queryBusy=false;}
}
async function generateDPIAQuery(){
 if(queryBusy||!queryPrepared)return;
 if(media.length){invalidateQuery();document.querySelector('#queryStatus').textContent='La interpretación de adjuntos todavía no está disponible.';return;}
 if(JSON.stringify(queryBody())!==queryPrepared.fingerprint){invalidateQuery();document.querySelector('#queryStatus').textContent='El pedido cambió. Prepará nuevamente la consulta.';return;}
 queryBusy=true;const button=document.querySelector('#generateQuery'),status=document.querySelector('#queryStatus');button.disabled=true;status.textContent='Generando candidatos…';
 try{
  const response=await fetch('/api/consultas/generar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(queryPrepared.body),signal:AbortSignal.timeout(120000)});
  const data=await response.json();if(!response.ok||!data.success)throw new Error(data.error||'No se pudo generar el resultado.');
  const container=document.querySelector('#queryResults');container.replaceChildren();
  if(data.result.needs_clarification){status.textContent=data.result.clarifying_question;return;}
  status.textContent='Candidatos generados. Precios y disponibilidad pendientes de verificación.';
  for(const row of data.rows){const card=document.createElement('article');card.className='prompt-result';const title=document.createElement('strong');title.textContent=row.Producto;const detail=document.createElement('p');detail.textContent=row.descripcion;const prices=document.createElement('small');prices.textContent=`Amazon: ${row.precio_amazon} · eBay: ${row.precio_ebay} · AliExpress: ${row.precio_aliexpress}`;card.append(title,detail,prices);container.append(card);}
  const download=document.createElement('button');download.type='button';download.textContent='Descargar JSON';download.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data.result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='dpia-results.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};container.append(download);
 }catch(error){status.textContent=error.message||'No se pudo generar la consulta.';}
 finally{queryBusy=false;button.disabled=false;}
}
document.querySelector('#queryScope').addEventListener('change',()=>refreshQuerySelectors());
for(const id of ['queryCategory','queryPostal','promptText','searchText'])document.querySelector('#'+id).addEventListener('input',invalidateQuery);
document.querySelector('#generateQuery').onclick=generateDPIAQuery;
