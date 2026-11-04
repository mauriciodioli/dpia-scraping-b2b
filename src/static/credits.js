/* Server-authoritative six-execution allowance. No fake purchases or local balances. */
(()=>{
 const $=id=>document.getElementById(id),tr=text=>window.DPIAI18N?.translate(text)||text;
 let testEnabled=false;
 let credits=null,account=null,generation=0,chosen=300,returnToQuery=false;
 const states={reserved:'Reservada',dispatching:'En curso o pendiente',pending:'Pendiente de confirmación',consumed:'Consumida',released:'Liberada'};
 function render(){
  const logged=typeof currentEmail==='string'&&!!currentEmail;
  const available=credits?.available??'—',reserved=credits?.reserved??'—',consumed=credits?.consumed??'—',initial=credits?.initial??'—';
  $('walletNum').textContent=available;$('balanceNum').textContent=available;$('scrapingBalanceUnit').textContent=tr('ejec.');
  $('balanceLabel').textContent=tr('Scrapings disponibles');$('freeCaption').textContent=tr('Iniciales');$('freeRemaining').textContent=initial;
  $('freeRenew').textContent=tr('Por usuario autenticado');$('paidCaption').textContent=tr('Reservadas o pendientes');$('paidRemaining').textContent=reserved;
  $('paidDetail').textContent=tr('Retenidas hasta confirmar el resultado');$('consumedExecutions').textContent=consumed;$('availableExecutions').textContent=available;
  $('usageTitle').textContent=tr('Consumidas');const percent=credits?Math.round(100*credits.consumed/credits.initial):0;
  $('usagePct').textContent=credits?percent+'%':'—';$('usageUsed').textContent=consumed+' '+tr('consumidas');$('usageTotal').textContent=initial+' '+tr('iniciales');
  $('creditMeterFill').style.width=percent+'%';$('creditMeterFill').style.background=percent<50?'#30d49a':percent<80?'#ffaf35':'#ff5668';$('creditMeter').setAttribute('aria-valuenow',String(percent));
  $('creditDemoHint').textContent=tr(logged?'Un punto representa una ejecución de scraping. No se descuentan tokens.':'Iniciá sesión para consultar tus ejecuciones.');
  $('creditOperations').replaceChildren();
  for(const operation of credits?.operations||[]){
   const row=document.createElement('li'),name=document.createElement('span'),button=document.createElement('button');
   name.textContent=operation.source+' · '+tr(states[operation.state]||'Pendiente de confirmación');button.type='button';button.textContent=tr('Ver resultado');
   button.onclick=()=>loadQueryOperation(operation.operation_id);row.append(name,button);$('creditOperations').append(row);
  }
  $('addTestCredits').hidden=!logged||!testEnabled;
  choose(chosen);
 }
 async function refresh(){
  const current=typeof currentEmail==='string'?currentEmail:null,serial=++generation;
  if(account!==current){credits=null;testEnabled=false;account=current;}
  if(!current){credits=null;render();return;}
  try{
   const response=await fetch('/api/consultas/creditos',{cache:'no-store'}),data=await response.json();
   if(serial!==generation||currentEmail!==current)return;
   if(!response.ok||!data.success||!data.credits)throw new Error(data.error||'No se pudieron consultar las ejecuciones.');
   credits=data.credits;testEnabled=!!data.test_credits_enabled;$('creditStatus').textContent='';
  }catch(error){if(serial!==generation)return;credits=null;testEnabled=false;$('creditStatus').textContent=tr(error.message);}
  render();
 }
 function choose(points){
  chosen=points;document.querySelectorAll('[data-upgrade]').forEach(button=>button.classList.toggle('active',Number(button.dataset.upgrade)===points));
  $('upgradeContinue').textContent=tr('Pagos no habilitados');$('upgradeContinue').disabled=true;
 }
 function open(insufficient=false,data=null){
  if(!currentEmail){openAuth();return;}
  returnToQuery=insufficient;$('upgradeTitle').textContent=tr(insufficient?'Crédito insuficiente':'Agregar crédito');
  $('upgradeSubtitle').textContent=tr('Paquetes de demostración. No acreditan ejecuciones.');
  $('insufficientCreditSummary').hidden=!insufficient;$('cancelCreditUpgrade').hidden=!insufficient;
  if(insufficient){$('insufficientAvailable').textContent=data?.credits?.available??0;$('insufficientRequired').textContent=data?.required??1;$('insufficientMissing').textContent=data?.missing??1;}
  $('upgradeNote').textContent=tr('Precios de referencia. Sin cobros ni acreditaciones.');$('upgradeOverlay').hidden=false;
 }
 function close(){
  $('upgradeOverlay').hidden=true;
  if(returnToQuery){show('consultPage');returnToQuery=false;}
 }
 $('addTestCredits').onclick=async()=>{
  const button=$('addTestCredits');if(button.disabled)return;button.disabled=true;
  try{
   const response=await fetch('/api/consultas/creditos/prueba',{method:'POST',headers:{'Content-Type':'application/json','X-DPIA-Test-Credits':'1'},body:'{}'}),data=await response.json();
   if(!response.ok||!data.success)throw new Error(data.error||'No se pudo agregar ejecuciones.');
   await refresh();
  }catch(error){$('creditStatus').textContent=error.message;}
  finally{button.disabled=false;}
 };
 $('openUpgrade').onclick=()=>open();$('closeUpgrade').onclick=close;$('cancelCreditUpgrade').onclick=close;
 $('upgradeOverlay').onclick=event=>{if(event.target===$('upgradeOverlay'))close();};
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('upgradeOverlay').hidden)close();});
 document.querySelectorAll('[data-upgrade]').forEach(button=>button.onclick=()=>choose(Number(button.dataset.upgrade)));
 document.querySelectorAll('.plans [data-points]').forEach(button=>button.onclick=()=>{choose(Number(button.dataset.points));open();});
 $('languageSelect').addEventListener('change',()=>queueMicrotask(render));
 new MutationObserver(()=>refresh()).observe($('userBtn'),{childList:true,subtree:true,characterData:true});
 window.DPIACredits={refresh,insufficient:data=>{refresh();open(true,data);}};
 render();refresh();
})();
