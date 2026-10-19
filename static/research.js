(function () {
  const el = id => document.getElementById(id);
  const money = n => Number.isFinite(Number(n)) ? '$' + Number(n).toFixed(2) : '—';
  async function refreshResearch() {
    el('research-status').textContent = 'Checking latest published research…';
    try {
      const response = await fetch('/api/research/latest?t=' + Date.now(), {cache: 'no-store'});
      if (!response.ok) throw new Error('Research API unavailable');
      const data = await response.json();
      if (!data.available || !data.report) {
        el('research-status').textContent = data.reason || 'No completed published research yet.';
        return;
      }
      const r = data.report;
      const selected = r.training_selected_variant;
      const holdout = (selected && r.selected_holdout) || r.baseline_holdout || {};
      const baseline = r.results && r.results.baseline;
      el('research-stocks').textContent = baseline ? baseline.symbols_completed : '—';
      el('research-trades').textContent = holdout.trades ?? '—';
      el('research-win').textContent = Number.isFinite(Number(holdout.win_rate)) ? Number(holdout.win_rate).toFixed(1) + '%' : '—';
      el('research-profit').textContent = money(holdout.net_profit);
      el('research-variant').textContent = selected || 'baseline (no qualified training selection)';
      el('research-date').textContent = r.generated_utc || '—';
      const total = Math.max(0, Number(r.universe_size) || 0);
      const completed = Math.max(0, Math.min(total, Number(r.coverage_completed_in_pass) || 0));
      const pct = total ? completed / total * 100 : 0;
      const bar = el('research-coverage');
      if (bar) bar.value = pct;
      el('research-coverage-label').textContent = total ? pct.toFixed(2) + '% (' + completed.toLocaleString() + ' / ' + total.toLocaleString() + ')' : '—';
      const experiments = r.adaptive_experiments || {};
      const count = Object.keys(experiments).length;
      const agent = r.improvement_agent || {};
      el('research-optimizer-state').textContent = count ? 'Active in latest report' : 'Not confirmed in latest report';
      el('research-experiments').textContent = count ? count + ' generated variations · ' + (agent.status || 'evaluation pending') : 'No generated variations in latest published report.';
      const age = r.generated_utc ? (Date.now() - Date.parse(r.generated_utc)) / 60000 : Infinity;
      el('research-progress-note').textContent = Number.isFinite(age) && age >= 0 ? 'Latest report ' + Math.round(age) + ' minutes old · auto-refresh every 5 minutes' : 'Auto-refresh every 5 minutes';
      el('research-status').textContent = 'Latest backtest loaded · US coverage pass ' + (r.coverage_pass || 1) + ': ' + (r.coverage_completed_in_pass ?? r.symbols_requested ?? '?') + ' / ' + (r.universe_size ?? '?') + ' symbols attempted';
      el('research-note').textContent = 'Research only · independent $500 stock simulations · no combined portfolio or options P/L. ' + (r.research_gate && r.research_gate.reason || 'Not validated for live trading.');
    } catch (err) {
      el('research-status').textContent = 'Could not load research results. Try again shortly.';
    }
  }
  el('research-refresh')?.addEventListener('click', refreshResearch);
  refreshResearch();
  setInterval(refreshResearch, 300000);
})();
