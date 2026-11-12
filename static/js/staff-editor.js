// Labels for the question editor's generated inputs (django-jsonform renders them without any).
// Each control gets an aria-label built from its field path, e.g. "options 1 text", and the
// editor re-labels whenever the form grows (add / remove / reorder rows). No inline code: CSP.
(function () {
  function labelFor(el) {
    var name = (el.getAttribute("name") || "").split("§").slice(1);
    var parts = name.map(function (p) { return /^\d+$/.test(p) ? String(Number(p) + 1) : p.replace(/_/g, " "); });
    return parts.join(" ") || "Question field";
  }
  function label(root) {
    root.querySelectorAll("input, select, textarea").forEach(function (el) {
      if (el.type === "hidden" || el.hasAttribute("data-django-jsonform")) return;
      if (!el.getAttribute("aria-label") && !el.labels.length) el.setAttribute("aria-label", labelFor(el));
    });
  }
  function start() {
    document.querySelectorAll("[data-django-jsonform-container]").forEach(function (root) {
      label(root);
      new MutationObserver(function () { label(root); }).observe(root, { childList: true, subtree: true });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
