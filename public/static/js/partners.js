/* Fichua Partners: map pin, photo compression, local-currency previews, calendar selection.
   Every form still works without JavaScript; this makes it faster and mobile-friendly. */
(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const CITY = { "Rwanda": [-1.9441, 30.0619], "Benin": [6.3703, 2.3912], "Côte d'Ivoire": [5.3600, -4.0083] };

  /* ---------- Map pin (Leaflet + OpenStreetMap, loaded only on the hotel details page) ---------- */
  function initMap() {
    const el = $("[data-map]");
    if (!el || !window.L) return;
    const latIn = $("input[data-lat]"), lngIn = $("input[data-lng]"), coords = $("[data-coords]"), country = $("[data-country]");
    const has = el.dataset.lat !== "" && el.dataset.lng !== "";
    const start = has ? [parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)] : (CITY[country?.value] || CITY.Rwanda);
    const map = L.map(el, { scrollWheelZoom: false }).setView(start, has ? 17 : 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    let marker = has ? L.marker(start, { draggable: true }).addTo(map) : null;
    const set = (latlng) => {
      if (!marker) { marker = L.marker(latlng, { draggable: true }).addTo(map); marker.on("dragend", () => set(marker.getLatLng())); }
      marker.setLatLng(latlng);
      latIn.value = latlng.lat.toFixed(6); lngIn.value = latlng.lng.toFixed(6);
      coords.textContent = `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
    };
    if (marker) marker.on("dragend", () => set(marker.getLatLng()));
    map.on("click", (e) => set(e.latlng));
    country?.addEventListener("change", () => { if (!marker && CITY[country.value]) map.setView(CITY[country.value], 13); });
    $("[data-locate]")?.addEventListener("click", () => {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition((p) => {
        const ll = L.latLng(p.coords.latitude, p.coords.longitude);
        map.setView(ll, 18); set(ll);
      }, () => { coords.textContent = "Location not available: click the map instead."; }, { enableHighAccuracy: true, timeout: 10000 });
    });
  }
  window.addEventListener("load", initMap);

  /* ---------- Photos: shrink on the phone before upload (max 1600px, JPEG) ---------- */
  function shrink(file) {
    return new Promise((resolve) => {
      if (!file.type.startsWith("image/")) return resolve(file);
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * scale); canvas.height = Math.round(img.height * scale);
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        canvas.toBlob((blob) => resolve(blob ? new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file), "image/jpeg", 0.82);
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
      img.src = url;
    });
  }
  $$("form[data-upload]").forEach((form) => form.addEventListener("submit", async (e) => {
    const inputs = $$("input[type=file]", form).filter((i) => i.files.length);
    if (!inputs.length || !window.fetch) return;
    e.preventDefault();
    const status = $("[data-upload-status]", form) || $("[data-upload-status]");
    const button = $("button[type=submit]", form);
    if (button) { button.disabled = true; }
    const data = new FormData(form);
    for (const input of inputs) {
      data.delete(input.name);
      let i = 0;
      for (const file of input.files) {
        i += 1;
        if (status) status.textContent = `Preparing photo ${i} of ${input.files.length}…`;
        data.append(input.name, await shrink(file));
      }
    }
    if (status) status.textContent = "Uploading…";
    try {
      const resp = await fetch(form.action, { method: "POST", body: data, credentials: "same-origin" });
      if (resp.redirected) { window.location = resp.url; return; }
      document.open(); document.write(await resp.text()); document.close();
    } catch {
      if (status) status.textContent = "Upload failed. Check your connection and try again.";
      if (button) button.disabled = false;
    }
  }));

  /* ---------- USD inputs: show the local amount as the hotel types ---------- */
  const rate = window.FICHUA_RATE || 0, label = window.FICHUA_LOCAL || "";
  const fmt = (n) => label === "FCFA" ? Math.round(n / 100) * 100 : Math.round(n / 100) * 100;
  $$("[data-money]").forEach((input) => {
    const out = $(`[data-local-for="${input.id}"]`);
    if (!out || !rate) return;
    const update = () => {
      const v = parseFloat((input.value || "").replace(/,/g, ""));
      out.textContent = v > 0 ? `≈ ${fmt(v * rate).toLocaleString(label === "FCFA" ? "fr-FR" : "en-US")} ${label}` : "";
    };
    input.addEventListener("input", update); update();
  });

  /* ---------- Calendar: click a day, click a second day for a range ---------- */
  const cal = $("[data-calendar]"), calForm = $("[data-cal-form]");
  if (cal && calForm) {
    const days = $$(".cal__day", cal).filter((d) => !d.disabled);
    const from = $("[data-from]", calForm), to = $("[data-to]", calForm), title = $("[data-cal-title]", calForm);
    const price = $("[data-price]", calForm), units = $("[data-units]", calForm), closed = $("[data-closed]", calForm);
    const note = $("[data-booked-note]", calForm);
    let a = null, b = null;
    const label = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(document.documentElement.lang || "en-GB", { weekday: "short", day: "numeric", month: "short" });
    const paint = () => {
      const lo = a && b ? (a < b ? a : b) : a, hi = a && b ? (a < b ? b : a) : a;
      let booked = 0;
      days.forEach((d) => {
        const on = lo && d.dataset.date >= lo && d.dataset.date <= hi;
        d.classList.toggle("is-selected", !!on);
        d.setAttribute("aria-pressed", on ? "true" : "false");
        if (on) booked = Math.max(booked, parseInt(d.dataset.booked || "0", 10));
      });
      if (!lo) return;
      from.value = lo; to.value = hi;
      const nights = Math.round((new Date(hi) - new Date(lo)) / 86400000) + 1;
      title.textContent = lo === hi ? label(lo) : `${label(lo)} – ${label(hi)} · ${nights} nights`;
      if (note) note.textContent = booked ? `Up to ${booked} room${booked > 1 ? "s are" : " is"} already booked on these dates, so you can't sell fewer.` : "No bookings on these dates yet.";
      if (units) units.min = booked;
    };
    days.forEach((d) => d.addEventListener("click", () => {
      if (!a || b) { a = d.dataset.date; b = null;
        // Empty boxes keep each night's current value; the hint shows what the first night has now.
        price.value = ""; units.value = "";
        price.placeholder = d.dataset.price ? `Now $${d.dataset.price}: leave empty to keep` : "Keep current";
        units.placeholder = d.dataset.units ? `Now ${d.dataset.units}: leave empty to keep` : "Keep current";
        closed.checked = !!d.dataset.closed;
        price.dispatchEvent(new Event("input"));
      } else { b = d.dataset.date; }
      paint();
      if (window.matchMedia("(max-width: 1179px)").matches) calForm.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
  }
})();
