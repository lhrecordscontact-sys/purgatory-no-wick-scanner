(() => {
  const $ = id => document.getElementById(id);
  const money = n => Number.isFinite(Number(n)) ? '$' + Number(n).toFixed(2) : '—';
  const text = (id, value) => { $(id).textContent = value; };
  const et = v => v ? new Date(v).toLocaleString('en-US', {timeZone:'America/New_York', month:'numeric', day:'numeric', hour:'numeric', minute:'2-digit'}) : '—';
  async function refresh() {
    try {
      const response = await fetch('/api/paper/status', {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const d = await response.json();
      if (!d.available) {
        text('paper-status', 'Paper account not connected: ' + (d.reason || 'snapshot unavailable'));
        return;
      }
      text('paper-balance', money(d.realized_balance));
      text('paper-pnl', money(d.realized_pnl));
      text('paper-open', String(d.open_positions.length));
      text('paper-updated', d.last_scan ? new Date(d.last_scan).toLocaleString() : 'No market-hours scan yet');
      text('paper-status', 'Saved GitHub paper snapshot · delayed, not live brokerage data');
      const tbody = $('paper-trades');
      tbody.replaceChildren();
      if (!d.trades.length) {
        const tr = document.createElement('tr'), td = document.createElement('td');
        td.colSpan = 10; td.textContent = 'No simulated trades yet'; tr.append(td); tbody.append(tr);
      }
      for (const t of d.trades.slice(0, 100)) {
        const tr = document.createElement('tr');
        for (const v of [t.symbol,t.side,t.status,money(t.entry),money(t.stop),money(t.target),String(t.shares),et(t.entry_time),et(t.exit_time),t.status==='CLOSED'?money(t.pnl):'Open']) {
          const td=document.createElement('td'); td.textContent=v; tr.append(td);
        }
        tbody.append(tr);
      }
    } catch (e) { text('paper-status', 'Paper account unavailable: ' + e.message); }
  }
  refresh();
  setInterval(refresh, 60000);
})();