/* Presentation only: existing search, media and discovery handlers remain authoritative. */
(()=>{
 const journey=document.getElementById('situationJourney');
 const choices=document.getElementById('situationChoices');
 const stage=document.getElementById('situationSearchStage');
 const title=document.getElementById('situationSelectedTitle');
 function step(number){journey.querySelectorAll('[data-journey-step]').forEach(item=>{
  const current=Number(item.dataset.journeyStep)===number;
  if(current)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');
  item.classList.toggle('is-complete',Number(item.dataset.journeyStep)<number);
 });}
 journey.querySelectorAll('[data-situation]').forEach(button=>button.addEventListener('click',()=>{
  journey.querySelectorAll('[data-situation]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
  const key=button.querySelector('strong').getAttribute('data-i18n');
  title.setAttribute('data-i18n',key);title.textContent=window.DPIAI18N?.translate(key)||key;
  choices.hidden=true;stage.hidden=false;step(2);
  document.getElementById('searchText').focus();
 }));
 document.getElementById('changeSituation').addEventListener('click',()=>{
  choices.hidden=false;stage.hidden=true;step(1);
  (journey.querySelector('[aria-pressed="true"]')||journey.querySelector('[data-situation]')).focus();
 });
 // Navigation may be asynchronous (catalog preparation or authentication).
 const home=document.getElementById('home');
 new MutationObserver(()=>{
  if(!stage.hidden)step(home.hidden?3:2);
 }).observe(home,{attributes:true,attributeFilter:['hidden']});
})();
