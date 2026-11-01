"use strict";

const app = document.getElementById("app");
const meta = document.getElementById("meta");
const tip = document.getElementById("tip");
const LIVE = new Set(["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"]);
const FINISHED = new Set(["FT", "AET", "PEN"]);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt1 = (v) => (v == null ? "–" : (Math.round(v * 10) / 10).toLocaleString("pl-PL"));
const timeOf = (iso) => new Date(iso).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
const shortDate = (iso) => new Date(iso).toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit", year: "2-digit" });
// Skrót do osi wykresu: "Manchester City" -> "MCI", "Arsenal" -> "ARS".
const abbr = (name) => {
  const words = name.replace(/\b(FC|AFC|CF|SC|SSC|SS|US|RC|VfB|VfL|TSG|1\.)\b/g, " ")
    .split(/[\s\-.]+/).map((w) => w.replace(/[^\p{L}]/gu, "")).filter((w) => w.length > 1);
  if (!words.length) return name.slice(0, 3).toUpperCase();
  const s = words.length === 1 ? words[0].slice(0, 3) : words[0][0] + words[1].slice(0, 2);
  return s.toUpperCase();
};
const avg = (vals) => {
  const xs = vals.filter((v) => v != null);
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
};

async function load() {
  let data;
  try {
    const res = await fetch("data/matches.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
  } catch (e) {
    meta.textContent = "";
    app.innerHTML = `<p class="notice warn">Nie udało się wczytać danych (${esc(e.message)}). Spróbuj odświeżyć stronę.</p>`;
    return;
  }
  render(data);
}

function render(data) {
  const day = new Date(data.date + "T12:00:00");
  const dayTxt = day.toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" });
  const gen = new Date(data.generated_at).toLocaleString("pl-PL", { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
  meta.textContent = `${dayTxt} · aktualizacja ${gen}`;

  let html = "";
  const today = new Date().toLocaleDateString("sv-SE");
  if (data.date !== today) {
    html += `<p class="notice">Zestawienie z dnia ${esc(day.toLocaleDateString("pl-PL"))}. Dane na dziś pojawią się po porannej aktualizacji.</p>`;
  }
  for (const n of data.notes || []) html += `<p class="notice warn">${esc(n)}</p>`;
  if (!data.leagues.length) {
    html += `<p class="notice">Brak meczów w wybranych ligach w tym dniu.</p>`;
  }
  for (const lg of data.leagues) {
    html += `<section class="league"><div class="league-head">
      ${lg.logo ? `<img src="${esc(lg.logo)}" alt="" loading="lazy">` : ""}
      <span class="country">${esc(lg.country)}:</span> ${esc(lg.name)}</div>`;
    for (const m of lg.matches) html += matchRow(m);
    html += `</section>`;
  }
  app.innerHTML = html;

  const byId = new Map(data.leagues.flatMap((lg) => lg.matches.map((m) => [String(m.id), m])));
  const lgById = new Map(data.leagues.flatMap((lg) => lg.matches.map((m) => [String(m.id), lg])));
  app.querySelectorAll(".match-row").forEach((btn) => {
    btn.addEventListener("click", () => {
      const box = btn.parentElement;
      const det = box.querySelector(".details");
      const open = !box.classList.contains("open");
      box.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open);
      if (open && !det.dataset.ready) {
        det.innerHTML = details(byId.get(box.dataset.id), data, lgById.get(box.dataset.id));
        det.dataset.ready = "1";
        det.querySelector(".collapse").addEventListener("click", () => {
          btn.click();
          if (btn.getBoundingClientRect().top < 72) btn.scrollIntoView({ block: "start" });
        });
      }
      det.hidden = !open;
    });
  });
}

function matchRow(m) {
  let time = timeOf(m.kickoff), cls = "time";
  if (LIVE.has(m.status)) { time = "LIVE"; cls += " live"; }
  else if (FINISHED.has(m.status)) time = "Koniec";
  else if (m.status === "PST") time = "Przeł.";
  else if (m.status === "CANC") time = "Odw.";
  const showScore = m.goals && m.goals[0] != null;
  const team = (t, i, side) => `<span class="team">
      ${t.logo ? `<img src="${esc(t.logo)}" alt="" loading="lazy">` : `<span class="dot" style="background:var(--${side})"></span>`}
      <span class="nm">${esc(t.name)}</span>${showScore ? `<span class="sc">${m.goals[i]}</span>` : ""}</span>`;
  return `<div class="match" data-id="${m.id}">
    <button class="match-row" type="button" aria-expanded="false">
      <span class="${cls}">${time}</span>
      <span class="teams">${team(m.home, 0, "home")}${team(m.away, 1, "away")}</span>
      <svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="details" hidden></div>
  </div>`;
}

function details(m, data, lg) {
  let html = `<div class="legend">
    <span><i style="background:var(--home)"></i>${esc(m.home.name)}</span>
    <span><i style="background:var(--away)"></i>${esc(m.away.name)}</span></div>`;
  for (const st of data.stats) {
    const k = st.key;
    const rh = [...m.recent.home].reverse();  // od najstarszego do najnowszego
    const ra = [...m.recent.away].reverse();
    const h2h = [...m.h2h].reverse();
    const vals = [...rh, ...ra].map((x) => x.stats[k]).concat(h2h.flatMap((x) => [x.stats[k].home, x.stats[k].away]));
    const yMax = Math.max(4, ...vals.filter((v) => v != null));

    const ah = avg(rh.map((x) => x.stats[k])), aa = avg(ra.map((x) => x.stats[k]));
    html += `<details class="stat-block"><summary>
      <span class="st-name">${esc(st.label)}</span>
      <span class="st-avg"><b style="color:var(--text)">${fmt1(ah)}</b><i style="background:var(--home)"></i>
        <span>śr.</span><i style="background:var(--away)"></i><b style="color:var(--text)">${fmt1(aa)}</b></span>
      <svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </summary><div class="st-body">`;
    html += `<div class="section"><h4>Ostatnie ${data.recent_matches} meczów ligowych</h4>`;
    html += compare(ah, aa, "średnio na mecz");
    html += barChart(m.home.name, "home", rh.map((x) => recentPoint(x, k)), yMax);
    html += barChart(m.away.name, "away", ra.map((x) => recentPoint(x, k)), yMax);
    html += `</div>`;

    html += `<div class="section"><h4>H2H · ostatnie ${data.h2h_years} lata (liga)</h4>`;
    if (!h2h.length) {
      html += `<div class="empty">Brak spotkań ligowych tych drużyn w ostatnich ${data.h2h_years} latach.</div>`;
    } else {
      html += compare(avg(h2h.map((x) => x.stats[k].home)), avg(h2h.map((x) => x.stats[k].away)), `średnio w ${h2h.length} H2H`);
      html += groupedChart(m, h2h, k, yMax);
    }
    html += `</div></div></details>`;
  }
  html += leagueTable(m, lg);
  html += `<button class="collapse" type="button">Zwiń statystyki
    <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 12.5l5-5 5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`;
  return html;
}

// Tabela ligowa z wyróżnieniem obu drużyn z meczu.
function leagueTable(m, lg) {
  const rows = (lg && lg.table) || [];
  if (!rows.length) return "";
  const sideOf = (r) => String(r.team.id) === String(m.home.id) ? "home"
    : String(r.team.id) === String(m.away.id) ? "away" : "";
  const formCell = (f) => `<span class="form">${f.map((x) =>
    `<b class="f-${x}" title="${{ W: "wygrana", D: "remis", L: "porażka" }[x]}">${{ W: "Z", D: "R", L: "P" }[x]}</b>`).join("")}</span>`;
  const body = rows.map((r) => {
    const side = sideOf(r);
    const gd = r.gd > 0 ? `+${r.gd}` : r.gd;
    return `<tr class="${side ? "hl hl-" + side : ""}">
      <td class="n rk">${r.rank}</td>
      <td class="tm">${esc(r.team.name)}</td>
      <td class="n">${r.p}</td><td class="n">${r.w}</td><td class="n">${r.d}</td><td class="n">${r.l}</td>
      <td class="n gl">${r.gf}:${r.ga}<small>${gd}</small></td>
      <td class="n pts">${r.pts}</td>
      <td>${formCell(r.form)}</td></tr>`;
  }).join("");
  const pos = (id) => rows.find((r) => String(r.team.id) === String(id));
  const ph = pos(m.home.id), pa = pos(m.away.id);
  const sum = ph && pa ? `<span class="st-avg">${ph.rank}. <i style="background:var(--home)"></i>
      <span>vs</span><i style="background:var(--away)"></i> ${pa.rank}.</span>` : "";
  return `<details class="stat-block mtable ltable"><summary><span class="st-name">Tabela ligowa</span>${sum}
      <svg class="chev" viewBox="0 0 20 20" aria-hidden="true" style="${sum ? "" : "margin-left:auto"}"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </summary><div class="st-body tbl-wrap"><table>
      <thead><tr><th class="n">#</th><th>Drużyna</th><th class="n" title="mecze">M</th><th class="n" title="zwycięstwa">Z</th>
        <th class="n" title="remisy">R</th><th class="n" title="porażki">P</th><th class="n">Bramki</th><th class="n">Pkt</th><th>Forma</th></tr></thead>
      <tbody>${body}</tbody></table>
    <p class="tbl-note">M – mecze, Z – zwycięstwa, R – remisy, P – porażki. Forma: 5 ostatnich meczów ligowych, najnowszy z prawej.
      Przy równej liczbie punktów kolejność może różnić się od oficjalnej.</p></div></details>`;
}

function recentPoint(x, k) {
  return {
    v: x.stats[k], top: abbr(x.opponent), bottom: x.venue,
    tip: `${shortDate(x.date)} · ${x.venue === "D" ? "dom" : "wyjazd"}<br>vs ${esc(x.opponent)} (${esc(x.score)})`,
  };
}

function compare(a, b, label) {
  const tot = (a || 0) + (b || 0);
  const pa = tot ? (a || 0) / tot * 100 : 0, pb = tot ? (b || 0) / tot * 100 : 0;
  const ca = a != null && b != null && a !== b ? (a > b ? "lead" : "trail") : "";
  const cb = a != null && b != null && a !== b ? (b > a ? "lead" : "trail") : "";
  return `<div class="cmp">
    <span class="v ${ca}">${fmt1(a)}</span><span class="lbl">${esc(label)}</span><span class="v a ${cb}">${fmt1(b)}</span>
    <div class="bars"><div class="bar h"><b style="width:${pa}%"></b></div><div class="bar w"><b style="width:${pb}%"></b></div></div>
  </div>`;
}

// ---------------------------------------------------------------- wykresy SVG
const W = 340, PAD_L = 4, PAD_R = 4, TOP = 14;

function barPath(x, y, w, h, r = 4) {
  if (h <= 0) return "";
  r = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function barChart(title, side, pts, yMax) {
  if (!pts.length) return `<div class="chart"><div class="ttl"><i style="background:var(--${side})"></i>${esc(title)}</div><div class="empty">Brak danych.</div></div>`;
  const H = 70, base = TOP + H, slots = Math.max(pts.length, 5);
  const sw = (W - PAD_L - PAD_R) / slots, bw = Math.min(16, sw * 0.55);
  const y = (v) => base - (v / yMax) * H;
  let s = `<line class="grid" x1="0" x2="${W}" y1="${base}" y2="${base}"/>`;
  const a = avg(pts.map((p) => p.v));
  pts.forEach((p, i) => {
    const cx = PAD_L + sw * i + sw / 2, x = cx - bw / 2;
    const hitTip = `<b>${p.v == null ? "brak danych" : p.v}</b> · ${p.tip}`;
    s += `<rect class="hit" x="${cx - sw / 2}" y="0" width="${sw}" height="${base + 26}" data-tip="${esc(hitTip)}" tabindex="0"/>`;
    if (p.v == null) {
      s += `<rect x="${x}" y="${base - 3}" width="${bw}" height="3" rx="1" fill="var(--missing)"/>`;
      s += `<text x="${cx}" y="${base - 6}" text-anchor="middle">b/d</text>`;
    } else {
      s += `<path d="${barPath(x, y(p.v), bw, base - y(p.v))}" fill="var(--${side})"/>`;
      s += `<text class="val" x="${cx}" y="${y(p.v) - 3}" text-anchor="middle">${p.v}</text>`;
    }
    s += `<text x="${cx}" y="${base + 11}" text-anchor="middle">${esc(p.top)}</text>`;
    s += `<text x="${cx}" y="${base + 21}" text-anchor="middle">${esc(p.bottom)}</text>`;
  });
  if (a != null) {
    s += `<line class="avg" x1="0" x2="${W}" y1="${y(a)}" y2="${y(a)}"/>`;
  }
  return `<div class="chart"><div class="ttl"><i style="background:var(--${side})"></i>${esc(title)}
    <span style="margin-left:auto;color:var(--muted)">- - średnia ${fmt1(a)}</span></div>
    <svg viewBox="0 0 ${W} ${base + 24}" role="img" aria-label="${esc(title)}: wartości z ostatnich meczów">${s}</svg></div>`;
}

function groupedChart(m, h2h, k, yMax) {
  const H = 70, base = TOP + H, slots = Math.max(h2h.length, 4);
  const sw = (W - PAD_L - PAD_R) / slots, bw = Math.min(16, sw * 0.28), gap = 2;
  const y = (v) => base - (v / yMax) * H;
  let s = `<line class="grid" x1="0" x2="${W}" y1="${base}" y2="${base}"/>`;
  h2h.forEach((g, i) => {
    const cx = PAD_L + sw * i + sw / 2;
    const vals = [["home", g.stats[k].home, cx - gap / 2 - bw], ["away", g.stats[k].away, cx + gap / 2]];
    const t = `${shortDate(g.date)} · ${esc(g.label)} ${esc(g.score)}<br>` +
      `${esc(m.home.name)}: <b>${g.stats[k].home ?? "b/d"}</b><br>${esc(m.away.name)}: <b>${g.stats[k].away ?? "b/d"}</b>`;
    s += `<rect class="hit" x="${cx - sw / 2}" y="0" width="${sw}" height="${base + 26}" data-tip="${esc(t)}" tabindex="0"/>`;
    for (const [side, v, x] of vals) {
      if (v == null) {
        s += `<rect x="${x}" y="${base - 3}" width="${bw}" height="3" rx="1" fill="var(--missing)"/>`;
        continue;
      }
      s += `<path d="${barPath(x, y(v), bw, base - y(v))}" fill="var(--${side})"/>`;
      s += `<text class="val" x="${x + bw / 2}" y="${y(v) - 3}" text-anchor="middle">${v}</text>`;
    }
    s += `<text x="${cx}" y="${base + 11}" text-anchor="middle">${shortDate(g.date)}</text>`;
    s += `<text x="${cx}" y="${base + 21}" text-anchor="middle">${g.host === "home" ? abbr(m.home.name) : abbr(m.away.name)} dom · ${esc(g.score)}</text>`;
  });
  return `<div class="chart"><svg viewBox="0 0 ${W} ${base + 24}" role="img" aria-label="Porównanie w meczach H2H">${s}</svg></div>`;
}


// ---------------------------------------------------------------- dymki
let tipFor = null;
function showTip(el, x, y) {
  tip.innerHTML = el.dataset.tip;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let left = Math.min(Math.max(8, x - r.width / 2), innerWidth - r.width - 8);
  let top = y - r.height - 12;
  if (top < 8) top = y + 16;
  tip.style.left = left + "px";
  tip.style.top = top + "px";
  tipFor = el;
}
function hideTip() { tip.hidden = true; tipFor = null; }
document.addEventListener("pointerover", (e) => {
  const el = e.target.closest?.(".hit");
  if (el && e.pointerType === "mouse") showTip(el, e.clientX, e.clientY);
});
document.addEventListener("pointerout", (e) => {
  if (e.pointerType === "mouse" && e.target.closest?.(".hit")) hideTip();
});
document.addEventListener("click", (e) => {
  const el = e.target.closest?.(".hit");
  if (el && el !== tipFor) showTip(el, e.clientX, e.clientY);
  else hideTip();
});
document.addEventListener("focusin", (e) => {
  const el = e.target.closest?.(".hit");
  if (el) { const r = el.getBoundingClientRect(); showTip(el, r.left + r.width / 2, r.top + 20); }
});
addEventListener("scroll", hideTip, { passive: true });

load();
