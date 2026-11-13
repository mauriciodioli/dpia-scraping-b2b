/* Handoff to existing index.html controllers, without cloning Consultar. */
(()=>{'use strict';
if(new URLSearchParams(location.search).get('dpia_task_draft')!=='1')return;
let draft;try{draft=JSON.parse(sessionStorage.getItem('dpia-new-task-draft')||'null')}catch(_){}
if(!draft||draft.origin!=='crear-tarea')return;
const actions={explore:'exploreBtn',novel:'novelBtn',local:'localBtn',exterior:'exteriorBtn',search:'sendBtn'};
if(!Object.hasOwn(actions,draft.action))return;
function ready(){return typeof setQueryJourney==='function'&&typeof show==='function'&&document.getElementById(actions[draft.action])&&document.getElementById('queryScope')}
function resume(){if(!ready())return false;
try{
 if(draft.situation)setQueryJourney(draft.situation);else setQueryJourney(null);
 if(draft.action==='search')document.getElementById('searchText').value=draft.prompt||'';
 document.getElementById(actions[draft.action]).click();
 sessionStorage.removeItem('dpia-new-task-draft');history.replaceState(history.state,'',location.pathname+location.hash);return true;
}catch(error){console.error('DPIA crear tarea: error al recuperar el recorrido',error);return false}}
if(!resume())window.addEventListener('load',()=>{resume()},{once:true});
})();
