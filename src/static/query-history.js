/* History and galleries are loaded through authenticated Flask endpoints. */
(()=>{
 const $=id=>document.getElementById(id);
 let generation=0,offset=0,chosen=null,imageBusy=false,identity=null;
 function showQuery(){
  $('currentQueryPanel').hidden=false;$('queryHistoryPanel').hidden=true;
  $('queryCurrentTab').setAttribute('aria-selected','true');$('queryHistoryTab').setAttribute('aria-selected','false');
 }
 async function history(append=false){
  if(!currentEmail){openAuth();return;}
  const email=currentEmail,serial=++generation;
  if(!append){offset=0;$('queryHistoryList').replaceChildren();$('ArchivosCargados').replaceChildren(new Option('Seleccioná una búsqueda',''));}
  $('queryHistoryStatus').textContent='Cargando historial…';$('moreQueryHistory').hidden=true;
  try{
   const response=await fetch('/api/consultas/historial?offset='+offset,{cache:'no-store'}),data=await response.json();
   if(serial!==generation||email!==currentEmail)return;
   if(response.status===401){openAuth();return;}
   if(!response.ok||!data.success||!Array.isArray(data.operations))throw new Error(data.error||'No se pudo consultar el historial.');
   const states={reserved:'Reservada',dispatching:'En curso',pending:'Pendiente de confirmación',consumed:'Finalizada',released:'No iniciada'};
   for(const row of data.operations){
    const label=[row.query,row.source,row.city,row.created_at?new Date(row.created_at).toLocaleString():null].filter(Boolean).join(' · ');
    const option=new Option(label,row.operation_id);option.dataset.trabajoId=row.operation_id;$('ArchivosCargados').add(option);
    const card=document.createElement('article');card.className='source-result';
    const title=document.createElement('strong');title.textContent=label;
    const detail=document.createElement('p');detail.textContent=`${states[row.state]||'Estado sin confirmar'} · ${row.product_count} productos · ${row.category||''}`;
    const button=document.createElement('button');button.type='button';button.textContent='Consultar resultados';button.onclick=()=>loadQueryOperation(row.operation_id);
    card.append(title,detail,button);$('queryHistoryList').append(card);
   }
   offset+=data.operations.length;$('moreQueryHistory').hidden=!data.has_more;
   $('queryHistoryStatus').textContent=$('queryHistoryList').children.length?'':'Todavía no tenés búsquedas guardadas en esta PWA.';
  }catch(error){if(serial===generation&&email===currentEmail)$('queryHistoryStatus').textContent=error.message;}
 }
 function showHistory(){
  if(!currentEmail){openAuth();return;}
  $('currentQueryPanel').hidden=true;$('queryHistoryPanel').hidden=false;
  $('queryCurrentTab').setAttribute('aria-selected','false');$('queryHistoryTab').setAttribute('aria-selected','true');history();
 }
 function gallery(data){
  $('productGallery').replaceChildren();
  for(const value of data.images||[]){const url=safeQueryUrl(value);if(!url)continue;const label=document.createElement('label'),check=document.createElement('input'),img=document.createElement('img');check.type='checkbox';check.name='publicationPhoto';check.value=url;check.checked=true;img.src=url;img.alt='Imagen del producto';img.loading='lazy';img.onerror=()=>label.remove();label.append(check,img);$('productGallery').append(label);}
  $('queryPublicationForm').hidden=!(data.status==='complete'&&data.images?.length);
  $('saveQueryPublication').disabled=!!data.publication;
  if(data.publication)$('queryPublicationStatus').textContent='Publicación guardada · ID '+data.publication.id;
  const d=data.diagnostics;
  const diagnosis=d?`Precio: ${d.price??'N/D'} · Rating: ${d.rating??'N/D'} · Reseñas: ${d.rating_missing?'No exigidas sin rating':d.reviews}. `:'';
  const reasons=d?Object.entries(d.checks).filter(([,ok])=>!ok).map(([key])=>({precio:'precio',rating:'rating',resenas:'reseñas'}[key])):[];
  const text=data.status==='filtered'?`No cumple los filtros de ${reasons.join(', ')}. Podés ajustarlos antes de preparar imágenes.`:data.status==='complete'?(data.images?.length?'Imágenes preparadas.':'La API no devolvió imágenes válidas.'):data.error||'Preparación pendiente de confirmación.';
  $('productImagesStatus').textContent=diagnosis+text;
 }
 function openImages(operation,index,product,stage){
  if(!currentEmail){openAuth();return;}
  chosen={operation,index,email:currentEmail};$('queryPublicationForm').hidden=true;$('queryPublicationStatus').textContent='';$('publicationTitle').value=product.title.slice(0,120);$('publicationDescription').value=product.title;$('publicationCurrency').value=product.currency||'';$('productImagesTitle').textContent=product.title;
  $('imagePriceMin').value='0';$('imagePriceMax').value='';$('imageRatingMin').value='4.4';$('imageReviewsMin').value='50';
  $('productGallery').replaceChildren();$('productImagesStatus').textContent='Se usarán el ASIN y los datos del producto guardado. Preparar imágenes no publica el producto.';
  if(stage){if(stage.filters){$('imagePriceMin').value=stage.filters.precio_minimo;$('imagePriceMax').value=stage.filters.precio_maximo??'';$('imageRatingMin').value=stage.filters.rating_minimo;$('imageReviewsMin').value=stage.filters.resenas_minimas;}gallery(stage);}
  $('productImagesOverlay').hidden=false;$('closeProductImages').focus();
 }
 async function prepareImages(){
  if(imageBusy||!chosen||chosen.email!==currentEmail)return;
  const form=$('productImagesForm');if(!form.reportValidity())return;
  const target={...chosen};imageBusy=true;$('prepareProductImages').disabled=true;
  $('productImagesStatus').textContent='Consultando imágenes en DPIA…';
  const filters={precio_minimo:Number($('imagePriceMin').value),precio_maximo:$('imagePriceMax').value===''?null:Number($('imagePriceMax').value),rating_minimo:Number($('imageRatingMin').value),resenas_minimas:Number($('imageReviewsMin').value)};
  try{
   const response=await fetch('/api/consultas/operaciones/'+encodeURIComponent(target.operation)+'/imagenes',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_index:target.index,filters}),signal:AbortSignal.timeout(200000)}),data=await response.json();
   if(currentEmail!==target.email||chosen?.operation!==target.operation||chosen?.index!==target.index)return;
   if(!response.ok||!data.success)throw new Error(data.error||'No se pudieron preparar las imágenes.');
   gallery(data);
  }catch(error){if(currentEmail===target.email)$('productImagesStatus').textContent=error.name==='TimeoutError'?'La preparación quedó pendiente. Consultá el resultado guardado antes de reintentar.':error.message;}
  finally{imageBusy=false;$('prepareProductImages').disabled=false;}
 }
 async function publish(){
  if(imageBusy||!chosen||chosen.email!==currentEmail||!$('queryPublicationForm').reportValidity())return;
  const target={...chosen};imageBusy=true;$('saveQueryPublication').disabled=true;
  $('queryPublicationStatus').textContent='Guardando publicación…';
  try{
   const response=await fetch('/api/consultas/operaciones/'+encodeURIComponent(target.operation)+'/publicar',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_index:target.index,
    titulo:$('publicationTitle').value,descripcion:$('publicationDescription').value,moneda:$('publicationCurrency').value,
    imagenes:[...document.querySelectorAll('[name="publicationPhoto"]:checked')].map(input=>input.value)})}),data=await response.json();
   if(currentEmail!==target.email)return;
   if(!response.ok||!data.success||!data.guardado)throw new Error(data.error||'No se pudo confirmar la publicación.');
   $('queryPublicationStatus').textContent='Publicación guardada · ID '+data.publicacion_id+' · Disponible en Mi perfil → Mis publicaciones.';
   const button=document.createElement('button');button.type='button';button.textContent='Ver mis publicaciones';button.onclick=()=>{$('productImagesOverlay').hidden=true;window.DPIAPublications?.openProfile();};$('queryPublicationStatus').append(button);
  }catch(error){$('queryPublicationStatus').textContent=error.message;$('saveQueryPublication').disabled=false;}
  finally{imageBusy=false;}
 }
 $('queryPublicationForm').onsubmit=e=>{e.preventDefault();publish();};
 function imageButton(operation,index,product,stage){
  const button=document.createElement('button');button.type='button';button.textContent=stage?.status==='complete'?'Ver imágenes / ajustar filtros':'Preparar imágenes';
  button.onclick=()=>openImages(operation,index,product,stage);return button;
 }
 $('queryCurrentTab').onclick=showQuery;$('queryHistoryTab').onclick=showHistory;
 $('refreshQueryHistory').onclick=()=>history();$('moreQueryHistory').onclick=()=>history(true);
 $('ArchivosCargados').onchange=e=>{if(e.target.value)loadQueryOperation(e.target.value);};
 $('productImagesForm').onsubmit=e=>{e.preventDefault();prepareImages();};
 function closeImages(){if(imageBusy)return;$('productImagesOverlay').hidden=true;chosen=null;}
 $('closeProductImages').onclick=closeImages;
 $('productImagesOverlay').onclick=e=>{if(e.target===$('productImagesOverlay'))closeImages();};
 document.addEventListener('keydown',e=>{if(e.key==='Escape')closeImages();});
 new MutationObserver(()=>{if(identity!==currentEmail){identity=currentEmail;generation++;$('queryHistoryList').replaceChildren();$('ArchivosCargados').replaceChildren(new Option('Seleccioná una búsqueda',''));$('productImagesOverlay').hidden=true;chosen=null;}}).observe($('userBtn'),{childList:true,subtree:true,characterData:true});
 window.DPIAHistory={showQuery,showHistory,imageButton};
})();
