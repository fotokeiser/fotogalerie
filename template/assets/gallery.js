/* Fotogalerie – Interaktion */
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("gallery-data").textContent);
  const $ = (s) => document.querySelector(s);

  const ICON = {
    heart: '<svg viewBox="0 0 24 24"><path d="M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z"/></svg>',
    dl: '<svg viewBox="0 0 24 24"><path d="M12 4v11m-4.5-4.5L12 15l4.5-4.5M5 19.5h14"/></svg>',
    zip: '<svg viewBox="0 0 24 24"><path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5z M4 7.5 12 12l8-4.5 M12 12v9"/></svg>',
    mail: '<svg viewBox="0 0 24 24"><path d="M3.5 6h17v12h-17z M3.5 6.5 12 13l8.5-6.5"/></svg>',
    copy: '<svg viewBox="0 0 24 24"><path d="M8 8h11v12H8z M5 16V4h11"/></svg>',
  };

  // ---------- Daten ----------
  const all = [];
  data.sets.forEach((s, si) => s.images.forEach((img) => { img.set = si; all.push(img); }));
  const byId = new Map(all.map((i) => [i.id, i]));

  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const FAV_KEY = "fotogalerie:fav:" + data.slug;
  const favs = new Set(store.get(FAV_KEY, []).filter((id) => byId.has(id)));
  let view = "all";

  // ---------- Hilfen ----------
  const toastEl = $("#toast");
  let toastT;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastT);
    toastT = setTimeout(() => toastEl.classList.remove("show"), 2400);
  }
  function fmtSize(n) {
    const u = ["B", "KB", "MB", "GB"]; let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i >= 2 ? n.toFixed(1) : Math.round(n)).toString().replace(".", ",") + " " + u[i];
  }
  function download(img) {
    const a = document.createElement("a");
    a.href = img.dl;
    a.download = img.name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  async function downloadMany(list) {
    if (!list.length) return;
    toast(`${list.length} Fotos werden heruntergeladen …`);
    for (const img of list) {
      download(img);
      await new Promise((r) => setTimeout(r, 700));
    }
  }

  // ---------- Raster (Justified Layout) ----------
  const content = $("#content");
  const grids = [];

  function tile(img) {
    const f = document.createElement("figure");
    f.className = "tile" + (favs.has(img.id) ? " fav" : "");
    f.dataset.id = img.id;
    f.tabIndex = 0;
    f.innerHTML =
      '<img alt="" loading="lazy" decoding="async">' +
      '<div class="tile-ui">' +
      `<button class="tile-btn fav" type="button" aria-label="Als Favorit markieren">${ICON.heart}</button>` +
      (data.download ? `<button class="tile-btn dl" type="button" aria-label="Herunterladen">${ICON.dl}</button>` : "") +
      "</div>";
    const im = f.firstChild;
    im.addEventListener("load", () => f.classList.add("loaded"), { once: true });
    im.src = img.t;
    return f;
  }

  function makeGrid(images) {
    const el = document.createElement("div");
    el.className = "grid";
    const tiles = images.map((img) => { const t = tile(img); el.appendChild(t); return t; });
    const g = { el, images, tiles };
    grids.push(g);
    return el;
  }

  function layout(g) {
    const W = g.el.clientWidth;
    if (!W) return;
    const gap = W < 600 ? 4 : W < 1100 ? 8 : 10;
    const target = W < 600 ? 170 : W < 1100 ? 260 : 340;
    let y = 0, row = [], ar = 0;
    const place = (items, h) => {
      let x = 0;
      items.forEach((i) => {
        const w = (g.images[i].w / g.images[i].h) * h;
        Object.assign(g.tiles[i].style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
        x += w + gap;
      });
      y += h + gap;
    };
    g.images.forEach((img, i) => {
      row.push(i);
      ar += img.w / img.h;
      const h = (W - gap * (row.length - 1)) / ar;
      if (h <= target) { place(row, h); row = []; ar = 0; }
    });
    if (row.length) place(row, Math.min(target, (W - gap * (row.length - 1)) / ar));
    g.el.style.height = Math.max(0, y - gap) + "px";
  }
  const layoutAll = () => grids.forEach(layout);
  let lastW = 0;
  new ResizeObserver(() => {
    const w = content.clientWidth;
    if (w !== lastW) { lastW = w; layoutAll(); }
  }).observe(content);

  function section(title, sub, images, id) {
    const s = document.createElement("section");
    s.className = "section";
    if (id) s.id = id;
    if (title) {
      const h = document.createElement("div");
      h.className = "section-head";
      h.innerHTML = `<h2></h2>${sub ? "<p></p>" : ""}`;
      h.querySelector("h2").textContent = title;
      if (sub) h.querySelector("p").textContent = sub;
      s.appendChild(h);
    }
    if (images.length) s.appendChild(makeGrid(images));
    return s;
  }

  function render() {
    grids.length = 0;
    content.replaceChildren();
    if (view === "favs") {
      const list = all.filter((i) => favs.has(i.id));
      const s = section("Ihre Favoriten", list.length ? `${list.length} ${list.length === 1 ? "Foto" : "Fotos"} ausgewählt` : "", list);
      if (!list.length) {
        const e = document.createElement("div");
        e.className = "empty";
        e.innerHTML = `${ICON.heart}<p>Noch keine Favoriten. Tippen Sie auf das Herz bei einem Foto, um es hier zu sammeln.</p>`;
        s.appendChild(e);
      } else {
        const acts = document.createElement("div");
        acts.className = "section-actions";
        if (data.download) acts.appendChild(button("btn btn-dark", ICON.dl + "<span>Favoriten herunterladen</span>", () => downloadMany(list)));
        if (data.email) acts.appendChild(button("btn btn-line", ICON.mail + "<span>Auswahl senden</span>", () => sendSelection(list)));
        acts.appendChild(button("btn btn-line", ICON.copy + "<span>Liste kopieren</span>", () => copyList(list)));
        s.querySelector(".section-head").appendChild(acts);
      }
      content.appendChild(s);
    } else {
      const named = data.sets.filter((s) => s.name).length;
      data.sets.forEach((set, i) => {
        if (!set.images.length) return;
        content.appendChild(section(named > 1 || set.name ? set.name : "", "", set.images, "set-" + i));
      });
    }
    lastW = content.clientWidth;
    layoutAll();
    observeSets();
  }

  function button(cls, html, fn) {
    const b = document.createElement("button");
    b.type = "button"; b.className = cls; b.innerHTML = html;
    b.addEventListener("click", fn);
    return b;
  }

  function fileList(list) { return list.map((i) => i.name).join("\n"); }
  function sendSelection(list) {
    const subject = `Favoriten – ${data.title}`;
    const body = `Hallo,\n\nhier ist meine Auswahl aus der Galerie „${data.title}“ (${list.length} Fotos):\n\n${fileList(list)}\n\nViele Grüße`;
    location.href = `mailto:${data.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
  async function copyList(list) {
    try { await navigator.clipboard.writeText(fileList(list)); toast("Dateiliste kopiert"); }
    catch { toast("Kopieren nicht möglich"); }
  }

  // ---------- Favoriten ----------
  const favToggle = $("#favToggle"), favCount = $("#favCount");
  function updateFavUI() {
    favCount.textContent = favs.size;
    favCount.hidden = favs.size === 0;
    favToggle.setAttribute("aria-pressed", view === "favs");
  }
  function toggleFav(id) {
    if (favs.has(id)) favs.delete(id); else favs.add(id);
    store.set(FAV_KEY, [...favs]);
    document.querySelectorAll(`.tile[data-id="${CSS.escape(id)}"]`).forEach((t) => t.classList.toggle("fav", favs.has(id)));
    updateFavUI();
    if (lb.open && lb.list[lb.i].id === id) $("#lbFav").classList.toggle("on", favs.has(id));
    return favs.has(id);
  }
  favToggle.addEventListener("click", () => {
    view = view === "favs" ? "all" : "favs";
    updateFavUI();
    setsEl.style.visibility = view === "favs" ? "hidden" : "";
    render();
    document.getElementById("galerie").scrollIntoView();
  });

  // ---------- Klicks im Raster ----------
  content.addEventListener("click", (e) => {
    const t = e.target.closest(".tile");
    if (!t) return;
    const img = byId.get(t.dataset.id);
    if (e.target.closest(".tile-btn.fav")) { toast(toggleFav(img.id) ? "Zu Favoriten hinzugefügt" : "Aus Favoriten entfernt"); return; }
    if (e.target.closest(".tile-btn.dl")) { download(img); return; }
    openLb(img.id);
  });
  content.addEventListener("keydown", (e) => {
    const t = e.target.closest(".tile");
    if (t && e.key === "Enter") openLb(t.dataset.id);
  });

  // ---------- Set-Navigation ----------
  const setsEl = $("#sets");
  const namedSets = data.sets.map((s, i) => ({ ...s, i })).filter((s) => s.name && s.images.length);
  if (namedSets.length > 1) {
    namedSets.forEach((s) => {
      const b = button("", "", () => document.getElementById("set-" + s.i)?.scrollIntoView({ behavior: "smooth" }));
      b.textContent = s.name;
      b.dataset.set = s.i;
      setsEl.appendChild(b);
    });
  }
  let setObs;
  function observeSets() {
    setObs?.disconnect();
    if (!setsEl.children.length) return;
    setObs = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        const i = en.target.id.replace("set-", "");
        setsEl.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.set === i));
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    content.querySelectorAll(".section[id]").forEach((s) => setObs.observe(s));
  }

  // Leiste bekommt Linie, sobald sie oben klebt
  const bar = $("#bar");
  new IntersectionObserver(([en]) => bar.classList.toggle("stuck", !en.isIntersecting), { threshold: 0 })
    .observe(document.getElementById("top"));

  // ---------- Teilen ----------
  $("#shareBtn").addEventListener("click", async () => {
    const url = location.href.split("#")[0];
    if (navigator.share && matchMedia("(pointer: coarse)").matches) {
      try { await navigator.share({ title: data.title, url }); } catch {}
      return;
    }
    try { await navigator.clipboard.writeText(url); toast("Link kopiert"); }
    catch { prompt("Link zur Galerie:", url); }
  });

  // ---------- Download-Dialog ----------
  const modal = $("#modal"), modalBody = $("#modalBody");
  const dlAll = $("#dlAllBtn");
  if (!data.download) dlAll.hidden = true;
  function openModal() {
    const total = all.reduce((s, i) => s + (i.size || 0), 0);
    let h = "";
    if (data.zips.length) {
      h += `<p>${all.length} Fotos in voller Auflösung${data.zips.length > 1 ? `, aufgeteilt in ${data.zips.length} Pakete` : ""}.</p><ul class="dl-list">`;
      data.zips.forEach((z, i) => {
        const label = data.zips.length > 1 ? `Paket ${i + 1} von ${data.zips.length}` : "Alle Fotos (ZIP)";
        h += `<li><a href="${z.url}" download><span class="dl-label">${ICON.zip}${label}</span><small>${z.sizeText}</small></a></li>`;
      });
      h += "</ul>";
    } else {
      h += `<p>${all.length} Fotos${data.originals ? ` · ${fmtSize(total)} in voller Auflösung` : ""}. Einzelne Fotos laden Sie über das Download-Symbol am Bild herunter.</p><ul class="dl-list">`;
      h += `<li><button type="button" data-act="all"><span class="dl-label">${ICON.dl}Alle Fotos einzeln laden</span><small>${all.length} Dateien</small></button></li>`;
      h += "</ul>";
    }
    if (favs.size) {
      h += `<ul class="dl-list" style="border-top:0"><li><button type="button" data-act="favs"><span class="dl-label">${ICON.heart}Nur Favoriten</span><small>${favs.size} ${favs.size === 1 ? "Foto" : "Fotos"}</small></button></li></ul>`;
    }
    h += `<p class="hint">Tipp: Am Computer herunterladen – die Dateien sind groß. ${data.originals ? "Die Fotos sind in Originalauflösung." : ""}</p>`;
    modalBody.innerHTML = h;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeModal() { modal.hidden = true; document.body.style.overflow = ""; }
  dlAll.addEventListener("click", openModal);
  $("#modalClose").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) return closeModal();
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "all") { closeModal(); downloadMany(all); }
    if (act === "favs") { closeModal(); downloadMany(all.filter((i) => favs.has(i.id))); }
  });

  // ---------- Lightbox ----------
  const lbEl = $("#lb"), lbImg = $("#lbImg");
  const lb = { open: false, list: all, i: 0, token: 0 };
  if (!data.download) $("#lbDl").hidden = true;

  function openLb(id) {
    lb.list = view === "favs" ? all.filter((i) => favs.has(i.id)) : all;
    lb.i = Math.max(0, lb.list.findIndex((i) => i.id === id));
    lb.open = true;
    lbEl.hidden = false;
    document.body.style.overflow = "hidden";
    show();
  }
  function closeLb() {
    if (!lb.open) return;
    const id = lb.list[lb.i]?.id;
    lb.open = false;
    lbEl.hidden = true;
    document.body.style.overflow = "";
    history.replaceState(null, "", location.pathname + location.search);
    const t = id && document.querySelector(`.tile[data-id="${CSS.escape(id)}"]`);
    if (t) { const r = t.getBoundingClientRect(); if (r.top < 80 || r.bottom > innerHeight) t.scrollIntoView({ block: "center" }); t.focus({ preventScroll: true }); }
  }
  function show() {
    const img = lb.list[lb.i];
    if (!img) return closeLb();
    const token = ++lb.token;
    $("#lbCount").textContent = `${lb.i + 1} / ${lb.list.length}`;
    $("#lbName").textContent = img.name;
    $("#lbFav").classList.toggle("on", favs.has(img.id));
    $("#lbPrev").style.visibility = lb.i > 0 ? "" : "hidden";
    $("#lbNext").style.visibility = lb.i < lb.list.length - 1 ? "" : "hidden";
    history.replaceState(null, "", "#" + img.id);

    // Sofort das (gecachte) Vorschaubild zeigen, dann die große Version nachladen
    lbImg.classList.remove("in");
    lbImg.src = img.t;
    requestAnimationFrame(() => lbImg.classList.add("in"));
    const big = new Image();
    big.onload = () => { if (token === lb.token) lbImg.src = img.p; };
    big.src = img.p;
    // Nachbarn vorladen
    [lb.list[lb.i + 1], lb.list[lb.i - 1]].forEach((n) => { if (n) new Image().src = n.p; });
  }
  const go = (d) => {
    const n = lb.i + d;
    if (n >= 0 && n < lb.list.length) { lb.i = n; show(); }
  };
  $("#lbPrev").addEventListener("click", () => go(-1));
  $("#lbNext").addEventListener("click", () => go(1));
  $("#lbClose").addEventListener("click", closeLb);
  $("#lbFav").addEventListener("click", () => toggleFav(lb.list[lb.i].id));
  $("#lbDl").addEventListener("click", () => download(lb.list[lb.i]));
  $("#lbStage").addEventListener("click", (e) => { if (e.target !== lbImg) closeLb(); });

  document.addEventListener("keydown", (e) => {
    if (!modal.hidden && e.key === "Escape") return closeModal();
    if (!lb.open) return;
    if (e.key === "ArrowRight") go(1);
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "Escape") closeLb();
    else if (e.key.toLowerCase() === "f") toggleFav(lb.list[lb.i].id);
    else if (e.key.toLowerCase() === "d" && data.download) download(lb.list[lb.i]);
  });

  // Wischen auf dem Handy
  let tx = null, ty = null;
  lbEl.addEventListener("touchstart", (e) => { tx = e.touches[0].clientX; ty = e.touches[0].clientY; }, { passive: true });
  lbEl.addEventListener("touchend", (e) => {
    if (tx === null) return;
    const dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
    else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) closeLb();
    tx = ty = null;
  });

  // ---------- Start ----------
  updateFavUI();
  render();
  const hashId = decodeURIComponent(location.hash.slice(1));
  if (byId.has(hashId)) openLb(hashId);
})();
