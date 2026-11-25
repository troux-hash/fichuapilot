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
      coords.textContent = "Pin set. Drag it to adjust.";
    };
    if (marker) marker.on("dragend", () => set(marker.getLatLng()));
    map.on("click", (e) => set(e.latlng));
    country?.addEventListener("change", () => { if (!marker && CITY[country.value]) map.setView(CITY[country.value], 13); });
    $("[data-locate]")?.addEventListener("click", () => {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition((p) => {
        const ll = L.latLng(p.coords.latitude, p.coords.longitude);
        map.setView(ll, 18); set(ll);
      }, () => { coords.textContent = "Location not available: tap or click the map instead."; }, { enableHighAccuracy: true, timeout: 10000 });
    });
  }
  window.addEventListener("load", initMap);

  /* ---------- Photos: shrink on the phone before upload (max 1600px, JPEG), plus an 800px card copy ---------- */
  const PHOTO_LIMIT = 3 * 1024 * 1024;       // the server's limit for one photo (partners.MAX_PHOTO_BYTES)
  const REQUEST_BUDGET = 3.5 * 1024 * 1024;  // the host refuses requests over 4.5 MB, so photos go up in batches
  function toJpeg(img, max, quality, name) {
    return new Promise((resolve) => {
      const scale = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.naturalWidth * scale); canvas.height = Math.round(img.naturalHeight * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => resolve(blob ? new File([blob], name, { type: "image/jpeg" }) : null), "image/jpeg", quality);
    });
  }
  // One decode gives both sizes. A phone that stalls gets 20 seconds; then the photo goes as it is.
  function prepare(file) {
    const none = { full: null, card: null };
    if (!file.type.startsWith("image/")) return Promise.resolve(none);
    const work = new Promise((resolve) => {
      const img = new Image();
      const url = URL.createObjectURL(file);
      const name = file.name.replace(/\.\w+$/, "") + ".jpg";
      img.onload = async () => {
        try {
          resolve({ full: await toJpeg(img, 1600, 0.82, name), card: await toJpeg(img, 800, 0.78, name) });
        } catch { resolve(none); } finally { URL.revokeObjectURL(url); }
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(none); };
      img.src = url;
    });
    return Promise.race([work, new Promise((resolve) => setTimeout(() => resolve(none), 20000))]);
  }
  // On the photos page, choosing photos uploads them straight away: no second tap.
  $$("input[type=file][data-autoupload]").forEach((input) => input.addEventListener("change", () => {
    if (input.files.length) input.form.requestSubmit();
  }));
  $$("form[data-upload]").forEach((form) => form.addEventListener("submit", async (e) => {
    const inputs = $$("input[type=file]", form).filter((i) => i.files.length);
    if (!inputs.length || !window.fetch) return;
    e.preventDefault();
    const status = $("[data-upload-status]", form) || $("[data-upload-status]");
    const button = $("button[type=submit]", form);
    const say = (text) => { if (status) status.textContent = text; };
    const stop = (text) => { say(text); if (button) button.disabled = false; };
    if (button) { button.disabled = true; }
    const photos = [];
    for (const input of inputs) {
      let i = 0;
      for (const file of input.files) {
        i += 1;
        say(`Preparing photo ${i} of ${input.files.length}…`);
        const { full, card } = await prepare(file);
        const photo = full || file;
        if (photo.size > PHOTO_LIMIT) {
          return stop(`“${file.name}” is over 3 MB and could not be resized on this device. Choose a smaller copy.`);
        }
        photos.push({ field: input.name, photo, card });
      }
    }
    // Batches under the request limit; a photo and its small copy always travel together.
    const batches = [[]];
    let size = 0;
    for (const p of photos) {
      const bytes = p.photo.size + (p.card ? p.card.size : 0);
      if (batches[batches.length - 1].length && size + bytes > REQUEST_BUDGET) { batches.push([]); size = 0; }
      batches[batches.length - 1].push(p);
      size += bytes;
    }
    let action = form.action, sent = 0;
    const onward = new URL(action, location.href).pathname.replace(/\/new$/, "/");  // where the next batch may go
    for (const [b, batch] of batches.entries()) {
      const last = b === batches.length - 1;
      const data = new FormData(form);
      for (const input of inputs) data.delete(input.name);
      data.delete("thumbs");
      for (const p of batch) {
        data.append(p.field, p.photo);
        data.append("thumbs", p.card || "");  // an empty entry keeps photos and their small copies in step
      }
      if (!last) data.set("stay", "1");
      say(batches.length > 1 ? `Uploading photos ${sent + 1}–${sent + batch.length} of ${photos.length}…` : "Uploading…");
      let resp;
      try {
        resp = await fetch(action, { method: "POST", body: data, credentials: "same-origin" });
      } catch {
        return stop(sent ? `${sent} of ${photos.length} photos are in. Check your connection, then add the rest.`
                         : "Upload failed. Check your connection and try again.");
      }
      sent += batch.length;
      if (!last && resp.redirected && new URL(resp.url).pathname.startsWith(onward)) { action = resp.url; continue; }
      if (resp.redirected) { window.location = resp.url; return; }
      if (resp.status === 413) return stop("Those photos are too large to send together. Choose fewer at a time.");
      document.open(); document.write(await resp.text()); document.close();
      return;
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

  /* ---------- Calendar: pick a day, pick a second day for a range ---------- */
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
    // On phones the form sits under the calendar: stay on the calendar until the range is picked.
    const stacked = () => window.matchMedia("(max-width: 1179px)").matches;
    const toForm = () => { if (stacked()) calForm.scrollIntoView({ behavior: "smooth", block: "start" }); };
    const hint = $("[data-cal-hint]");
    const say = (first) => {
      if (!hint) return;
      hint.textContent = "";
      if (!first) { hint.textContent = "Range picked. Set the price or rooms below, then save."; return; }
      hint.append(`${label(a)} picked. Pick the last night to change a range, or `);
      if (stacked()) {
        const go = document.createElement("button");
        go.type = "button"; go.className = "link-button"; go.textContent = "change just this night";
        go.addEventListener("click", toForm);
        hint.append(go, ".");
      } else hint.append("change just this night in the form.");
    };
    days.forEach((d) => d.addEventListener("click", () => {
      const first = !a || b;
      if (first) { a = d.dataset.date; b = null;
        // Empty boxes keep each night's current value; the hint shows what the first night has now.
        price.value = ""; units.value = "";
        price.placeholder = d.dataset.price ? `Now $${d.dataset.price}: leave empty to keep` : "Keep current";
        units.placeholder = d.dataset.units ? `Now ${d.dataset.units}: leave empty to keep` : "Keep current";
        closed.checked = !!d.dataset.closed;
        price.dispatchEvent(new Event("input"));
      } else { b = d.dataset.date; }
      paint();
      say(first);
      if (!first) toForm();
    }));
  }
})();
