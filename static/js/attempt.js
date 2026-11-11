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
  /* ---- Saving answers: an outbox kept per question ----
     Each change is copied (with the question number it belongs to) into the outbox at once, so it
     never depends on which question is on screen later. It is sent after a short pause, or at
     once when the learner navigates away. A failed save stays in the outbox and is retried for
     the ORIGINAL question with a growing delay. "Saved" is shown only when the server accepted
     every answer; an answer the server refuses is shown as "Not saved", never as saved. */
  var outbox = {};   // question number -> { body, version, sentVersion, inflight, failing, delay, timer }
  var refused = {};  // question number -> true (the server said no; not retried)
  var expired = false; // the session ended: answers wait in this page until the learner signs in again
  var DEBOUNCE = 150, FIRST_RETRY = 2000, LAST_RETRY = 30000, TIMEOUT = 15000;

  var pending = function () { return Object.keys(outbox).length > 0; };
  var currentPosition = function () {
    var f = document.querySelector("[data-answer-form]");
    return f && f.elements.position ? f.elements.position.value : null;
  };
  var notice = function () { return document.getElementById("session-notice"); };
  var refreshPill = function () {
    var keys = Object.keys(outbox);
    var box = notice();
    if (box) { box.hidden = !expired; }
    if (expired && keys.length) { setState("signin"); return; }
    if (keys.length) {
      setState(keys.some(function (k) { return outbox[k].failing; }) ? "offline" : "saving");
    } else {
      setState(Object.keys(refused).length ? "error" : "saved");
    }
  };

  /* What the server sends back for a save is the pill and the refreshed question map. It is
     applied only while that question is still the one on screen (the map marks the current
     question). */
  var applyResponse = function (position, html) {
    if (String(position) !== String(currentPosition()) || !window.htmx || !window.htmx.swap) { return; }
    window.htmx.swap("#save-status", html, { swapStyle: "outerHTML" });
  };

  var leaving = false; // keepalive lets a request outlive the page, so it is used only while leaving
  var send, fail;
  var schedule = function (entry, ms) {
    if (entry.timer) { window.clearTimeout(entry.timer); }
    entry.timer = window.setTimeout(function () { entry.timer = null; send(entry); }, ms);
  };
  fail = function (entry) {
    entry.inflight = false;
    entry.failing = true;
    schedule(entry, entry.delay);
    entry.delay = Math.min(entry.delay * 2, LAST_RETRY);
    refreshPill();
  };
  var sessionEnded = function (entry) {
    // The answer endpoint answered with the sign-in page (after a redirect). Nothing was saved.
    // Keep the answer in memory, do not retry blindly, and tell the learner.
    entry.inflight = false;
    entry.failing = true;
    if (entry.timer) { window.clearTimeout(entry.timer); entry.timer = null; }
    expired = true;
    refreshPill();
  };
  var finished = function (entry, response, html) {
    entry.inflight = false;
    if (response.redirected || /\/accounts\/login\//.test(response.url || "")) { sessionEnded(entry); return; }
    if (response.ok && response.headers.get("X-Answer-Saved") !== "1") { fail(entry); return; } // not confirmed
    if (response.ok) {
      expired = false;
      entry.failing = false;
      entry.delay = FIRST_RETRY;
      if (entry.version !== entry.sentVersion) { send(entry); refreshPill(); return; } // changed meanwhile
      delete outbox[entry.position];
      applyResponse(entry.position, html);
      refreshPill();
      document.dispatchEvent(new CustomEvent("ccfr:saved", { detail: { position: entry.position } }));
      return;
    }
    if (response.status === 409) { // the attempt was submitted elsewhere
      delete outbox[entry.position];
      var to = response.headers.get("HX-Redirect");
      if (to) { window.location.assign(to); }
      return;
    }
    if (response.status >= 500 || response.status === 408 || response.status === 429) { fail(entry); return; }
    delete outbox[entry.position]; // refused (400, 403 ...): retrying cannot help, and it is not saved
    refused[entry.position] = true;
    refreshPill();
  };
  /* Signing in again changes the CSRF token, so a waiting answer uses the token in the cookie now,
     not the one this page was loaded with. */
  var csrfToken = function (entry) {
    var m = /(?:^|; )csrftoken=([^;]+)/.exec(document.cookie || "");
    return m ? decodeURIComponent(m[1]) : entry.csrf;
  };
  send = function (entry) {
    if (entry.inflight) { return; }
    entry.inflight = true;
    entry.sentVersion = entry.version;
    var controller = window.AbortController ? new window.AbortController() : null;
    var timeout = window.setTimeout(function () { if (controller) { controller.abort(); } }, TIMEOUT);
    window.fetch(entry.path, {
      method: "POST", body: entry.body, credentials: "same-origin", keepalive: leaving,
      headers: { "Content-Type": "application/x-www-form-urlencoded", "HX-Request": "true", "X-CSRFToken": csrfToken(entry) },
      signal: controller ? controller.signal : undefined
    }).then(function (response) {
      return response.text().then(function (html) { window.clearTimeout(timeout); finished(entry, response, html); });
    }, function () { window.clearTimeout(timeout); fail(entry); });
  };

  var capture = function (answerForm) {
    var field = answerForm.elements.position;
    if (!field) { return; }
    var position = field.value;
    var entry = outbox[position];
    if (!entry) {
      entry = outbox[position] = { position: position, version: 0, sentVersion: 0, inflight: false, failing: false, delay: FIRST_RETRY, timer: null };
    }
    entry.path = answerForm.getAttribute("action");
    var params = new window.URLSearchParams(new window.FormData(answerForm));
    entry.csrf = params.get("csrfmiddlewaretoken") || "";
    params.delete("csrfmiddlewaretoken"); // sent as a header instead, from the current cookie
    entry.body = params.toString();
    entry.version += 1;
    delete refused[position];
    schedule(entry, DEBOUNCE);
    refreshPill();
  };
  var flushAll = function () {
    Object.keys(outbox).forEach(function (key) {
      var entry = outbox[key];
      if (!entry.inflight) { schedule(entry, 0); }
    });
  };

  document.addEventListener("change", function (evt) {
    var answerForm = evt.target && evt.target.closest ? evt.target.closest("[data-answer-form]") : null;
    if (answerForm) { capture(answerForm); }
  }, true);
  /* Leaving the question (Next, Previous, the map): send what is waiting now. */
  document.body.addEventListener("htmx:beforeRequest", flushAll);
  /* Leaving the page: the request is kept alive by the browser. If an answer is still waiting
     (offline, or a save not yet accepted), the browser first asks the learner to stay, because
     the outbox lives in this page and a reload or a closed tab would lose it. */
  window.addEventListener("pagehide", function () { leaving = true; flushAll(); });
  window.addEventListener("beforeunload", function (evt) {
    if (!pending()) { return; }
    flushAll();
    evt.preventDefault();
    evt.returnValue = "";
  });
  var retrySignedIn = document.getElementById("session-retry");
  if (retrySignedIn) {
    retrySignedIn.addEventListener("click", function () {
      Object.keys(outbox).forEach(function (key) { outbox[key].delay = FIRST_RETRY; });
      flushAll();
    });
  }
  window.addEventListener("online", function () {
    Object.keys(outbox).forEach(function (key) { outbox[key].delay = FIRST_RETRY; });
    flushAll();
  });
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { flushAll(); } });
  window.addEventListener("focus", function () { if (expired) { flushAll(); } });
  window.addEventListener("offline", function () { if (pending()) { refreshPill(); } });
  /* A normal link (such as Review and submit) waits until every answer is saved, so the next
     page shows them. If a save cannot go through, the learner stays here and sees why. */
  var hasRefused = function () { return Object.keys(refused).length > 0; };
  var holdHere = function () { // stay on the quiz and point the learner at the "Not saved" pill
    refreshPill();
    var el = pill();
    if (el) { el.setAttribute("tabindex", "-1"); el.focus(); }
    // If the answer that was not saved belongs to another question, show that question.
    var waiting = Object.keys(outbox).concat(Object.keys(refused));
    var current = String(currentPosition());
    var f = document.querySelector("[data-answer-form]");
    if (!f || !waiting.length || waiting.indexOf(current) >= 0 || !window.htmx) { return; }
    var url = f.getAttribute("action").replace(/answer\/$/, "q/" + encodeURIComponent(waiting[0]) + "/");
    window.htmx.ajax("GET", url, { target: "#question-panel" });
  };
  root.addEventListener("click", function (evt) {
    var link = evt.target.closest ? evt.target.closest("a[href]") : null;
    if (!link || link.hasAttribute("hx-get") || evt.defaultPrevented) { return; }
    if (!pending() && !hasRefused()) { return; }
    evt.preventDefault();
    if (!pending()) { holdHere(); return; } // a refused answer: leaving now would hide it
    flushAll();
    var waited = 0;
    var timer = window.setInterval(function () {
      waited += 100;
      if (pending() && waited < 8000) { return; }
      window.clearInterval(timer);
      if (pending() || hasRefused()) { holdHere(); return; } // still failing, or refused meanwhile
      window.location.assign(link.href);
    }, 100);
  });

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
