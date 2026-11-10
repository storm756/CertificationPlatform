/* The attempt page: save status, retry when offline, the count-up timer and focus after a swap.
   htmx does the requests (it is configured without eval, see attempt.html). This file never builds
   HTML: it only sets textContent and attributes. Plain JavaScript, CSP-safe. */
(function () {
  "use strict";
  var root = document.querySelector("[data-attempt]");
  if (!root) { return; }

  /* ---- Save status: Saved / Saving / Offline ---- */
  var pill = function () { return document.getElementById("save-status"); };
  var setState = function (state) {
    var el = pill();
    if (!el) { return; }
    el.setAttribute("data-state", state);
    var text = el.querySelector("[data-pill-text]");
    if (text) { text.textContent = el.getAttribute("data-text-" + state) || ""; }
  };
  var form = function () { return document.querySelector("[data-answer-form]"); };

  /* ---- Retry with a growing delay until the answer is saved ---- */
  var retryTimer = null, delay = 2000, pendingForm = null;
  var scheduleRetry = function () {
    if (retryTimer) { return; }
    retryTimer = window.setTimeout(function () {
      retryTimer = null;
      var f = pendingForm && document.body.contains(pendingForm) ? pendingForm : form();
      if (f && window.htmx) { window.htmx.trigger(f, "change"); }
    }, delay);
    delay = Math.min(delay * 2, 30000);
  };
  var failed = function (evt) {
    var target = evt.detail && evt.detail.elt;
    if (!target || !target.matches || !target.matches("[data-answer-form]")) { return; }
    pendingForm = target;
    setState("offline");
    scheduleRetry();
  };
  document.body.addEventListener("htmx:beforeRequest", function (evt) {
    if (evt.detail.elt.matches && evt.detail.elt.matches("[data-answer-form]")) { setState("saving"); }
  });
  document.body.addEventListener("htmx:sendError", failed);
  document.body.addEventListener("htmx:timeout", failed);
  document.body.addEventListener("htmx:responseError", function (evt) {
    var status = evt.detail.xhr && evt.detail.xhr.status;
    if (status === 409) { return; } // the attempt was submitted elsewhere: the server redirects
    if (status && status < 500) { setState("saved"); return; } // a refused answer is not retried
    failed(evt);
  });
  document.body.addEventListener("htmx:afterRequest", function (evt) {
    if (evt.detail.successful && evt.detail.elt.matches && evt.detail.elt.matches("[data-answer-form]")) {
      delay = 2000; pendingForm = null;
      if (retryTimer) { window.clearTimeout(retryTimer); retryTimer = null; }
    }
  });
  window.addEventListener("online", function () { if (pendingForm) { delay = 2000; scheduleRetry(); } });
  window.addEventListener("offline", function () { if (form()) { setState("offline"); } });

  /* ---- After a question loads: move focus to its heading ---- */
  document.body.addEventListener("htmx:afterSwap", function (evt) {
    if (evt.detail.target && evt.detail.target.id === "question-panel") {
      var title = document.getElementById("q-title");
      if (title) { title.focus({ preventScroll: false }); }
    }
  });

  /* ---- Count-up timer: a guide only, never enforced ---- */
  var timer = document.querySelector("[data-timer]");
  if (timer) {
    var seconds = parseInt(root.getAttribute("data-elapsed"), 10) || 0;
    var paint = function () {
      var h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
      var two = function (n) { return (n < 10 ? "0" : "") + n; };
      timer.textContent = (h ? h + ":" : "") + two(m) + ":" + two(s);
    };
    paint();
    window.setInterval(function () { seconds += 1; paint(); }, 1000);
  }
})();
