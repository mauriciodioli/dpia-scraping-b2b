/* V12 demonstration: separate anonymous free, monthly free, and paid credits. Not a billing authority. */
(()=>{
const $=id=>document.getElementById(id),KEY='dpia-credit-demo-v12';
const strings={es:['Puntos FREE','Gratis mensuales','Puntos pagados','Sin iniciar sesión','Renovación mensual (demo)','No vencen mensualmente','Mejorá tu plan','Continuar','No hay pagos conectados. Esto es una demostración.','Simular consumo: −30 pts','Reiniciar demo','Consumidos','puntos cargados'],en:['FREE points','Monthly free','Paid points','Not signed in','Monthly renewal (demo)','No monthly expiration','Upgrade plan','Continue','Payments are not connected. This is a demo.','Simulate usage: −30 pts','Reset demo','Used','points loaded'],pl:['Punkty FREE','Darmowe miesięczne','Punkty płatne','Bez logowania','Odnowienie miesięczne (demo)','Bez miesięcznego wygaśnięcia','Ulepsz plan','Kontynuuj','Płatności nie są podłączone. To demo.','Symuluj zużycie: −30 pkt','Resetuj demo','Zużyto','załadowanych punktów'],it:['Punti FREE','Gratis mensili','Punti acquistati','Senza accesso','Rinnovo mensile (demo)','Non scadono ogni mese','Migliora piano','Continua','Pagamenti non collegati. Questa è una demo.','Simula consumo: −30 pt','Reimposta demo','Utilizzati','punti caricati']};
const tr=i=>(strings[$('languageSelect').value]||strings.es)[i];
let s;try{s=JSON.parse(localStorage.getItem(KEY)||'null')}catch{};
if(!s||!Number.isFinite(s.anonymous)||!Number.isFinite(s.monthly)||!Number.isFinite(s.paid))s={anonymous:30,monthly:100,paid:0,anonUsed:0,monthlyUsed:0,paidUsed:0,month:new Date().toISOString().slice(0,7)};
let logged=false,chosen=300;
const save=()=>localStorage.setItem(KEY,JSON.stringify(s));
function refreshSession(){logged=!!(document.getElementById('userBtn')?.textContent||'').match(/@/);}
function render(){refreshSession();const free=logged?s.monthly:s.anonymous,paid=logged?s.paid:0,used=logged?s.monthlyUsed+s.paidUsed:s.anonUsed,total=free+paid+used,pct=total?Math.round(100*used/total):0;
$('walletNum').textContent=free+paid;$('balanceNum').textContent=free+paid;$('freeRemaining').textContent=free;$('paidRemaining').textContent=paid;$('freeCaption').textContent=logged?tr(1):tr(0);$('paidCaption').textContent=tr(2);$('freeRenew').textContent=logged?tr(4):tr(3);$('paidDetail').textContent=tr(5);$('balanceLabel').textContent=logged?tr(1)+' + '+tr(2):tr(0);$('openUpgrade').firstChild.textContent='✦ '+tr(6)+' ';$('usageTitle').textContent=tr(11);$('usagePct').textContent=pct+'%';$('usageUsed').textContent=used+' '+tr(11).toLowerCase();$('usageTotal').textContent=total+' '+tr(12);$('creditMeterFill').style.width=pct+'%';$('creditMeterFill').style.background=pct<50?'#30D49A':pct<80?'#ffaf35':'#ff5668';$('creditMeter').setAttribute('aria-valuenow',pct);$('simulateUsage').textContent=tr(9);$('resetUsage').textContent=tr(10);$('simulateUsage').disabled=free+paid<30;$('demoTopup').hidden=true;
}
function consume(n){refreshSession();if(logged){const fromFree=Math.min(n,s.monthly);s.monthly-=fromFree;s.monthlyUsed+=fromFree;const fromPaid=Math.min(n-fromFree,s.paid);s.paid-=fromPaid;s.paidUsed+=fromPaid;}else{const x=Math.min(n,s.anonymous);s.anonymous-=x;s.anonUsed+=x;}save();render();}
$('simulateUsage').onclick=()=>consume(30);
$('resetUsage').onclick=()=>{s={anonymous:30,monthly:100,paid:0,anonUsed:0,monthlyUsed:0,paidUsed:0,month:new Date().toISOString().slice(0,7)};save();render()};
const overlay=$('upgradeOverlay');$('openUpgrade').onclick=()=>{overlay.hidden=false};$('closeUpgrade').onclick=()=>overlay.hidden=true;overlay.addEventListener('click',e=>{if(e.target===overlay)overlay.hidden=true});document.addEventListener('keydown',e=>{if(e.key==='Escape')overlay.hidden=true});
function choose(n){chosen=n;document.querySelectorAll('[data-upgrade]').forEach(b=>b.classList.toggle('active',Number(b.dataset.upgrade)===n));$('upgradeContinue').textContent=tr(7)+' · '+n+' pts';}
document.querySelectorAll('[data-upgrade]').forEach(b=>b.onclick=()=>choose(Number(b.dataset.upgrade)));$('upgradeContinue').onclick=()=>{$('upgradeNote').textContent=tr(8)};
document.querySelectorAll('.plans [data-points]').forEach(b=>b.onclick=()=>{choose(Number(b.dataset.points));overlay.hidden=false});
$('demoTopup').hidden=true; // No fake purchases: paid credits must only be granted by verified server-side payments.
$('languageSelect').addEventListener('change',()=>queueMicrotask(render));
const obs=new MutationObserver(render);obs.observe($('userBtn'),{childList:true,subtree:true,characterData:true});
// Demo monthly reset, based on browser date; production must use server ledger and billing cycle.
const month=new Date().toISOString().slice(0,7);if(s.month!==month){s.monthly=100;s.monthlyUsed=0;s.month=month;save()}
render();
})();