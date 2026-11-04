/* Owned publications only; IDs come from confirmed MySQL records. */
(()=>{
 const $=id=>document.getElementById(id);
 let generation=0,offset=0,selected=null,deleting=false,previousFocus=null;
 function clear(){
  generation++;offset=0;selected=null;
  $('publicationHistory').replaceChildren();$('profileOverlay').hidden=true;
  $('deletePublicationOverlay').hidden=true;
 }
 function close(){if(deleting)return;clear();$('userBtn').focus();}
 function cancelDelete(){
  if(deleting)return;
  selected=null;$('deletePublicationOverlay').hidden=true;
  $('profileOverlay').removeAttribute('aria-hidden');previousFocus?.focus();
 }
 function requestDelete(publication,card,button){
  if(deleting)return;
  selected={publication,card,email:currentEmail};previousFocus=button;
  $('deletePublicationDescription').textContent=`¿Eliminar «${publication.titulo}»? Esta acción elimina únicamente esta publicación y sus asociaciones.`;
  $('deletePublicationStatus').textContent='';$('deletePublicationConfirm').disabled=false;
  $('profileOverlay').setAttribute('aria-hidden','true');
  $('deletePublicationOverlay').hidden=false;$('deletePublicationCancel').focus();
 }
 function cardFor(publication){
  const card=document.createElement('article');card.className='scraped-product';
  card.dataset.publicationId=String(publication.id);
  const imageUrl=safeQueryUrl(publication.imagen);
  if(imageUrl){const image=document.createElement('img');image.src=imageUrl;image.alt='';image.loading='lazy';image.onerror=()=>image.remove();card.append(image);}
  const title=document.createElement('strong');title.textContent=publication.titulo;
  const description=document.createElement('p');description.textContent=publication.descripcion||'';
  const price=document.createElement('p');price.textContent=publication.precio==null?'Precio no informado':`${publication.precio} ${publication.moneda||''}`.trim();
  card.append(title,description,price);
  if(publication.can_delete&&Number.isInteger(publication.id)&&publication.id>0){
   const button=document.createElement('button');button.type='button';button.textContent='Eliminar publicación';
   button.onclick=()=>requestDelete(publication,card,button);card.append(button);
  }
  return card;
 }
 async function load(append=false){
  if(!currentEmail){openAuth();return;}
  const email=currentEmail,serial=++generation;
  if(!append){offset=0;$('publicationHistory').replaceChildren();}
  $('profileStatus').textContent='Cargando tus publicaciones…';$('moreMyPublications').hidden=true;
  try{
   const response=await fetch('/api/publicaciones/mias?offset='+offset,{cache:'no-store'}),data=await response.json();
   if(serial!==generation||email!==currentEmail)return;
   if(response.status===401){clear();openAuth();return;}
   if(!response.ok||!data.success)throw new Error(data.error||'No se pudieron consultar tus publicaciones.');
   for(const publication of data.publicaciones)$('publicationHistory').append(cardFor(publication));
   offset+=data.publicaciones.length;$('moreMyPublications').hidden=!data.has_more;
   $('profileStatus').textContent=$('publicationHistory').children.length?'':'Todavía no tenés publicaciones guardadas.';
  }catch(error){if(serial===generation&&email===currentEmail)$('profileStatus').textContent=error.message;}
 }
 async function confirmDelete(){
  if(deleting||!selected||selected.email!==currentEmail)return;
  deleting=true;const target=selected;$('deletePublicationConfirm').disabled=true;
  $('deletePublicationStatus').textContent='Eliminando publicación…';
  try{
   const response=await fetch('/api/publicaciones/'+target.publication.id,{method:'DELETE',headers:{'X-DPIA-Action':'delete-publication'}}),data=await response.json();
   if(target.email!==currentEmail)return;
   if(!response.ok||!data.success||!data.eliminado||data.publicacion_id!==target.publication.id)throw new Error(data.error||'No se pudo confirmar la eliminación. Actualizá el listado antes de reintentar.');
   target.card.remove();offset=Math.max(0,offset-1);
   $('deletePublicationOverlay').hidden=true;$('profileOverlay').removeAttribute('aria-hidden');selected=null;
   // Refresh the currently visible local list, preserving its filters.
   if(typeof page!=='undefined'&&page==='mapPage')loadLocalPublications();
   $('profileStatus').textContent='Publicación eliminada.';$('closeProfile').focus();
  }catch(error){if(target.email===currentEmail)$('deletePublicationStatus').textContent=error.message;}
  finally{deleting=false;$('deletePublicationConfirm').disabled=false;}
 }
 function openProfile(){
  if(!currentEmail){openAuth();return;}
  $('profileOverlay').removeAttribute('aria-hidden');$('profileOverlay').hidden=false;
  $('profileEmail').textContent=currentEmail;$('closeProfile').focus();load();
 }
 $('closeProfile').onclick=close;$('reloadMyPublications').onclick=()=>load();
 $('moreMyPublications').onclick=()=>load(true);
 $('deletePublicationCancel').onclick=cancelDelete;$('deletePublicationConfirm').onclick=confirmDelete;
 $('profileOverlay').onclick=e=>{if(e.target===$('profileOverlay'))close();};
 $('deletePublicationOverlay').onclick=e=>{if(e.target===$('deletePublicationOverlay'))cancelDelete();};
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(!$('deletePublicationOverlay').hidden)cancelDelete();else if(!$('profileOverlay').hidden)close();}});
 $('profileLogout').onclick=async()=>{
  if(deleting)return;
  try{const response=await fetch('/api/auth/logout',{method:'POST'});if(!response.ok)throw new Error('No se pudo cerrar la sesión.');clear();updateUser(null);notify('Sesión cerrada');}
  catch(error){$('profileStatus').textContent=error.message;}
 };
 let identity=typeof currentEmail==='string'?currentEmail:null;
 new MutationObserver(()=>{const next=typeof currentEmail==='string'?currentEmail:null;if(next!==identity){identity=next;clear();}}).observe($('userBtn'),{childList:true,subtree:true,characterData:true});
 window.DPIAPublications={openProfile,refresh:()=>load()};
})();
