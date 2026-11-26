(() => {
  const { el, api, toast, errorText, requireAuth, fmtDateTime, fmtTime } = App;
  const $ = (id) => document.getElementById(id);
  const PAGE = 25;
  let events = [], current = null, offset = 0, query = "", timer = null, searchDebounce = null;

  const toLocalInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

  /* ---------------------------------------------------------------- events */
  async function loadEvents(selectId) {
    const r = await api("/api/v1/events");
    if (!r.ok) return toast(errorText(r), "bad");
    events = r.data;
    const list = $("eventList");
    list.replaceChildren();
    if (!events.length) { list.append(el("li", { class: "empty" }, "No events yet.")); }
    for (const ev of events) {
      list.append(el("li", {}, el("button", { type: "button", class: current && current.id === ev.id ? "active" : "", onclick: () => select(ev) },
        el("b", {}, ev.name), el("small", {}, fmtDateTime(ev.start_time)))));
    }
    $("noEvent").hidden = events.length > 0;
    $("eventPane").hidden = !events.length;
    const pick = events.find((e) => e.id === selectId) || (current && events.find((e) => e.id === current.id)) || events[0];
    if (pick) select(pick);
  }

  function select(ev) {
    current = ev; offset = 0; query = ""; $("search").value = "";
    $("evName").textContent = ev.name;
    $("evWhen").textContent = `${fmtDateTime(ev.start_time)} → ${fmtDateTime(ev.end_time)}`;
    document.querySelectorAll("#eventList button").forEach((b) => b.classList.toggle("active", b.querySelector("b").textContent === ev.name));
    refreshAll();
    clearInterval(timer);
    timer = setInterval(() => { if (!document.hidden) { loadStats(); loadActivity(); } }, 4000);
  }

  const refreshAll = () => Promise.all([loadStats(), loadActivity(), loadAttendees()]);

  async function loadStats() {
    if (!current) return;
    const id = current.id;
    const r = await api(`/api/v1/events/${id}/stats`);
    if (!r.ok || id !== current.id) return;
    const s = r.data;
    $("sTotal").textContent = s.total; $("sIn").textContent = s.checked_in;
    $("sPend").textContent = s.pending; $("sRev").textContent = s.revoked;
    const pct = Math.round(s.check_in_rate * 100);
    $("sPct").textContent = `${pct}% of ${s.total - s.revoked} admissible`;
    $("bar").style.width = `${pct}%`;
  }

  async function loadActivity() {
    if (!current) return;
    const id = current.id;
    const r = await api(`/api/v1/events/${id}/activity?limit=12`);
    if (!r.ok || id !== current.id) return;
    const ul = $("activity");
    ul.replaceChildren();
    if (!r.data.length) ul.append(el("li", { class: "empty", style: "display:block" }, "No check-ins yet."));
    for (const a of r.data) {
      ul.append(el("li", {}, el("span", { class: "dot ok" }),
        el("div", { class: "who" }, el("b", {}, a.full_name), el("small", {}, `by ${a.scanned_by}`)),
        el("small", {}, fmtTime(a.scanned_at))));
    }
  }

  /* ------------------------------------------------------------- attendees */
  const STATUS = { registered: ["Registered", "brand"], checked_in: ["Checked in", "ok"], revoked: ["Revoked", "bad"] };

  async function loadAttendees() {
    if (!current) return;
    const id = current.id;
    const qs = new URLSearchParams({ limit: PAGE, offset });
    if (query) qs.set("q", query);
    const r = await api(`/api/v1/events/${id}/attendees?${qs}`);
    if (!r.ok || id !== current.id) return;
    const { items, total } = r.data;
    $("attCount").textContent = `(${total})`;
    $("attEmpty").hidden = items.length > 0;
    $("pager").hidden = total <= PAGE;
    $("pageInfo").textContent = `${Math.min(offset + 1, total)}–${Math.min(offset + PAGE, total)} of ${total}`;
    $("prevBtn").disabled = offset === 0; $("nextBtn").disabled = offset + PAGE >= total;
    const body = $("attBody");
    body.replaceChildren();
    for (const a of items) {
      const [label, cls] = STATUS[a.status] || [a.status, ""];
      body.append(el("tr", {},
        el("td", {}, el("b", {}, a.full_name), el("br"), el("small", { class: "muted" }, a.email)),
        el("td", {}, el("span", { class: `badge ${cls}` }, label)),
        el("td", {}, el("div", { class: "actions" },
          el("button", { class: "btn sm", type: "button", title: "Copy attendee ticket link", onclick: () => copyLink(a) }, "Link"),
          el("button", { class: "btn sm", type: "button", title: "Download QR code", onclick: () => downloadQr(a) }, "QR"),
          a.status !== "revoked" && el("button", { class: "btn sm danger", type: "button", onclick: () => revoke(a) }, "Revoke")))));
    }
  }

  async function copyLink(a) {
    const url = `${location.origin}/ticket/${a.ticket_token}`;
    try { await navigator.clipboard.writeText(url); toast("Ticket link copied", "ok"); }
    catch { window.prompt("Copy ticket link:", url); }
  }

  async function downloadQr(a) {
    const r = await api(`/api/v1/attendees/${a.id}/qr`, { blob: true });
    if (!r.ok) return toast("Could not load QR", "bad");
    const url = URL.createObjectURL(r.data);
    const link = el("a", { href: url, download: `ticket-${a.full_name.replace(/\W+/g, "-").toLowerCase()}.png` });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function revoke(a) {
    if (!confirm(`Revoke ${a.full_name}'s ticket? It will stop working immediately.`)) return;
    const r = await api(`/api/v1/attendees/${a.id}/revoke`, { method: "POST" });
    if (!r.ok) return toast(errorText(r), "bad");
    toast("Ticket revoked", "ok");
    refreshAll();
  }

  $("attForm").onsubmit = async (e) => {
    e.preventDefault();
    const r = await api(`/api/v1/events/${current.id}/attendees`, { method: "POST", json: { full_name: $("aName").value, email: $("aEmail").value } });
    if (!r.ok) return toast(errorText(r), "bad");
    toast(`Registered ${r.data.full_name}`, "ok");
    $("aName").value = ""; $("aEmail").value = "";
    refreshAll();
  };

  $("csvFile").onchange = async (e) => {
    const file = e.target.files[0]; e.target.value = "";
    if (!file) return;
    const form = new FormData(); form.append("file", file);
    const r = await api(`/api/v1/events/${current.id}/attendees/import`, { method: "POST", form });
    if (!r.ok) return toast(errorText(r), "bad");
    const { created, skipped, errors } = r.data;
    toast(`Imported ${created}, skipped ${skipped}${errors.length ? `, ${errors.length} errors` : ""}`, errors.length ? "" : "ok");
    refreshAll();
  };

  $("search").oninput = (e) => { clearTimeout(searchDebounce); searchDebounce = setTimeout(() => { query = e.target.value.trim(); offset = 0; loadAttendees(); }, 250); };
  $("prevBtn").onclick = () => { offset = Math.max(0, offset - PAGE); loadAttendees(); };
  $("nextBtn").onclick = () => { offset += PAGE; loadAttendees(); };

  /* ------------------------------------------------------------ new event */
  const modal = $("eventModal");
  $("newEventBtn").onclick = () => {
    const start = new Date(); start.setMinutes(0, 0, 0); start.setHours(start.getHours() + 1);
    $("eStart").value = toLocalInput(start);
    $("eEnd").value = toLocalInput(new Date(start.getTime() + 3 * 3600000));
    $("eErr").textContent = ""; modal.classList.add("open"); $("eName").focus();
  };
  $("evCancel").onclick = () => modal.classList.remove("open");
  $("eventForm").onsubmit = async (e) => {
    e.preventDefault();
    const r = await api("/api/v1/events", { method: "POST", json: {
      name: $("eName").value, start_time: new Date($("eStart").value).toISOString(), end_time: new Date($("eEnd").value).toISOString() } });
    if (!r.ok) { $("eErr").textContent = errorText(r); return; }
    modal.classList.remove("open"); $("eName").value = "";
    toast("Event created", "ok");
    loadEvents(r.data.id);
  };

  requireAuth({ roles: ["admin"] }).then(() => loadEvents());
})();
