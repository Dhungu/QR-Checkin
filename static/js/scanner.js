(() => {
  const { el, api, toast, requireAuth, getName, fmtTime } = App;
  const $ = (id) => document.getElementById(id);
  const counters = { ok: 0, dup: 0, bad: 0 };
  let scanner = null, cameras = [], camIndex = 0, running = false, busy = false, muted = false;
  let lastToken = "", lastAt = 0;

  /* ---- audio + haptics (no asset files needed) ---- */
  let audio;
  function beep(freqs, dur = 0.12, type = "sine") {
    if (muted) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      let t = audio.currentTime;
      for (const f of freqs) {
        const o = audio.createOscillator(), g = audio.createGain();
        o.type = type; o.frequency.value = f; o.connect(g); g.connect(audio.destination);
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        o.start(t); o.stop(t + dur + 0.02); t += dur;
      }
    } catch { /* audio blocked: visual feedback still works */ }
  }
  const buzz = (p) => navigator.vibrate && navigator.vibrate(p);

  /* ---- result rendering ---- */
  const KIND = {
    SUCCESS: { cls: "ok", icon: "✓", title: "Admitted", snd: () => { beep([660, 880]); buzz(80); } },
    ALREADY_CHECKED_IN: { cls: "dup", icon: "!", title: "Already checked in", snd: () => { beep([300, 300], 0.16, "square"); buzz([60, 40, 60]); } },
    INVALID_TICKET: { cls: "bad", icon: "✕", title: "Invalid ticket", snd: () => { beep([200], 0.4, "sawtooth"); buzz(300); } },
    TICKET_REVOKED: { cls: "bad", icon: "✕", title: "Ticket revoked", snd: () => { beep([200], 0.4, "sawtooth"); buzz(300); } },
    OUTSIDE_EVENT_WINDOW: { cls: "bad", icon: "⏱", title: "Outside event hours", snd: () => { beep([240, 200], 0.2, "sawtooth"); buzz(200); } },
    NO_QR_FOUND: { cls: "bad", icon: "?", title: "No QR code found", snd: () => { beep([240], 0.3, "sawtooth"); buzz(200); } },
  };

  function describe(data) {
    const who = data.attendee ? `${data.attendee.full_name} · ${data.attendee.event_name}` : "";
    switch (data.status) {
      case "SUCCESS": return who;
      case "ALREADY_CHECKED_IN":
        return `${who ? who + " — " : ""}first scanned ${data.checked_in_at ? fmtTime(data.checked_in_at) : "earlier"}${data.scanned_by ? " by " + data.scanned_by : ""}`;
      case "INVALID_TICKET": return "This code is not a ticket issued by this system.";
      case "TICKET_REVOKED": return `${who} — this ticket was cancelled.`;
      case "OUTSIDE_EVENT_WINDOW": return `${who} — doors open ${new Date(data.event_start).toLocaleString()}.`;
      case "NO_QR_FOUND": return "Try a sharper, closer photo of the code.";
      default: return "";
    }
  }

  function show(data) {
    const k = KIND[data.status] || KIND.INVALID_TICKET;
    const box = $("result");
    box.className = `result ${k.cls} pop`;
    $("resIcon").textContent = k.icon;
    $("resTitle").textContent = data.attendee && data.status === "SUCCESS" ? data.attendee.full_name : k.title;
    $("resText").textContent = data.status === "SUCCESS" ? `${k.title} · ${describe(data)}` : describe(data);
    k.snd();
    counters[k.cls === "ok" ? "ok" : k.cls === "dup" ? "dup" : "bad"]++;
    $("cOk").textContent = counters.ok; $("cDup").textContent = counters.dup; $("cBad").textContent = counters.bad;
    $("feedEmpty").style.display = "none";
    const name = data.attendee ? data.attendee.full_name : k.title;
    $("feed").prepend(el("li", {}, el("span", { class: `dot ${k.cls}` }),
      el("div", { class: "who" }, el("b", {}, name), el("small", {}, k.title)),
      el("small", {}, fmtTime(new Date().toISOString()))));
    setTimeout(() => box.classList.remove("pop"), 300);
  }

  /* ---- check-in calls ---- */
  async function submitToken(token) {
    const r = await api("/api/v1/check-in", { method: "POST", json: { ticket_token: token, scanned_by: getName() || "Gate staff" } });
    return handle(r);
  }
  function handle(r) {
    if (r.status === 401) { toast("Session expired — reload and sign in again.", "bad"); return; }
    if (r.status === 429) { toast("Too many scans — slow down for a moment.", "bad"); return; }
    if (r.data && r.data.status) show(r.data);
    else toast(App.errorText(r), "bad");
  }

  async function onScan(text) {
    const now = Date.now();
    if (busy || (text === lastToken && now - lastAt < 4000)) return;
    busy = true; lastToken = text; lastAt = now;
    await submitToken(text.trim());
    setTimeout(() => { busy = false; }, 1200);
  }

  /* ---- camera ---- */
  async function startCamera() {
    try {
      scanner = scanner || new Html5Qrcode("reader", { verbose: false });
      cameras = cameras.length ? cameras : await Html5Qrcode.getCameras();
      const cfg = { fps: 10, qrbox: (w, h) => { const s = Math.floor(Math.min(w, h) * 0.7); return { width: s, height: s }; } };
      const source = cameras.length > 1 && camIndex ? cameras[camIndex].id : { facingMode: "environment" };
      await scanner.start(source, cfg, onScan, () => {});
      running = true;
      $("viewer").classList.add("live");
      $("startBtn").textContent = "Stop camera";
      $("switchBtn").hidden = cameras.length < 2;
    } catch (e) {
      toast("Could not start the camera. Check permissions (HTTPS or localhost required).", "bad");
    }
  }
  async function stopCamera() {
    if (scanner && running) { await scanner.stop().catch(() => {}); }
    running = false;
    $("viewer").classList.remove("live");
    $("startBtn").textContent = "Start camera";
  }

  $("startBtn").onclick = () => (running ? stopCamera() : startCamera());
  $("switchBtn").onclick = async () => { camIndex = (camIndex + 1) % cameras.length; await stopCamera(); await startCamera(); };
  $("muteBtn").onclick = (e) => { muted = !muted; e.currentTarget.textContent = muted ? "🔇 Sound off" : "🔊 Sound on"; e.currentTarget.setAttribute("aria-pressed", muted); };
  $("uploadBtn").onclick = () => $("fileInput").click();
  $("clearBtn").onclick = () => { Object.assign(counters, { ok: 0, dup: 0, bad: 0 }); $("cOk").textContent = $("cDup").textContent = $("cBad").textContent = 0; $("feed").querySelectorAll("li:not(#feedEmpty)").forEach((n) => n.remove()); $("feedEmpty").style.display = "block"; };

  $("fileInput").onchange = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("scanned_by", getName() || "Gate staff");
    handle(await api("/api/v1/check-in/scan-image", { method: "POST", form }));
  };
  $("manualForm").onsubmit = async (e) => {
    e.preventDefault();
    const v = $("manualToken").value.trim();
    if (!v) return;
    await submitToken(v);
    $("manualToken").value = "";
  };

  window.addEventListener("pagehide", () => { if (running) scanner.stop().catch(() => {}); });

  requireAuth({ roles: ["staff", "admin"], askName: true }).then(() => {
    const who = $("who"); who.hidden = false; who.textContent = getName() || "Gate staff";
  });
})();
