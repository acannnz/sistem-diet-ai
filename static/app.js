// ---------- Utilitas ----------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const r0 = (n) => Math.round(n || 0);
const MEALS = { sarapan: "Sarapan", siang: "Makan siang", camilan: "Camilan", malam: "Makan malam" };

async function api(path, opts = {}) {
  const init = { credentials: "same-origin", ...opts };
  if (opts.json !== undefined) {
    init.method = opts.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.json);
  }
  const res = await fetch("api/" + path, init);
  if (res.status === 401 && path !== "login") { showLogin(); throw new Error("Belum login"); }
  if ([502, 503, 504].includes(res.status) && !(res.headers.get("content-type") || "").includes("json")) {
    throw new Error("Server sedang sibuk atau baru di-update. Tunggu sebentar lalu coba lagi.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Terjadi kesalahan (" + res.status + ")");
  return data;
}

function isoDate(d) {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
}

// ---------- State ----------
const state = { date: isoDate(new Date()), me: null, scanItems: [], chat: [] };

// ---------- Login ----------
function showLogin() {
  $("#app").classList.add("hidden");
  $("#login").classList.remove("hidden");
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  $("#login-error").textContent = "";
  try {
    await api("login", { json: { username: f.get("username"), pin: f.get("pin") } });
    start();
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});

$("#btn-logout").addEventListener("click", async () => {
  await api("logout", { json: {} });
  showLogin();
});

async function start() {
  state.me = await api("me");
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  if (!state.me.targets) switchTab("profile");
  else switchTab("today");
}

// ---------- Navigasi tab ----------
function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== "tab-" + name));
  $$(".bottom-nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  window.scrollTo(0, 0);
  ({ today: loadDay, history: loadHistory, profile: loadProfile })[name]?.();
}
$$(".bottom-nav button").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

// ---------- Hari ini ----------
$$("[data-day]").forEach((b) =>
  b.addEventListener("click", () => {
    const d = new Date(state.date + "T12:00:00");
    d.setDate(d.getDate() + Number(b.dataset.day));
    if (isoDate(d) > isoDate(new Date())) return;
    state.date = isoDate(d);
    loadDay();
  })
);

const MEAL_ICON = { sarapan: "🌅", siang: "☀️", camilan: "🍪", malam: "🌙" };

function ringSvg(value, target) {
  const pct = target ? Math.min(value / target, 1) : 0;
  const over = target && value > target;
  const R = 62, C = 2 * Math.PI * R;
  const left = target ? r0(target - value) : null;
  return `<svg viewBox="0 0 150 150" role="img" aria-label="${r0(value)} kkal">
    <circle cx="75" cy="75" r="${R}" fill="none" stroke="rgba(255,255,255,.22)" stroke-width="13"/>
    <circle cx="75" cy="75" r="${R}" fill="none" stroke="${over ? "#fecaca" : "#fff"}" stroke-width="13" stroke-linecap="round"
      stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}" transform="rotate(-90 75 75)"
      style="transition:stroke-dashoffset .8s cubic-bezier(.2,.8,.2,1)"/>
    <text x="75" y="72" text-anchor="middle" style="font-size:32px;font-weight:800;fill:#fff">${r0(value)}</text>
    <text x="75" y="93" text-anchor="middle" style="font-size:12px;font-weight:600;fill:rgba(255,255,255,.85)">kkal masuk</text>
  </svg>`;
}

function heroStats(value, target) {
  if (!target) return `<div class="stat"><small>Target belum ada</small><b style="font-size:14px">Lengkapi profil dulu ya</b></div>`;
  const left = target - value;
  return `<div class="stat"><small>Target harian</small><b>${r0(target)} <span>kkal</span></b></div>
    <div class="stat"><small>${left >= 0 ? "Sisa kalori" : "Kelebihan"}</small><b>${r0(Math.abs(left))} <span>kkal</span></b></div>
    <div class="stat"><small>Progres</small><b>${r0((value / target) * 100)}<span>%</span></b></div>`;
}

function macroCard(label, val, target, color) {
  const pct = target ? Math.min((val / target) * 100, 100) : 0;
  return `<div class="macro"><div class="name"><i style="background:${color}"></i>${label}</div>
    <div class="val">${r0(val)}<span>${target ? " / " + target : ""} g</span></div>
    <div class="bar"><div style="width:${pct}%;background:${color}"></div></div></div>`;
}

function greeting() {
  const h = new Date().getHours();
  const part = h < 11 ? "Selamat pagi" : h < 15 ? "Selamat siang" : h < 18 ? "Selamat sore" : "Selamat malam";
  const name = state.me?.user?.display_name || "";
  return `${part}${name ? ", " + name : ""} 👋`;
}

async function loadDay() {
  const today = isoDate(new Date());
  $("#hello").textContent = greeting();
  $("#day-label").textContent = state.date === today ? "Hari ini"
    : new Date(state.date + "T12:00:00").toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "short" });
  $("[data-day='1']").disabled = state.date >= today;
  const data = await api("day?date=" + state.date);
  const t = data.targets || {};
  $("#ring").innerHTML = ringSvg(data.totals.kcal, t.kcal);
  $("#hero-stats").innerHTML = heroStats(data.totals.kcal, t.kcal);
  $("#demo-pill").classList.toggle("hidden", !data.is_demo);
  $("#macros").innerHTML =
    macroCard("Protein", data.totals.protein, t.protein, "var(--protein)") +
    macroCard("Karbo", data.totals.carb, t.carb, "var(--carb)") +
    macroCard("Lemak", data.totals.fat, t.fat, "var(--fat)");

  const groups = {};
  data.logs.forEach((l) => (groups[l.meal] ||= []).push(l));
  $("#meals").innerHTML = data.logs.length
    ? Object.entries(MEALS).filter(([k]) => groups[k]).map(([k, label]) => {
        const items = groups[k];
        const sum = items.reduce((s, i) => s + i.kcal, 0);
        return `<div class="card meal">
          <div class="meal-head"><div class="meal-icon">${MEAL_ICON[k]}</div><h3>${label}</h3><span class="sum">${r0(sum)} kkal</span></div>
          ${items.map((i) => `<div class="log-item" data-id="${i.id}" data-name="${esc(i.name)}" data-grams="${i.grams}">
            <div><div class="name">${esc(i.name)}${i.source === "ai" ? '<span class="badge ai">perkiraan AI</span>' : ""}</div>
            <div class="meta">${r0(i.grams)} g · ${i.time}</div></div>
            <div class="kc">${r0(i.kcal)} <span>kkal</span></div></div>`).join("")}
        </div>`;
      }).join("")
    : `<div class="empty"><span class="big">🍽️</span><b>Belum ada catatan makan</b>Tekan tombol kamera di bawah untuk scan makananmu.</div>`;

  $$(".log-item").forEach((el) => el.addEventListener("click", () => editLog(el.dataset)));

  if (state.date === today) {
    api("couple").then((list) => {
      $("#couple").innerHTML = list.length > 1 ? list.map((p) =>
        `<div class="pill ${p.me ? "me" : ""}"><div class="avatar">${esc((p.name || "?")[0].toUpperCase())}</div>
          <div style="min-width:0"><div class="who">${esc(p.name)}${p.me ? " (kamu)" : ""}</div>
          <div class="kc">${r0(p.kcal)}${p.target ? `<span> / ${p.target} kkal</span>` : "<span> kkal</span>"}</div></div></div>`
      ).join("") : "";
    }).catch(() => {});
  } else {
    $("#couple").innerHTML = "";
  }
}

function editLog({ id, name, grams }) {
  const dlg = $("#log-dialog");
  $("#log-dialog-title").textContent = name;
  $("#log-grams").value = r0(grams);
  dlg.onclose = async () => {
    try {
      if (dlg.returnValue === "save") await api("logs/" + id, { method: "PATCH", json: { grams: Number($("#log-grams").value) } });
      if (dlg.returnValue === "delete") await api("logs/" + id, { method: "DELETE" });
      loadDay();
    } catch (err) { alert(err.message); }
  };
  dlg.showModal();
}

// ---------- Dialog cari makanan ----------
let foodDialogCallback = null;
let pickedFood = null;
let searchTimer = null;

function openFoodDialog({ title, showMeal, onPick }) {
  foodDialogCallback = onPick;
  pickedFood = null;
  $("#food-dialog-title").textContent = title;
  $("#food-meal-wrap").classList.toggle("hidden", !showMeal);
  $("#food-search").value = "";
  $("#food-results").innerHTML = "";
  $("#food-pick").classList.add("hidden");
  $("#food-dialog").showModal();
  $("#food-search").focus();
}

$("#food-search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 2) { $("#food-results").innerHTML = ""; return; }
  searchTimer = setTimeout(async () => {
    const list = await api("foods?q=" + encodeURIComponent(q));
    $("#food-results").innerHTML = list.length ? list.map((f, i) =>
      `<button type="button" data-i="${i}">${esc(f.name)}<br><small>${r0(f.kcal)} kkal / 100 g${f.portion_label ? " · " + esc(f.portion_label) : ""}</small></button>`
    ).join("") : `<p class="muted small">Tidak ditemukan di database gizi.</p>`;
    $$("#food-results button").forEach((b) => b.addEventListener("click", () => pickFood(list[b.dataset.i])));
  }, 250);
});

function pickFood(food) {
  pickedFood = food;
  $("#food-results").innerHTML = "";
  $("#food-pick").classList.remove("hidden");
  $("#food-pick-name").innerHTML = `<b>${esc(food.name)}</b>`;
  $("#food-grams").value = r0(food.portion_g || 100);
  $("#food-meal").value = guessMeal();
  updatePickKcal();
}
function updatePickKcal() {
  if (!pickedFood) return;
  const g = Number($("#food-grams").value) || 0;
  $("#food-pick-kcal").textContent = `≈ ${r0((pickedFood.kcal * g) / 100)} kkal`;
}
$("#food-grams").addEventListener("input", updatePickKcal);

$("#food-dialog").addEventListener("close", () => {
  if ($("#food-dialog").returnValue === "ok" && pickedFood && foodDialogCallback) {
    foodDialogCallback(pickedFood, Number($("#food-grams").value) || 100, $("#food-meal").value);
  }
});

function guessMeal() {
  const h = new Date().getHours();
  return h >= 4 && h < 10 ? "sarapan" : h < 15 && h >= 10 ? "siang" : h < 18 && h >= 15 ? "camilan" : "malam";
}

$("#btn-manual").addEventListener("click", () =>
  openFoodDialog({
    title: "Tambah manual",
    showMeal: true,
    onPick: async (food, grams, meal) => {
      try {
        await api("logs", { json: { meal, date: state.date, items: [{ food_id: food.id, name: food.name, grams }] } });
        loadDay();
      } catch (err) { alert(err.message); }
    },
  })
);

// ---------- Scan ----------
function resizeImage(file, max = 1024) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      c.toBlob((b) => (b ? resolve(b) : reject(new Error("Gagal memproses foto"))), "image/jpeg", 0.82);
    };
    img.onerror = () => reject(new Error("Foto tidak bisa dibaca"));
    img.src = URL.createObjectURL(file);
  });
}

function loadImage(blob) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Foto tidak bisa dibaca"));
    img.src = URL.createObjectURL(blob);
  });
}

// Potong gambar ke kotak [x, y, w, h] (skala 0-1). pad = ruang tambahan di tepi.
function cropImage(img, box, { pad = 0, max = 1024 } = {}) {
  const W = img.naturalWidth, H = img.naturalHeight;
  const x = Math.max(0, (box[0] - pad) * W), y = Math.max(0, (box[1] - pad) * H);
  const w = Math.min(W - x, (box[2] + pad * 2) * W), h = Math.min(H - y, (box[3] + pad * 2) * H);
  const scale = Math.min(1, max / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.round(w * scale);
  c.height = Math.round(h * scale);
  c.getContext("2d").drawImage(img, x, y, w, h, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.85);
}

function setPreview(src, cropped) {
  const el = $("#scan-preview");
  el.classList.add("swap");
  setTimeout(() => {
    el.src = src;
    el.onload = () => el.classList.remove("swap");
    $("#crop-badge").classList.toggle("hidden", !cropped);
  }, 180);
}

$("#scan-preview").addEventListener("click", () => {
  // Ketuk foto untuk bergantian melihat hasil crop / foto asli
  const s = state.photo;
  if (!s?.cropped) return;
  s.showCropped = !s.showCropped;
  setPreview(s.showCropped ? s.cropped : s.original, s.showCropped);
});

async function handlePhoto(file) {
  if (!file) return;
  $("#scan-start").classList.add("hidden");
  $("#scan-result").classList.remove("hidden");
  $("#scan-actions").classList.add("hidden");
  $("#scan-items").innerHTML = "";
  $("#scan-note").textContent = "";
  $("#scan-error").textContent = "";
  $("#scan-loading").classList.remove("hidden");
  state.scanItems = [];
  try {
    const blob = await resizeImage(file);
    const img = await loadImage(blob);
    state.photo = { img, original: img.src, cropped: null, showCropped: false };
    $("#crop-badge").classList.add("hidden");
    $("#scan-preview").src = img.src;
    const fd = new FormData();
    fd.append("image", blob, "foto.jpg");
    fd.append("hint", $("#scan-hint").value);
    const data = await api("scan", { method: "POST", body: fd });
    state.scanItems = data.items;
    // Auto-crop: fokuskan foto ke area makanan/minuman yang terdeteksi
    if (data.crop) {
      state.photo.cropped = cropImage(img, data.crop);
      state.photo.showCropped = true;
      setPreview(state.photo.cropped, true);
    }
    data.items.forEach((it) => { if (it.box) it.thumb = cropImage(img, it.box, { pad: 0.02, max: 160 }); });
    $("#scan-meal").value = data.meal;
    $("#scan-note").textContent = data.note || "";
    if (!data.items.length) $("#scan-error").textContent = "Tidak ada makanan yang terdeteksi. Coba foto ulang atau tambah item manual.";
    $("#scan-actions").classList.remove("hidden");
    renderScanItems();
  } catch (err) {
    $("#scan-error").textContent = err.message;
    $("#scan-actions").classList.remove("hidden");
  } finally {
    $("#scan-loading").classList.add("hidden");
  }
}

$("#photo-input").addEventListener("change", (e) => { handlePhoto(e.target.files[0]); e.target.value = ""; });
$("#gallery-input").addEventListener("change", (e) => { handlePhoto(e.target.files[0]); e.target.value = ""; });
$("#btn-rescan").addEventListener("click", resetScan);

function resetScan() {
  state.scanItems = [];
  $("#scan-hint").value = "";
  $("#scan-start").classList.remove("hidden");
  $("#scan-result").classList.add("hidden");
}

function per100(item) {
  if (item.food_id) return item.matches.find((m) => m.id === item.food_id) || item.per100g;
  return item.per100g;
}

function renderScanItems() {
  $("#scan-items").innerHTML = state.scanItems.map((it, i) => {
    const opts = it.matches.map((m) =>
      `<option value="${m.id}" ${m.id === it.food_id ? "selected" : ""}>${esc(m.name)} (${r0(m.kcal)} kkal/100g)</option>`
    ).join("");
    // Selalu tampilkan pilihan perkiraan AI (termasuk 0 kkal, mis. air putih)
    const aiOpt = it.per100g
      ? `<option value="ai" ${!it.food_id ? "selected" : ""}>Perkiraan AI: ${esc(it.name)} (${r0(it.per100g.kcal)} kkal/100g)</option>` : "";
    return `<div class="card scan-item" data-i="${i}">
      <div class="head">
        ${it.thumb ? `<img class="thumb" src="${it.thumb}" alt="">` : ""}
        <div style="flex:1;min-width:0"><b>${esc(it.name)}</b><div class="portion">${esc(it.portion || "")}</div></div>
        <div style="display:flex;gap:6px;align-items:center"><span class="kcal" data-kcal></span><button class="remove" data-remove aria-label="Hapus">✕</button></div>
      </div>
      <select data-match>${opts}${aiOpt}</select>
      <div class="qty">
        <button class="step" type="button" data-step="0.5">½×</button>
        <input type="number" inputmode="decimal" min="1" value="${r0(it.grams)}" data-grams aria-label="Gram">
        <span class="unit">gram</span>
        <button class="step" type="button" data-step="1.5">1½×</button>
      </div>
    </div>`;
  }).join("");

  $$(".scan-item").forEach((el) => {
    const it = state.scanItems[el.dataset.i];
    $("[data-match]", el).addEventListener("change", (e) => {
      it.food_id = e.target.value === "ai" ? null : Number(e.target.value);
      updateScanTotals();
    });
    $("[data-grams]", el).addEventListener("input", (e) => { it.grams = Number(e.target.value) || 0; updateScanTotals(); });
    $$("[data-step]", el).forEach((b) => b.addEventListener("click", () => {
      it.grams = Math.max(1, Math.round(it.grams * Number(b.dataset.step)));
      $("[data-grams]", el).value = it.grams;
      updateScanTotals();
    }));
    $("[data-remove]", el).addEventListener("click", () => { state.scanItems.splice(el.dataset.i, 1); renderScanItems(); });
  });
  updateScanTotals();
}

function updateScanTotals() {
  let total = 0;
  $$(".scan-item").forEach((el) => {
    const it = state.scanItems[el.dataset.i];
    const kcal = ((per100(it)?.kcal || 0) * it.grams) / 100;
    total += kcal;
    $("[data-kcal]", el).textContent = r0(kcal) + " kkal";
  });
  $("#scan-total").textContent = r0(total) + " kkal";
  $("#btn-save-scan").disabled = !state.scanItems.length;
}

$("#btn-add-item").addEventListener("click", () =>
  openFoodDialog({
    title: "Tambah item",
    showMeal: false,
    onPick: (food, grams) => {
      state.scanItems.push({ name: food.name, grams, portion: "", per100g: null, matches: [food], food_id: food.id });
      renderScanItems();
    },
  })
);

$("#btn-save-scan").addEventListener("click", async (e) => {
  e.target.disabled = true;
  try {
    await api("logs", {
      json: {
        meal: $("#scan-meal").value,
        items: state.scanItems.filter((it) => it.grams > 0).map((it) => ({
          food_id: it.food_id, name: it.name, grams: it.grams, per100g: it.food_id ? null : it.per100g,
        })),
      },
    });
    resetScan();
    state.date = isoDate(new Date());
    switchTab("today");
  } catch (err) {
    alert(err.message);
  } finally {
    e.target.disabled = false;
  }
});

// ---------- Riwayat ----------
async function loadHistory() {
  const data = await api("history?days=14");
  const target = data.targets?.kcal;
  const W = 340, H = 170, P = 28;
  const max = Math.max(target || 0, ...data.days.map((d) => d.kcal), 500) * 1.12;
  const bw = (W - P) / data.days.length;
  const y = (v) => H - 20 - (v / max) * (H - 32);
  const today = isoDate(new Date());
  const bars = data.days.map((d, i) => {
    const over = target && d.kcal > target;
    const x = P + i * bw;
    const day = new Date(d.date + "T12:00:00").getDate();
    const h = Math.max(H - 20 - y(d.kcal), d.kcal ? 3 : 0);
    return `<rect x="${x + 3}" y="${H - 20 - h}" width="${bw - 6}" height="${h}" rx="5"
      fill="${over ? "var(--danger)" : "url(#barGrad)"}"><title>${d.date}: ${r0(d.kcal)} kkal</title></rect>
      <text x="${x + bw / 2}" y="${H - 5}" text-anchor="middle" style="${d.date === today ? "font-weight:800;fill:var(--sky-dark)" : ""}">${day}</text>`;
  }).join("");
  const line = target ? `<line x1="${P}" x2="${W}" y1="${y(target)}" y2="${y(target)}" stroke="var(--sky-dark)" stroke-dasharray="5 5" opacity=".6"/>
    <text x="0" y="${y(target) + 3}" style="font-weight:700;fill:var(--sky-dark)">${target}</text>` : "";
  $("#kcal-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}">
    <defs><linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#38bdf8"/><stop offset="1" stop-color="#0284c7"/></linearGradient></defs>
    ${line}${bars}</svg>`;

  const ws = data.weights;
  if (ws.length < 2) {
    $("#weight-chart").innerHTML = `<p class="muted small" style="margin:12px 0 0">${ws.length ? `Terakhir tercatat <b>${ws[0].weight_kg} kg</b>. ` : "Belum ada data berat badan. "}Catat rutin untuk melihat grafiknya.</p>`;
    return;
  }
  const vals = ws.map((w) => w.weight_kg);
  const lo = Math.min(...vals) - 1, hi = Math.max(...vals) + 1;
  const px = (i) => P + (i / (ws.length - 1)) * (W - P - 10);
  const py = (v) => 12 + (1 - (v - lo) / (hi - lo)) * (H - 44);
  const pts = ws.map((w, i) => `${px(i)},${py(w.weight_kg)}`).join(" ");
  const area = `${px(0)},${H - 20} ${pts} ${px(ws.length - 1)},${H - 20}`;
  const diff = vals.at(-1) - vals[0];
  $("#weight-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="margin-top:14px">
      <defs><linearGradient id="wGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#38bdf8" stop-opacity=".35"/><stop offset="1" stop-color="#38bdf8" stop-opacity="0"/></linearGradient></defs>
      <polygon points="${area}" fill="url(#wGrad)"/>
      <polyline points="${pts}" fill="none" stroke="var(--sky-dark)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
      ${ws.map((w, i) => `<circle cx="${px(i)}" cy="${py(w.weight_kg)}" r="4" fill="var(--card)" stroke="var(--sky-dark)" stroke-width="2.5"><title>${w.date}: ${w.weight_kg} kg</title></circle>`).join("")}
      <text x="0" y="${py(hi - 1) + 3}">${hi - 1}</text><text x="0" y="${py(lo + 1) + 3}">${lo + 1}</text>
    </svg>
    <div class="weight-sum">
      <div>Sekarang<b>${vals.at(-1)} kg</b></div>
      <div class="${diff <= 0 ? "down" : "up"}">${diff <= 0 ? "Turun" : "Naik"}<b>${Math.abs(diff).toFixed(1)} kg</b></div>
      <div>Sejak<b style="font-size:14px">${new Date(ws[0].date + "T12:00:00").toLocaleDateString("id-ID", { day: "numeric", month: "short" })}</b></div>
    </div>`;
}

$("#weight-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("weights", { json: { weight_kg: Number(e.target.weight.value) } });
    e.target.reset();
    loadHistory();
  } catch (err) { alert(err.message); }
});

// ---------- Coach ----------
function scrollChat(behavior = "auto") {
  // Gulir ke paling bawah halaman (kolom ketik menempel di bawah, jadi jangan pakai scrollIntoView)
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior });
}

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = "bubble " + role;
  div.textContent = text;
  $("#chat-log").appendChild(div);
  scrollChat("smooth");
  return div;
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = e.target.msg;
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addBubble("user", text);
  state.chat.push({ role: "user", content: text });
  $("#chat-chips").classList.add("hidden");
  const pending = addBubble("assistant typing", "•••");
  const sendBtn = $(".send-btn");
  sendBtn.disabled = true;
  try {
    const res = await fetch("api/chat", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.chat }),
    });
    if (res.status === 401) { showLogin(); throw new Error("Belum login"); }
    if (!res.ok) throw new Error("Terjadi kesalahan (" + res.status + ")");
    // Tampilkan jawaban sepotong demi sepotong selagi AI mengetik
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let reply = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      reply += decoder.decode(value, { stream: true });
      if (reply.trim()) {
        pending.classList.remove("typing");
        pending.textContent = reply;
        scrollChat();
      }
    }
    reply = reply.trim();
    if (!reply) throw new Error("Coach tidak membalas, coba lagi.");
    pending.textContent = reply;
    scrollChat();
    state.chat.push({ role: "assistant", content: reply });
  } catch (err) {
    pending.classList.remove("typing");
    pending.textContent = "⚠️ " + err.message;
    state.chat.pop();
  } finally {
    sendBtn.disabled = false;
  }
});

$$("#chat-chips button").forEach((b) => b.addEventListener("click", () => {
  $("#chat-form").msg.value = b.textContent;
  $("#chat-form").requestSubmit();
}));

// ---------- Profil ----------
function renderTargets(p) {
  const t = p.targets;
  $("#targets-card").innerHTML = t
    ? `<h3>Target harian kamu</h3>
        <div class="big">${t.kcal} <span>kkal / hari</span></div>
        <div class="targets">
          <div>Protein<b>${t.protein} g</b></div><div>Karbo<b>${t.carb} g</b></div><div>Lemak<b>${t.fat} g</b></div>
          <div>BMR<b>${t.bmr}</b></div><div>TDEE<b>${t.tdee}</b></div><div>Tujuan<b>${{ turun: "Turun", jaga: "Jaga", naik: "Naik" }[p.user.goal] || "-"}</b></div>
        </div>
        <p>Dihitung dengan rumus Mifflin-St Jeor. Punya target dari ahli gizi? Isi "Target kalori manual".</p>`
    : `<h3>Belum ada target</h3><p>Lengkapi tahun lahir, tinggi, dan berat di bawah untuk menghitung target kalorimu.</p>`;
}

async function loadProfile() {
  const p = (state.me = await api("me"));
  const f = $("#profile-form");
  for (const [k, v] of Object.entries(p.user)) if (f.elements[k]) f.elements[k].value = v ?? "";
  if (!p.user.sex) f.elements.sex.value = "L";
  renderTargets(p);
}

$("#profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const num = (n) => (f.elements[n].value === "" ? null : Number(f.elements[n].value));
  try {
    const p = await api("me", {
      method: "PUT",
      json: {
        display_name: f.elements.display_name.value || null,
        sex: f.elements.sex.value, activity: f.elements.activity.value, goal: f.elements.goal.value,
        birth_year: num("birth_year"), height_cm: num("height_cm"), weight_kg: num("weight_kg"), target_kcal: num("target_kcal"),
      },
    });
    state.me = p;
    renderTargets(p);
    $("#profile-msg").textContent = "Tersimpan ✓";
    setTimeout(() => ($("#profile-msg").textContent = ""), 2000);
  } catch (err) {
    $("#profile-msg").textContent = err.message;
  }
});

// ---------- Mulai ----------
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
start().catch(() => showLogin());
