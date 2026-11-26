/* Shared helpers: API client, DOM builder, toasts and the API-key gate. */
window.App = (() => {
  const KEY = "qrci.apiKey", NAME = "qrci.staffName";
  const getKey = () => sessionStorage.getItem(KEY) || "";
  const getName = () => localStorage.getItem(NAME) || "";

  function el(tag, attrs = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }

  async function api(path, { method = "GET", json, form, blob = false } = {}) {
    const headers = { "X-API-Key": getKey() };
    let body;
    if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
    if (form) body = form;
    let res;
    try { res = await fetch(path, { method, headers, body }); }
    catch { return { ok: false, status: 0, data: { detail: "Network error" } }; }
    if (res.status === 401) { sessionStorage.removeItem(KEY); }
    if (blob) return { ok: res.ok, status: res.status, data: res.ok ? await res.blob() : null };
    const isJson = (res.headers.get("content-type") || "").includes("json");
    return { ok: res.ok, status: res.status, data: isJson ? await res.json().catch(() => null) : null };
  }

  function toast(msg, kind = "") {
    let box = document.getElementById("toasts");
    if (!box) { box = el("div", { id: "toasts", "aria-live": "polite" }); document.body.append(box); }
    const t = el("div", { class: `toast ${kind}` }, msg);
    box.append(t);
    setTimeout(() => t.remove(), 4000);
  }

  function errorText(r) {
    const d = r && r.data;
    if (!d) return `Request failed (${r ? r.status : "?"})`;
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.detail)) return d.detail.map((x) => x.msg).join("; ");
    return d.status || "Request failed";
  }

  /* Shows the key modal until a valid key with an allowed role is entered. */
  function requireAuth({ roles, askName = false }) {
    const modal = document.getElementById("authModal");
    const form = document.getElementById("authForm");
    const keyIn = document.getElementById("authKey");
    const nameIn = document.getElementById("authName");
    const errBox = document.getElementById("authError");
    if (!askName) nameIn.closest(".field").hidden = true;
    nameIn.value = getName();

    const check = async () => {
      const r = await api("/api/v1/auth/whoami");
      return r.ok && roles.includes(r.data.role) ? r.data.role : null;
    };

    return new Promise(async (resolve) => {
      if (getKey() && (await check())) return resolve({ name: getName() });
      modal.classList.add("open");
      keyIn.focus();
      form.onsubmit = async (e) => {
        e.preventDefault();
        sessionStorage.setItem(KEY, keyIn.value.trim());
        const role = await check();
        if (!role) {
          sessionStorage.removeItem(KEY);
          errBox.textContent = "That key is not valid for this page.";
          return;
        }
        if (askName) localStorage.setItem(NAME, nameIn.value.trim() || "Gate staff");
        modal.classList.remove("open");
        resolve({ name: getName() });
      };
    });
  }

  const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const fmtDateTime = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

  return { el, api, toast, errorText, requireAuth, getKey, getName, fmtTime, fmtDateTime };
})();
