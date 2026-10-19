/* Read-only dashboard. Never infer agent deployment from existing paper trades. */
(async function(){
 const el=id=>document.getElementById(id);
 const set=(id,v)=>{if(el(id))el(id).textContent=v};
 const money=n=>Number(n).toLocaleString('en-US',{style:'currency',currency:'USD'});
 try {
  const response=await fetch('/api/paper/status',{cache:'no-store'});
  if(!response.ok)throw new Error('HTTP '+response.status);
  const data=await response.json();
  if(!data.available){set('agent-note','Paper snapshot unavailable. Research agents not deployed. '+(data.reason||''));return}
  const closed=(data.trades||[]).filter(t=>t.status==='CLOSED'&&Number.isFinite(Number(t.pnl)));
  const wins=closed.filter(t=>Number(t.pnl)>0).length;
  set('agent-trades',String(closed.length));
  set('agent-winrate',closed.length?(100*wins/closed.length).toFixed(1)+'%':'No closed trades');
  set('agent-net',money(data.realized_pnl||0));
  set('agent-last',data.last_scan?new Date(data.last_scan).toLocaleString():'No scan yet');
  const chronological=[...closed].sort((a,b)=>String(a.exit_time).localeCompare(String(b.exit_time)));
  let equity=Number(data.starting_cash||500),peak=equity,dd=0;
  for(const t of chronological){equity+=Number(t.pnl);peak=Math.max(peak,equity);if(peak>0)dd=Math.max(dd,100*(peak-equity)/peak)}
  set('agent-dd',closed.length?dd.toFixed(1)+'%':'—');
  set('agent-note','Showing available saved stock paper trades only. Research agents: not deployed. Options trades and unrealized P/L are excluded. Only the latest 100 saved trades may be shown.');
 }catch(e){set('agent-note','Could not load paper metrics: '+e.message)}
})();
