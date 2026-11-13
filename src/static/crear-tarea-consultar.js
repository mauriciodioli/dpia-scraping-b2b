/* Reuse the existing Consultar view and its submit handlers. */
(()=>{'use strict';
  if(new URLSearchParams(location.search).get('dpia_task_draft')!=='1')return;
  let draft;try{draft=JSON.parse(sessionStorage.getItem('dpia-new-task-draft')||'null')}catch(_){}
  if(!draft||typeof draft.prompt!=='string'||!draft.prompt.trim())return;
  const nav=document.querySelector('nav button[data-page="consultPage"]');
  const input=document.getElementById('promptText');
  if(!nav||!input)return;
  nav.click();input.value=draft.prompt;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();
  history.replaceState(history.state,'',location.pathname+location.hash);
})();
