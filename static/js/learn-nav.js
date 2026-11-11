/* Catalogue search and filters, the module page's tabs and the outline toggle. Plain JavaScript,
   no inline scripts (CSP). Everything shown comes from the server-rendered page. */
(function () {
  "use strict";
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ---- Catalogue: search and filter (progress state is on each card) ---- */
  var grid = $("[data-cat-grid]");
  if (grid) {
    var search = $("[data-cat-search]"), filter = "all";
    var apply = function () {
      var q = (search.value || "").trim().toLowerCase(), shown = 0;
      $$(".mod-card", grid).forEach(function (card) {
        var ok = (filter === "all" || card.getAttribute("data-state") === filter) &&
                 (!q || (card.getAttribute("data-search") || "").indexOf(q) >= 0);
        card.hidden = !ok;
        if (ok) { shown += 1; }
      });
      var empty = $("[data-cat-empty]");
      if (empty) { empty.hidden = shown > 0; }
      var count = $("[data-cat-count]");
      if (count) { count.textContent = shown + " modules shown"; }
    };
    if (search) { search.addEventListener("input", apply); }
    $$("[data-filter]").forEach(function (button) {
      button.addEventListener("click", function () {
        filter = button.getAttribute("data-filter");
        $$("[data-filter]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
        apply();
      });
    });
  }

  /* ---- Module page: Overview / Course content / Assessments tabs ---- */
  var tabs = $$("[data-tab]");
  if (tabs.length) {
    var select = function (name, focus) {
      tabs.forEach(function (tab) {
        var on = tab.getAttribute("data-tab") === name;
        tab.setAttribute("aria-selected", String(on));
        tab.tabIndex = on ? 0 : -1;
        if (on && focus) { tab.focus(); }
      });
      ["overview", "content", "assess"].forEach(function (p) {
        var panel = document.getElementById("panel-" + p);
        if (panel) { panel.hidden = p !== name; }
      });
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", window.location.pathname + (name === "overview" ? "" : "#" + name));
      }
    };
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { select(tab.getAttribute("data-tab")); });
      tab.addEventListener("keydown", function (e) {
        var d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (d) { e.preventDefault(); select(tabs[(i + d + tabs.length) % tabs.length].getAttribute("data-tab"), true); }
      });
    });
    $$("[data-tab-link]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        select(link.getAttribute("data-tab-link"));
        var bar = $(".tabs");
        if (bar && bar.scrollIntoView) { bar.scrollIntoView(); }
      });
    });
    var hash = window.location.hash.replace("#", "");
    if (hash === "content" || hash === "assess") { select(hash); }
  }

  /* ---- Outline: collapses on small screens ---- */
  $$("[data-outline-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var nav = button.closest("[data-outline]");
      var open = !nav.classList.contains("is-open");
      nav.classList.toggle("is-open", open);
      button.setAttribute("aria-expanded", String(open));
    });
  });
})();
