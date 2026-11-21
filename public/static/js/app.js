/* Fichua progressive enhancement. Every page works without this file; JS makes it instant. */
(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const addDays = (s, n) => { const d = new Date(s + "T12:00:00"); d.setDate(d.getDate() + n); return iso(d); };
  const store = {
    get(k, fallback) { try { return JSON.parse(localStorage.getItem(k)) ?? fallback; } catch { return fallback; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  // Broken image → placeholder (works for images added later too).
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (img.tagName === "IMG" && !img.dataset.fallback) {
      img.dataset.fallback = "1";
      img.src = "/static/img/placeholder.svg";
    }
  }, true);

  // Keep check-out after check-in in every date pair.
  $$("form").forEach((form) => {
    const ci = $("[data-check-in]", form), co = $("[data-check-out]", form);
    if (!ci || !co) return;
    const sync = () => {
      if (!ci.value) return;
      co.min = addDays(ci.value, 1);
      if (!co.value || co.value <= ci.value) co.value = addDays(ci.value, 1);
    };
    ci.addEventListener("change", sync);
    sync();
  });

  // Date preset chips: one tap fills both dates.
  $$("[data-preset]").forEach((chip) => chip.addEventListener("click", () => {
    const form = chip.closest("form");
    $("[data-check-in]", form).value = chip.dataset.in;
    $("[data-check-out]", form).value = chip.dataset.out;
    $$("[data-preset]", form).forEach((c) => c.classList.toggle("is-active", c === chip));
  }));

  // Guest stepper.
  $$("[data-stepper]").forEach((s) => {
    const input = $("input", s);
    $$("[data-step]", s).forEach((b) => b.addEventListener("click", () => {
      const v = Math.min(+input.max || 12, Math.max(+input.min || 1, (+input.value || 1) + +b.dataset.step));
      input.value = v;
    }));
  });

  // Recent searches: saved on submit, shown as one-tap chips on the home page.
  const RECENT = "fichua.recent";
  $$("[data-search]").forEach((form) => form.addEventListener("submit", () => {
    const data = Object.fromEntries(new FormData(form));
    if (!data.destination) return;
    const list = store.get(RECENT, []).filter((r) => r.destination.toLowerCase() !== data.destination.toLowerCase());
    store.set(RECENT, [data, ...list].slice(0, 4));
  }));
  const recentBox = $("[data-recent]");
  if (recentBox) {
    const today = iso(new Date());
    const items = store.get(RECENT, []).filter((r) => r.check_in >= today);
    if (items.length) {
      const list = $("[data-recent-list]", recentBox);
      items.forEach((r) => {
        const a = document.createElement("a");
        a.className = "chip";
        a.href = "/search?" + new URLSearchParams(r);
        const fmt = (s) => new Date(s + "T12:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
        a.textContent = `${r.destination} · ${fmt(r.check_in)}–${fmt(r.check_out)} · ${r.guests}`;
        list.appendChild(a);
      });
      recentBox.classList.add("is-visible");
    }
  }

  // Phone results: tap the summary pill to edit the search.
  $$("[data-toggle-search]").forEach((btn) => btn.addEventListener("click", () => {
    const panel = $("[data-search-panel]");
    const open = panel.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open);
    if (open) $("input[name=destination]", panel)?.focus();
  }));

  // Filters: instant on laptop, bottom sheet on phone/tablet.
  const filterForm = $("[data-filter-form]");
  if (filterForm) {
    const panel = $("[data-filters]"), scrim = $("[data-scrim]");
    const wide = window.matchMedia("(min-width: 1080px)");
    const range = $("[data-range]", filterForm), rangeLabel = $("[data-range-label]");
    const open = (on) => { panel.classList.toggle("is-open", on); scrim.classList.toggle("is-open", on); document.body.style.overflow = on ? "hidden" : ""; };
    const submit = () => filterForm.requestSubmit();

    filterForm.addEventListener("submit", () => {
      // An untouched price slider isn't a filter — don't put it in the URL.
      if (range && range.value === range.max) range.disabled = true;
    });
    range?.addEventListener("input", () => { rangeLabel.textContent = "$" + Number(range.value).toLocaleString(); });
    filterForm.addEventListener("change", () => { if (wide.matches) submit(); });
    $("[data-sort]")?.addEventListener("change", submit);
    $("[data-open-filters]")?.addEventListener("click", () => open(true));
    $("[data-close-filters]")?.addEventListener("click", () => open(false));
    scrim?.addEventListener("click", () => open(false));
  }

  // A field's error goes away as soon as the guest starts fixing it; its hint comes back.
  $$(".field.has-error").forEach((field) => {
    const input = $("input, textarea, select", field);
    input?.addEventListener("input", () => {
      field.classList.remove("has-error");
      $(".error", field)?.remove();
      const hint = $(".hint", field);
      if (hint) { hint.hidden = false; input.setAttribute("aria-describedby", hint.id); }
      else input.removeAttribute("aria-describedby");
      input.removeAttribute("aria-invalid");
    }, { once: true });
  });

  // Confirm destructive actions; prevent double submits.
  $$("form[data-confirm]").forEach((f) => f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
  $$("[data-checkout]").forEach((f) => f.addEventListener("submit", () => {
    const btn = $("[data-submit]", f);
    if (btn) setTimeout(() => { btn.disabled = true; btn.textContent = "Opening secure payment…"; }, 0);
  }));

  // Filter dropdowns (admin finance) apply as soon as they change.
  $$("select[data-autosubmit]").forEach((s) => s.addEventListener("change", () => s.form.requestSubmit()));

  // Tap reference to copy.
  $$("[data-copy]").forEach((el) => {
    el.style.cursor = "copy";
    el.title = "Tap to copy";
    el.addEventListener("click", () => navigator.clipboard?.writeText(el.dataset.copy).then(() => {
      const t = el.textContent; el.textContent = "Copied ✓"; setTimeout(() => (el.textContent = t), 1200);
    }));
  });

  // Admin upload drop zone label.
  $$("[data-dropzone]").forEach((z) => {
    const input = $("input[type=file]", z), label = $("[data-file-label]", z);
    input.addEventListener("change", () => { if (input.files[0]) label.textContent = input.files[0].name; });
    ["dragenter", "dragover"].forEach((ev) => z.addEventListener(ev, () => z.classList.add("is-drag")));
    ["dragleave", "drop"].forEach((ev) => z.addEventListener(ev, () => z.classList.remove("is-drag")));
  });

  // Hotel page: hide the "See rooms" bar while the rooms are on screen, so it never covers Reserve.
  const cta = $(".sticky-cta"), roomList = document.getElementById("rooms");
  if (cta && roomList && "IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => cta.classList.toggle("is-hidden", entry.isIntersecting)).observe(roomList);
  }
})();
