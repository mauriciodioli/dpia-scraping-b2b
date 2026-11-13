/* Reuse the original situationJourney DOM and its existing event handlers. */
(()=>{
 const journey=document.getElementById('situationJourney');
 const homeMount=document.getElementById('situationHomeMount');
 const agentMount=document.getElementById('agentCreateTaskMount');
 const agentPage=document.getElementById('agentPage');
 if(!journey||!homeMount||!agentMount||!agentPage)return;
 let active=false;
 function restore(){
  if(!active)return;
  active=false;
  homeMount.appendChild(journey);
  agentMount.hidden=true;
 }
 function open(){
  if(agentPage.hidden)return;
  active=true;
  agentMount.appendChild(journey);
  agentMount.hidden=false;
  document.getElementById('changeSituation').click();
  journey.scrollIntoView({block:'start'});
 }
 // The original discovery buttons navigate with show() to Consultar or Local.
 // On navigation, put the original component back in Home, preserving all handlers.
 new MutationObserver(()=>{if(active&&agentPage.hidden)restore();})
  .observe(agentPage,{attributes:true,attributeFilter:['hidden']});
 window.DPIACrearTarea={open};
})();
