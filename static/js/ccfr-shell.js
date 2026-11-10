/* Shared page behaviour: mobile menu, header shadow, language select, toasts, confirm dialog,
   password reveal. Plain JavaScript, no framework, no inline scripts (CSP-safe). Content is only
   ever written with textContent, never innerHTML. */
(function () {
  "use strict";
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ---- Header: shadow on scroll and the mobile menu ---- */
  var header = $("[data-header]");
  if (header) {
    var onScroll = function () { header.classList.toggle("is-scrolled", window.scrollY > 8); };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    var toggle = $(".nav-toggle", header), nav = $("#primary-nav");
    if (toggle && nav) {
      var setNav = function (open, focusToggle) {
        toggle.setAttribute("aria-expanded", String(open));
        nav.classList.toggle("is-open", open);
        document.body.classList.toggle("nav-open", open);
        if (open) { var first = $("a, select, button", nav); if (first) { first.focus(); } }
        if (!open && focusToggle) { toggle.focus(); }
      };
      toggle.addEventListener("click", function () { setNav(toggle.getAttribute("aria-expanded") !== "true"); });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && nav.classList.contains("is-open")) { setNav(false, true); }
      });
      window.matchMedia("(min-width: 72rem)").addEventListener("change", function () { setNav(false); });
    }
  }

  /* ---- Language select: submits Django's set_language form on change ---- */
  $$("[data-lang-select]").forEach(function (select) {
    select.addEventListener("change", function () { select.form.submit(); });
  });

  /* ---- Progress bars and rings: copy data-v into the --v custom property (CSP forbids style=""). ---- */
  $$("[data-v]").forEach(function (el) { el.style.setProperty("--v", el.getAttribute("data-v")); });

  /* ---- Toasts: server messages. They stay visible without JS; here they can be closed. ---- */
  $$("[data-toast]").forEach(function (toast) {
    var close = function () { toast.remove(); };
    var button = $("[data-toast-close]", toast);
    if (button) { button.addEventListener("click", close); }
    window.setTimeout(close, 8000);
  });

  /* ---- Password reveal: <button data-reveal-pw aria-controls="id"> ---- */
  $$("[data-reveal-pw]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("aria-controls"));
      if (!input) { return; }
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", String(show));
      btn.textContent = show ? btn.dataset.hideLabel : btn.dataset.showLabel;
    });
  });

  /* ---- Confirm dialog: data-confirm="Title" [data-confirm-body="..."] [data-confirm-yes="Label"] ----
     On a <form> it guards the submit; on a submit button it guards that button. */
  var dialog = $("#confirm-dialog");
  if (dialog && typeof dialog.showModal === "function") {
    var pending = null;
    var ask = function (source, proceed) {
      $("[data-confirm-title]", dialog).textContent = source.dataset.confirm;
      $("[data-confirm-body]", dialog).textContent = source.dataset.confirmBody || "";
      var yes = $("[data-confirm-yes]", dialog);
      if (source.dataset.confirmYes) { yes.textContent = source.dataset.confirmYes; }
      yes.classList.toggle("btn-danger", source.hasAttribute("data-confirm-danger"));
      yes.classList.toggle("btn-primary", !source.hasAttribute("data-confirm-danger"));
      pending = proceed;
      dialog.showModal();
    };
    dialog.addEventListener("close", function () {
      var proceed = pending; pending = null;
      if (dialog.returnValue === "yes" && proceed) { proceed(); }
      dialog.returnValue = "";
    });
    $$("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (form.dataset.confirmed) { return; }
        e.preventDefault();
        ask(form, function () { form.dataset.confirmed = "1"; form.requestSubmit ? form.requestSubmit() : form.submit(); });
      });
    });
    $$("button[data-confirm]").forEach(function (button) {
      button.addEventListener("click", function (e) {
        if (button.dataset.confirmed) { return; }
        e.preventDefault();
        ask(button, function () { button.dataset.confirmed = "1"; button.click(); });
      });
    });
  }
})();
