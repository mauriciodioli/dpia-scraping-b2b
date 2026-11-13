/* Standalone view; reuses original situationJourney markup and styles. */
(()=>{'use strict';
const journey=document.getElementById('situationJourney'),choices=document.getElementById('situationChoices'),stage=document.getElementById('situationSearchStage'),input=document.getElementById('searchText'),title=document.getElementById('situationSelectedTitle'),restore=document.getElementById('restoreSituationActions'),feedback=document.getElementById('taskFeedback');
let situation=null;
function step(n){journey.querySelectorAll('[data-journey-step]').forEach(el=>{const k=Number(el.dataset.journeyStep);el.classList.toggle('is-complete',k<n);if(k===n)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current')})}
function showSearch(){choices.hidden=true;stage.hidden=false;restore.hidden=false;step(2);input.focus()}
function reset(){choices.hidden=false;stage.hidden=true;restore.hidden=true;step(1)}
journey.querySelectorAll('[data-situation]').forEach(btn=>btn.addEventListener('click',()=>{situation=btn.dataset.situation;journey.querySelectorAll('[data-situation]').forEach(b=>b.setAttribute('aria-pressed',String(b===btn)));title.textContent=btn.querySelector('strong').textContent;showSearch()}));
document.getElementById('skipSituation').addEventListener('click',()=>{situation=null;title.textContent='';showSearch()});
document.getElementById('changeSituation').addEventListener('click',reset);
document.getElementById('restoreSituation').addEventListener('click',reset);
function prepare(){const prompt=input.value.trim();if(!prompt){feedback.textContent='Describí qué querés que haga tu agente.';input.focus();return;}sessionStorage.setItem('dpia-new-task-draft',JSON.stringify({situation,prompt,origin:'crear-tarea'}));window.location.assign('/?dpia_task_draft=1');}
document.getElementById('sendBtn').addEventListener('click',prepare);
input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();prepare()}});
})();