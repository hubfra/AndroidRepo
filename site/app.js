"use strict";

const app = document.getElementById("app");
const meta = document.getElementById("meta");
const tip = document.getElementById("tip");
const LIVE = new Set(["1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"]);
const FINISHED = new Set(["FT", "AET", "PEN"]);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt1 = (v) => (v == null ? "–" : (Math.round(v * 10) / 10).toLocaleString("pl-PL"));
const fmtAvg = (v) => (v == null ? "–" : v.toLocaleString("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
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

const AGAINST = { corners: "rożne oddane rywalom", offsides: "spalone rywali", fouls: "faule rywali" };
const AGAINST_HINT = {
  corners: "Ile rzutów rożnych wywalczyli rywale tej drużyny – czyli ile rożnych drużyna oddaje.",
  offsides: "Ile spalonych mieli rywale tej drużyny – im więcej, tym skuteczniej drużyna łapie na spalonym.",
  fouls: "Ile fauli popełnili rywale tej drużyny – czyli ile fauli drużyna wymusza.",
};

const seg = (name, opts) => `<div class="seg" role="group" data-seg="${name}">${opts.map(([v, l], i) =>
  `<button type="button" data-v="${v}" class="${i === 0 ? "on" : ""}" aria-pressed="${i === 0}">${l}</button>`).join("")}</div>`;

// Przełączniki widoku (Wszystkie / Dom-wyjazd, Za / Przeciw).
document.addEventListener("click", (e) => {
  const btn = e.target.closest?.(".seg button");
  if (!btn) return;
  const group = btn.parentElement, box = btn.closest(".rsec, .sttable");
  group.querySelectorAll("button").forEach((b) => { b.classList.toggle("on", b === btn); b.setAttribute("aria-pressed", b === btn); });
  box.dataset[group.dataset.seg] = btn.dataset.v;
  if (box.classList.contains("rsec")) {
    box.querySelectorAll(".rv").forEach((v) => {
      v.hidden = !(v.dataset.venue === box.dataset.venue && v.dataset.dir === box.dataset.dir);
    });
  } else {
    applySeasonDir(box);
  }
});

function oddsBlock(m) {
  const o = m.odds;
  if (!o) return "";
  const raw = [o.home, o.draw, o.away].map((x) => (x ? 1 / x : 0));
  const sum = raw.reduce((a, b) => a + b, 0) || 1;
  const fav = Math.min(...[o.home, o.away].filter(Boolean));
  const cell = (lbl, v, open, i, side) => {
    if (!v) return `<div class="oc"><span class="ol">${lbl}</span><b>–</b></div>`;
    let mv = "";
    if (open && Math.abs(open - v) >= 0.01) {
      mv = v < open ? `<span class="mv dn" title="kurs spadł z ${open.toFixed(2)}">▼ ${open.toFixed(2)}</span>`
        : `<span class="mv up" title="kurs wzrósł z ${open.toFixed(2)}">▲ ${open.toFixed(2)}</span>`;
    }
    const sw = side ? `<i style="background:var(--${side})"></i>` : "";
    return `<div class="oc${v === fav ? " fav" : ""}"><span class="ol">${sw}${lbl}</span><b>${v.toFixed(2)}</b>
      <span class="op">${Math.round((raw[i] / sum) * 100)}%</span>${mv}</div>`;
  };
  const t = o.total || {};
  const tot = t.line != null && (t.over || t.under)
    ? `<p class="ototal">Gole ${t.line}: powyżej <b>${t.over ? t.over.toFixed(2) : "–"}</b> · poniżej <b>${t.under ? t.under.toFixed(2) : "–"}</b></p>` : "";
  return `<div class="odds"><div class="ohead">Kursy${o.provider ? ` (${esc(o.provider)})` : ""}</div>
    <div class="ogrid">${cell("1", o.home, (o.open || {}).home, 0, "home")}${cell("X", o.draw, (o.open || {}).draw, 1)}${cell("2", o.away, (o.open || {}).away, 2, "away")}</div>
    ${tot}<p class="tbl-note">% – szansa wg kursów (bez marży). ▼/▲ – kurs otwarcia: spadek oznacza, że rynek mocniej stawia na tę drużynę.</p></div>`;
}

function details(m, data, lg) {
  let html = `<div class="legend">
    <span><i style="background:var(--home)"></i>${esc(m.home.name)}</span>
    <span><i style="background:var(--away)"></i>${esc(m.away.name)}</span></div>`;
  html += oddsBlock(m);
  for (const st of data.stats) {
    const k = st.key;
    const rh = [...m.recent.home].reverse();  // od najstarszego do najnowszego
    const ra = [...m.recent.away].reverse();
    const vh = [...((m.recent_venue || {}).home || [])].reverse();
    const va = [...((m.recent_venue || {}).away || [])].reverse();
    const h2h = [...m.h2h].reverse();
    const pick = (x, dir) => (dir === "against" ? (x.against || {})[k] : x.stats[k]);
    const vals = [...rh, ...ra, ...vh, ...va].flatMap((x) => [x.stats[k], (x.against || {})[k]])
      .concat(h2h.flatMap((x) => [x.stats[k].home, x.stats[k].away]));
    const yMax = Math.max(4, ...vals.filter((v) => v != null));
    const hasAgainst = rh.some((x) => x.against && x.against[k] != null);
    const hasVenue = vh.length || va.length;

    const ah = avg(rh.map((x) => x.stats[k])), aa = avg(ra.map((x) => x.stats[k]));
    html += `<details class="stat-block"><summary>
      <span class="st-name">${esc(st.label)}</span>
      <span class="st-avg"><b style="color:var(--text)">${fmt1(ah)}</b><i style="background:var(--home)"></i>
        <span>śr.</span><i style="background:var(--away)"></i><b style="color:var(--text)">${fmt1(aa)}</b></span>
      <svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </summary><div class="st-body">`;
    html += `<div class="section rsec" data-venue="all" data-dir="for"><h4>Ostatnie ${data.recent_matches} meczów ligowych</h4>`;
    html += `<div class="segs">`;
    if (hasVenue) html += seg("venue", [["all", "Wszystkie"], ["venue", "Dom / wyjazd"]]);
    if (hasAgainst) html += seg("dir", [["for", "Za"], ["against", "Przeciw"]]);
    html += `</div>`;
    for (const venue of hasVenue ? ["all", "venue"] : ["all"]) {
      const [lh, la] = venue === "all" ? [rh, ra] : [vh, va];
      for (const dir of hasAgainst ? ["for", "against"] : ["for"]) {
        const lbl = dir === "for" ? "średnio na mecz" : AGAINST[k] || "średnio rywale";
        const sfx = venue === "venue" ? [" · u siebie", " · na wyjeździe"] : ["", ""];
        const dirNote = dir === "against" ? " – rywale" : "";
        html += `<div class="rv" data-venue="${venue}" data-dir="${dir}"${venue === "all" && dir === "for" ? "" : " hidden"}>`;
        if (dir === "against") html += `<p class="hint">${esc(AGAINST_HINT[k] || "Wartości rywali w tych meczach.")}</p>`;
        html += compare(avg(lh.map((x) => pick(x, dir))), avg(la.map((x) => pick(x, dir))), lbl);
        html += barChart(m.home.name + sfx[0] + dirNote, "home", lh.map((x) => recentPoint(x, k, dir)), yMax);
        html += barChart(m.away.name + sfx[1] + dirNote, "away", la.map((x) => recentPoint(x, k, dir)), yMax);
        html += `</div>`;
      }
    }
    html += `</div>`;

    html += `<div class="section"><h4>H2H · ostatnie ${data.h2h_years} lata (${data.h2h_scope === "all" ? "wszystkie rozgrywki" : "liga"})</h4>`;
    if (!h2h.length) {
      html += `<div class="empty">Brak spotkań tych drużyn w ostatnich ${data.h2h_years} latach.</div>`;
    } else {
      html += compare(avg(h2h.map((x) => x.stats[k].home)), avg(h2h.map((x) => x.stats[k].away)), `średnio w ${h2h.length} H2H`);
      html += groupedChart(m, h2h, k, yMax);
    }
    html += seasonTable(m, lg, st);
    html += `</div></div></details>`;
  }
  html += leagueTable(m, lg);
  html += `<button class="collapse" type="button">Zwiń statystyki
    <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 12.5l5-5 5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`;
  return html;
}

// Średnie danej statystyki wszystkich drużyn ligi: cały sezon i ostatnie 5 meczów (sortowalne),
// „za” (drużyna) albo „przeciw” (rywale drużyny).
function seasonTable(m, lg, st) {
  const rows = ((lg && lg.team_stats) || []).filter((r) => r.season[st.key] != null);
  if (!rows.length) return "";
  const k = st.key;
  const hasA = rows.some((r) => r.season_against && r.season_against[k] != null);
  const sideOf = (r) => String(r.team.id) === String(m.home.id) ? "home"
    : String(r.team.id) === String(m.away.id) ? "away" : "";
  const sorted = rows.slice().sort((a, b) => (b.season[k] ?? -1) - (a.season[k] ?? -1));
  const dv = (v) => (v ?? "");
  const body = sorted.map((r, i) => {
    const side = sideOf(r);
    return `<tr class="${side ? "hl hl-" + side : ""}" data-name="${esc(r.team.name)}"
        data-season-for="${dv(r.season[k])}" data-last-for="${dv(r.last[k])}"
        data-season-against="${dv((r.season_against || {})[k])}" data-last-against="${dv((r.last_against || {})[k])}"
        data-season="${dv(r.season[k])}" data-last="${dv(r.last[k])}">
      <td class="n rk">${i + 1}</td><td class="tm">${esc(r.team.name)}</td>
      <td class="n muted">${r.n}</td>
      <td class="n v vs">${fmtAvg(r.season[k])}</td><td class="n v vl">${fmtAvg(r.last[k])}</td></tr>`;
  }).join("");
  const th = (key, label, cls = "n") =>
    `<th class="${cls}"><button type="button" class="sort${key === "season" ? " on desc" : ""}" data-sort="${key}">${label}<span class="arr"></span></button></th>`;
  return `<details class="sub mtable ltable sttable" data-dir="for"><summary>Średnie wszystkich drużyn ligi
      <svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 7.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></summary>
    <div class="tbl-wrap">${hasA ? `<div class="segs">${seg("dir", [["for", "Za"], ["against", "Przeciw"]])}</div>` : ""}<table>
      <thead><tr><th class="n">#</th>${th("name", "Drużyna", "")}<th class="n" title="mecze z danymi">M</th>
        ${th("season", "Sezon")}${th("last", "Ost. 5")}</tr></thead>
      <tbody>${body}</tbody></table>
    <p class="tbl-note"><span class="dir-for">Średnio na mecz – wartości drużyny.</span><span class="dir-against" hidden>Przeciw – ${esc(AGAINST[k] || "wartości rywali")} (średnio na mecz).</span>
      „Ost. 5” – 5 ostatnich meczów ligowych. Dotknij nagłówka, by sortować.</p></div></details>`;
}

function applySeasonDir(box) {
  const dir = box.dataset.dir;
  box.querySelectorAll("tbody tr").forEach((r) => {
    r.dataset.season = r.dataset[dir === "for" ? "seasonFor" : "seasonAgainst"];
    r.dataset.last = r.dataset[dir === "for" ? "lastFor" : "lastAgainst"];
    r.querySelector(".vs").textContent = r.dataset.season === "" ? "–" : fmtAvg(+r.dataset.season);
    r.querySelector(".vl").textContent = r.dataset.last === "" ? "–" : fmtAvg(+r.dataset.last);
  });
  box.querySelector(".dir-for").hidden = dir !== "for";
  box.querySelector(".dir-against").hidden = dir === "for";
  const active = box.querySelector("button.sort.on") || box.querySelector('button.sort[data-sort="season"]');
  sortTable(active, active.classList.contains("asc") ? "asc" : "desc");
}

// Sortowanie tabel średnich.
function sortTable(btn, forceDir) {
  const table = btn.closest("table");
  const key = btn.dataset.sort;
  let desc;
  if (forceDir) desc = forceDir === "desc";
  else {
    const wasDesc = btn.classList.contains("on") && btn.classList.contains("desc");
    desc = btn.classList.contains("on") ? !wasDesc : key !== "name";
  }
  table.querySelectorAll("button.sort").forEach((b) => b.classList.remove("on", "desc", "asc"));
  btn.classList.add("on", desc ? "desc" : "asc");
  const tbody = table.tBodies[0];
  const rows = [...tbody.rows];
  rows.sort((a, b) => {
    if (key === "name") return a.dataset.name.localeCompare(b.dataset.name, "pl") * (desc ? -1 : 1);
    const va = a.dataset[key] === "" ? -Infinity : +a.dataset[key];
    const vb = b.dataset[key] === "" ? -Infinity : +b.dataset[key];
    return (desc ? vb - va : va - vb);
  });
  rows.forEach((r, i) => { r.cells[0].textContent = i + 1; tbody.appendChild(r); });
}
document.addEventListener("click", (e) => {
  const btn = e.target.closest?.(".sttable button.sort");
  if (btn) sortTable(btn);
});

const ZONE_PL = {
  "Champions League": "Liga Mistrzów", "Europa League": "Liga Europy",
  "Conference League": "Liga Konferencji", "Europa Conference League": "Liga Konferencji",
  "Relegation": "Spadek", "Relegation Playoff": "Baraż o utrzymanie", "Relegation playoff": "Baraż o utrzymanie",
  "Champions League qualifying": "El. Ligi Mistrzów", "Conference League qualifying": "El. Ligi Konferencji",
};

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
      <td class="n rk">${r.zone && r.zone.color ? `<span class="zn" style="background:${esc(r.zone.color)}"></span>` : ""}${r.rank}</td>
      <td class="tm">${esc(r.team.name)}</td>
      <td class="n">${r.p}</td><td class="n">${r.w}</td><td class="n">${r.d}</td><td class="n">${r.l}</td>
      <td class="n gl">${r.gf}:${r.ga}<small>${gd}</small></td>
      <td class="n pts">${r.pts}</td>
      <td>${formCell(r.form)}</td></tr>`;
  }).join("");
  const zmap = new Map();
  rows.forEach((r) => { if (r.zone && r.zone.color && r.zone.label) zmap.set(r.zone.label, r.zone.color); });
  const zones = zmap.size ? `<div class="zones">${[...zmap].map(([l, c]) =>
    `<span><i style="background:${esc(c)}"></i>${esc(ZONE_PL[l] || l)}</span>`).join("")}</div>` : "";
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
    ${zones}<p class="tbl-note">M – mecze, Z – zwycięstwa, R – remisy, P – porażki. Forma: 5 ostatnich meczów ligowych, najnowszy z prawej.
      ${rows.some((r) => r.zone !== undefined) ? "Tabela oficjalna (ESPN)." : "Przy równej liczbie punktów kolejność może różnić się od oficjalnej."}</p></div></details>`;
}

function recentPoint(x, k, dir = "for") {
  const own = x.stats[k], opp = (x.against || {})[k];
  return {
    v: dir === "against" ? opp : own, top: abbr(x.opponent), bottom: x.venue,
    tip: `${shortDate(x.date)} · ${x.venue === "D" ? "dom" : "wyjazd"}<br>vs ${esc(x.opponent)} (${esc(x.score)})` +
      (opp != null ? `<br>drużyna: ${own ?? "b/d"} · rywal: ${opp}` : ""),
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
    s += `<rect class="hit" x="${cx - sw / 2}" y="0" width="${sw}" height="${base + 36}" data-tip="${esc(hitTip)}" tabindex="0"/>`;
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

const compShort = (c) => ({ "Liga Mistrzów": "LM", "Liga Europy": "LE", "Liga Konferencji": "LK",
  "Superpuchar UEFA": "Superpuchar", "Tarcza Wspólnoty": "Tarcza" }[c] || (c && c.startsWith("Puchar") ? "Puchar" : c) || "");

function groupedChart(m, h2h, k, yMax) {
  const H = 70, base = TOP + H, slots = Math.max(h2h.length, 4);
  const anyComp = h2h.some((g) => g.comp);
  const sw = (W - PAD_L - PAD_R) / slots, bw = Math.min(16, sw * 0.28), gap = 2;
  const y = (v) => base - (v / yMax) * H;
  let s = `<line class="grid" x1="0" x2="${W}" y1="${base}" y2="${base}"/>`;
  h2h.forEach((g, i) => {
    const cx = PAD_L + sw * i + sw / 2;
    const vals = [["home", g.stats[k].home, cx - gap / 2 - bw], ["away", g.stats[k].away, cx + gap / 2]];
    const t = `${shortDate(g.date)}${g.comp ? " · " + esc(g.comp) : ""}<br>${esc(g.label)} ${esc(g.score)}<br>` +
      `${esc(m.home.name)}: <b>${g.stats[k].home ?? "b/d"}</b><br>${esc(m.away.name)}: <b>${g.stats[k].away ?? "b/d"}</b>`;
    s += `<rect class="hit" x="${cx - sw / 2}" y="0" width="${sw}" height="${base + 36}" data-tip="${esc(t)}" tabindex="0"/>`;
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
    if (anyComp) s += `<text x="${cx}" y="${base + 31}" text-anchor="middle" class="${g.comp && g.comp !== "Liga" ? "cup" : ""}">${esc(compShort(g.comp))}</text>`;
  });
  return `<div class="chart"><svg viewBox="0 0 ${W} ${base + (anyComp ? 34 : 24)}" role="img" aria-label="Porównanie w meczach H2H">${s}</svg></div>`;
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
