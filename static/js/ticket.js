// Show event times in the visitor's local timezone (server renders UTC as a fallback).
document.querySelectorAll("time.localtime").forEach((t) => {
  const d = new Date(t.getAttribute("datetime"));
  if (!isNaN(d)) t.textContent = d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
});
