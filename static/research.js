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
