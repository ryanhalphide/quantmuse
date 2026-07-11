const FMT = {
  pct: (x) => (x == null || isNaN(x)) ? "—" : (x * 100).toFixed(1) + "%",
  num: (x) => (x == null || isNaN(x)) ? "—" : x.toFixed(2),
};
const COLORS = { trend_ls: "#58a6ff", trend_lf: "#3fb950", spy: "#8b949e", sixtyforty: "#d29922" };

let equityChart, logScale = false, DATA;

function card(label, value, cls, cmp) {
  return `<div class="card"><div class="label">${label}</div>
    <div class="value ${cls || ""}">${value}</div>
    ${cmp ? `<div class="cmp">${cmp}</div>` : ""}</div>`;
}

function renderCards(d) {
  const t = d.metrics.trend_ls, lf = d.metrics.trend_lf, spy = d.metrics.spy, sf = d.metrics.sixtyforty;
  document.getElementById("cards").innerHTML = [
    card("Trend Sharpe (L/S)", FMT.num(t.sharpe), "pos", `long/flat ${FMT.num(lf.sharpe)}`),
    card("Annual return", FMT.pct(t.ann_return), t.ann_return >= 0 ? "pos" : "neg", `vol ${FMT.pct(t.ann_vol)}`),
    card("Max drawdown", FMT.pct(t.max_drawdown), "neg", `SPY ${FMT.pct(spy.max_drawdown)}`),
    card("Correlation to SPY", FMT.num(t.corr_to_spy), "", "≈0 = diversifying"),
    card("SPY Sharpe", FMT.num(spy.sharpe), "", `60/40 ${FMT.num(sf.sharpe)}`),
  ].join("");
}

function renderEquity(d) {
  const ds = (key, label) => ({
    label, data: d.curves[key].values, borderColor: COLORS[key],
    borderWidth: key.startsWith("trend") ? 2 : 1.2, pointRadius: 0,
    borderDash: key === "sixtyforty" ? [4, 3] : [],
  });
  const ctx = document.getElementById("equityChart");
  equityChart = new Chart(ctx, {
    type: "line",
    data: { labels: d.curves.trend_ls.dates, datasets: [
      ds("trend_ls", "Trend L/S"), ds("trend_lf", "Trend long/flat"),
      ds("spy", "SPY buy & hold"), ds("sixtyforty", "60/40 SPY/TLT"),
    ]},
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#8b949e", maxTicksLimit: 10 }, grid: { color: "#283040" } },
        y: { type: "linear", ticks: { color: "#8b949e" }, grid: { color: "#283040" } },
      },
      plugins: { legend: { labels: { color: "#e6edf3" } } },
    },
  });
}

function renderAnnual(d) {
  new Chart(document.getElementById("annualChart"), {
    type: "bar",
    data: { labels: d.annual.years, datasets: [
      { label: "Trend", data: d.annual.trend.map(v => v == null ? null : v * 100), backgroundColor: "#58a6ff" },
      { label: "SPY", data: d.annual.spy.map(v => v == null ? null : v * 100), backgroundColor: "#8b949e" },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#8b949e" }, grid: { display: false } },
        y: { ticks: { color: "#8b949e", callback: v => v + "%" }, grid: { color: "#283040" } },
      },
      plugins: { legend: { labels: { color: "#e6edf3" } } },
    },
  });
}

function renderBlend(d) {
  const rows = d.blend.map(b => {
    const c = b.sharpe >= (d.metrics.spy.sharpe || 0) ? "pos" : "";
    return `<tr><td>${b.label}</td><td class="${c}">${FMT.num(b.sharpe)}</td>
      <td>${FMT.pct(b.ann_return)}</td><td class="neg">${FMT.pct(b.max_drawdown)}</td></tr>`;
  }).join("");
  document.getElementById("blendTable").innerHTML =
    `<tr><th>Portfolio</th><th>Sharpe</th><th>Ann</th><th>Max DD</th></tr>${rows}`;
}

function renderWeights(d) {
  new Chart(document.getElementById("weightsChart"), {
    type: "bar",
    data: { labels: d.weights.map(w => w.symbol), datasets: [{
      data: d.weights.map(w => +(w.weight * 100).toFixed(1)),
      backgroundColor: d.weights.map(w => w.weight >= 0 ? "#3fb950" : "#f85149"),
    }]},
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#8b949e", callback: v => v + "%" }, grid: { color: "#283040" } },
        y: { ticks: { color: "#e6edf3" }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderRollingCorr(d) {
  const rc = d.rolling_corr;
  if (!rc || !rc.dates || !rc.dates.length) return;
  new Chart(document.getElementById("rollingCorrChart"), {
    type: "line",
    data: { labels: rc.dates, datasets: [
      { label: "63d correlation to SPY", data: rc.values, borderColor: "#58a6ff",
        borderWidth: 2, pointRadius: 0, fill: false },
      { label: "zero", data: rc.dates.map(() => 0), borderColor: "#8b949e",
        borderWidth: 1, borderDash: [4, 4], pointRadius: 0, fill: false },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#8b949e", maxTicksLimit: 8 }, grid: { color: "#283040" } },
        y: { min: -1, max: 1, ticks: { color: "#8b949e" }, grid: { color: "#283040" } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderAttribution(d) {
  const a = d.attribution;
  if (!a || !a.length) return;
  const sorted = [...a].sort((x, y) => y.total_contribution - x.total_contribution);
  new Chart(document.getElementById("attributionChart"), {
    type: "bar",
    data: { labels: sorted.map(x => x.symbol), datasets: [{
      data: sorted.map(x => +(x.total_contribution * 100).toFixed(2)),
      backgroundColor: sorted.map(x => x.total_contribution >= 0 ? "#3fb950" : "#f85149"),
    }]},
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#8b949e", callback: v => v + "%" }, grid: { color: "#283040" } },
        y: { ticks: { color: "#e6edf3" }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderPaper(d) {
  const p = d.paper, el = document.getElementById("paperBody");
  if (!p || !p.n_days) { el.innerHTML = `<p class="note">No paper-trading data recorded yet.</p>`; return; }
  if (p.n_days < 2 || !p.curve) {
    el.innerHTML = `<p class="note">Accruing — ${p.n_days} day(s) recorded. P&L marking begins at 2 trading days.</p>`;
    return;
  }
  el.innerHTML = `<div class="paper-grid">
      ${card("Days live", p.n_days)}
      ${card("Cumulative", FMT.pct(p.cum_return), p.cum_return >= 0 ? "pos" : "neg")}
      ${card("Sharpe (ann.)", FMT.num(p.sharpe), p.sharpe >= 0 ? "pos" : "neg")}
      ${card("Max drawdown", FMT.pct(p.max_drawdown), "neg")}
    </div><div class="chart-wrap small"><canvas id="paperChart"></canvas></div>`;
  new Chart(document.getElementById("paperChart"), {
    type: "line",
    data: { labels: p.curve.dates, datasets: [{
      label: "Paper equity", data: p.curve.values, borderColor: "#3fb950", borderWidth: 2, pointRadius: 2,
    }]},
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { x: { ticks: { color: "#8b949e" }, grid: { color: "#283040" } },
                y: { ticks: { color: "#8b949e" }, grid: { color: "#283040" } } },
      plugins: { legend: { display: false } },
    },
  });
}

fetch("./data.json").then(r => r.json()).then(d => {
  DATA = d;
  document.getElementById("meta").textContent =
    `Window ${d.window} · ${d.n_assets} assets · generated ${d.generated}`;
  document.getElementById("assets").textContent = "Universe: " + (d.assets || []).join(", ");
  renderCards(d); renderEquity(d); renderAnnual(d); renderBlend(d); renderWeights(d);
  renderRollingCorr(d); renderAttribution(d); renderPaper(d);
}).catch(() => {
  document.getElementById("meta").textContent =
    "Dashboard data is generated by the daily backtest pipeline and will appear here once produced.";
});

document.getElementById("logToggle").addEventListener("click", () => {
  logScale = !logScale;
  equityChart.options.scales.y.type = logScale ? "logarithmic" : "linear";
  equityChart.update();
});
