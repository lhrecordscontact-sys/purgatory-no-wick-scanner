const smcButton = document.getElementById("smc-scan");
smcButton.addEventListener("click", async () => {
  const status = document.getElementById("smc-status");
  const body = document.getElementById("smc-results");
  smcButton.disabled = true;
  status.textContent = "Scanning historical 5-minute bars...";
  const params = new URLSearchParams({
    symbols: document.getElementById("symbols").value,
    min_rate: document.getElementById("smc-rate").value,
    min_trades: document.getElementById("smc-trades").value,
    rr: document.getElementById("rr").value
  });
  try {
    const response = await fetch("/api/smc/scan?" + params.toString());
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    status.textContent = data.qualified_count + " qualified / " + data.count + " checked";
    body.replaceChildren();
    for (const r of data.results) {
      const tr = document.createElement("tr");
      const values = r.error ? [r.symbol, "ERROR", r.error] :
        [r.symbol, r.qualified ? "PASS" : "NO", r.win_rate + "%",
         r.trades, r.profit_factor, r.avg_r, r.max_drawdown_r, r.last_signal];
      for (const v of values) {
        const td = document.createElement("td");
        td.textContent = String(v);
        tr.appendChild(td);
      }
      body.appendChild(tr);
    }
  } catch (e) {
    status.textContent = "Scan failed: " + String(e);
  } finally {
    smcButton.disabled = false;
  }
});