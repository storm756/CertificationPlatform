/* Landing page: the stage tabs, the first-response check tabs and "one FAQ open at a time".
   Every panel is already in the page (server-rendered, translated); this only shows one at a time.
   No inline script and no HTML written from strings (CSP-safe). Without JavaScript, only the first panel shows, so the
   page still reads (the other panels are `hidden` until a tab is chosen). */
(function () {
  "use strict";
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  $$("[data-tabs]").forEach(function (group) {
    var tabs = $$("[data-tab]", group);
    var panels = $$("[data-panel]", group);
    var links = $$(".stage-link", group);
    function select(index) {
      tabs.forEach(function (tab, j) {
        tab.setAttribute("aria-selected", String(j === index));
        tab.tabIndex = j === index ? 0 : -1;
        tab.classList.toggle("is-done", tab.classList.contains("stage") && j < index);
      });
      panels.forEach(function (panel, j) { panel.hidden = j !== index; });
      links.forEach(function (link, j) { link.classList.toggle("is-lit", j < index); });
    }
    tabs.forEach(function (tab, index) {
      tab.addEventListener("click", function () { select(index); });
      tab.addEventListener("keydown", function (e) {
        var step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        var target = null;
        if (step) { target = (index + step + tabs.length) % tabs.length; }
        else if (e.key === "Home") { target = 0; }
        else if (e.key === "End") { target = tabs.length - 1; }
        if (target === null) { return; }
        e.preventDefault();
        select(target);
        tabs[target].focus();
      });
    });
  });

  var faqs = $$("[data-faq] details");
  faqs.forEach(function (d) {
    d.addEventListener("toggle", function () {
      if (d.open) { faqs.forEach(function (o) { if (o !== d) { o.open = false; } }); }
    });
  });
})();
