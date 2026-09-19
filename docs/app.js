/* 讀 data.json，畫門檻軌道。無框架、無建置步驟。 */

const STATUS_TEXT = {
  ok: "正常",
  watch: "接近",
  triggered: "觸發",
  stale: "資料過期",
  unknown: "無資料",
};

const fmtNum = (v, unit) => {
  if (v === null || v === undefined) return "—";
  const abs = Math.abs(v);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 0 : abs >= 10 ? 1 : 2;
  const n = v.toFixed(digits);
  return unit ? `${n} ${unit}` : n;
};

const fmtDelta = (v, unit) => {
  if (v === null || v === undefined || v === 0) return "";
  const sign = v > 0 ? "+" : "−";
  const abs = Math.abs(v);
  return `${sign}${abs >= 10 ? abs.toFixed(0) : abs.toFixed(1)}${unit === "bp" ? "bp" : ""}`;
};

/* 把值換算成軌道上的百分比位置 */
const posOf = (v, scale) => {
  if (v === null || v === undefined || !scale) return null;
  const [lo, hi] = scale;
  if (hi === lo) return null;
  return Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));
};

function trackHTML(ind) {
  if (ind.type === "boolean") {
    const on = ind.value === 1;
    return `<div class="flag">${on ? "是 — 已發生" : "否"}</div>`;
  }
  if (!ind.scale || ind.value === null) return "";

  const [lo, hi] = ind.scale;
  const p = posOf(ind.value, ind.scale);
  const pw = posOf(ind.watch, ind.scale);
  const pt = posOf(ind.trigger, ind.scale);
  const worseHigh = ind.direction !== "lower_is_worse";

  // 填色從「安全端」延伸到當前值
  const fill = worseHigh
    ? `left:0;width:${p}%`
    : `left:${p}%;width:${100 - p}%`;

  const ticks = [
    pw !== null ? `<div class="tick" style="left:${pw}%"><span>觀察 ${fmtNum(ind.watch, "")}</span></div>` : "",
    pt !== null ? `<div class="tick" style="left:${pt}%"><span>觸發 ${fmtNum(ind.trigger, "")}</span></div>` : "",
  ].join("");

  return `
    <div class="track">
      <div class="rail"></div>
      <div class="fill" style="${fill}"></div>
      ${ticks}
      <div class="marker" style="left:${p}%"></div>
    </div>
    <div class="ends"><span>${fmtNum(lo, "")}</span><span>${fmtNum(hi, "")}</span></div>`;
}

function rowHTML(ind) {
  const delta = fmtDelta(ind.change_1w, ind.unit);
  const deltaHTML = delta ? `<span class="delta">一週 ${delta}</span>` : "";
  const noteHTML = ind.note
    ? `<details><summary>說明</summary><p class="note">${ind.note}</p>
       <p class="meta">資料日期 ${ind.as_of || "—"} ・ 檢視頻率 ${ind.cadence || "—"} ・ 來源 ${ind.source}${ind.stale ? " ・ 已過期" : ""}</p></details>`
    : `<p class="meta">資料日期 ${ind.as_of || "—"}${ind.stale ? " ・ 已過期" : ""}</p>`;

  return `
    <div class="row s-${ind.status}">
      <div class="head">
        <span class="dot" role="img" aria-label="${STATUS_TEXT[ind.status] || ind.status}"></span>
        <span class="label">${ind.name}</span>
        <span class="spacer"></span>
        ${deltaHTML}
        <span class="val">${fmtNum(ind.value, ind.unit)}</span>
      </div>
      ${trackHTML(ind)}
      ${noteHTML}
    </div>`;
}

function render(doc) {
  const s = doc.summary || {};
  const parts = [];
  if (s.triggered) parts.push(`<span class="is-trig"><span class="n">${s.triggered}</span> 項觸發</span>`);
  if (s.watch) parts.push(`<span class="is-watch"><span class="n">${s.watch}</span> 項接近</span>`);
  parts.push(`<span class="n">${s.ok || 0}</span> 項正常`);
  if (s.stale) parts.push(`<span class="is-stale"><span class="n">${s.stale}</span> 項資料過期</span>`);
  if (s.unknown) parts.push(`<span class="is-stale"><span class="n">${s.unknown}</span> 項無資料</span>`);

  document.getElementById("tally").innerHTML =
    parts.join('<span class="sep">・</span>');

  const gen = doc.generated_at ? new Date(doc.generated_at) : null;
  document.getElementById("stamp").textContent = gen
    ? `更新於 ${gen.toLocaleString("zh-TW", { hour12: false })}`
    : "";

  document.getElementById("groups").innerHTML = (doc.groups || [])
    .map((g) => `
      <section class="group">
        <h2>${g.name}</h2>
        ${g.blurb ? `<p class="blurb">${g.blurb}</p>` : ""}
        ${g.indicators.map(rowHTML).join("")}
      </section>`)
    .join("");
}

fetch("data.json", { cache: "no-store" })
  .then((r) => {
    if (!r.ok) throw new Error(`data.json 回應 ${r.status}`);
    return r.json();
  })
  .then(render)
  .catch((err) => {
    document.getElementById("tally").textContent = "讀不到資料";
    document.getElementById("groups").innerHTML = `
      <p class="loading">讀不到 data.json（${err.message}）。<br>
      先在 GitHub 的 Actions 分頁手動執行一次 <code>update</code>，它會產生這個檔案。</p>`;
  });
