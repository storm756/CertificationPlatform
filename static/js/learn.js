/* Lesson pages: reveal, flip cards, myth-or-fact, practice checks, completion and the time heartbeat.
   Plain JavaScript, no inline scripts. Server text is only ever written with textContent. The answers
   to reveal and myth-or-fact blocks are not in the page: the server sends them when asked. */
(function () {
  "use strict";
  var unit = document.querySelector("[data-unit]");
  if (!unit) { return; }
  var token = (unit.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
  var post = function (url, data) {
    var body = new URLSearchParams(data || {});
    return window.fetch(url, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": token, "Content-Type": "application/x-www-form-urlencoded" }, body: body.toString() })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, json: j }; }); });
  };
  var learner = unit.getAttribute("data-learner") === "1";
  var done = unit.getAttribute("data-done") === "1";
  var type = unit.getAttribute("data-type");
  var completeUrl = unit.getAttribute("data-complete-url");

  var markDone = function (how) {
    if (done || !learner) { return; }
    done = true;
    post(completeUrl, { how: how });
    var status = unit.querySelector("[data-complete-status]");
    if (status) { status.textContent = "Completed"; status.classList.add("status--done"); }
    var button = unit.querySelector("[data-mark]");
    if (button) { button.hidden = true; }
    var current = unit.querySelector(".outline a[aria-current=page]");
    if (current) { current.classList.add("is-done"); }
  };
  var button = unit.querySelector("[data-mark]");
  if (button) { button.addEventListener("click", function () { markDone("button"); }); }

  var verdict = function (box, tone, head, text) {
    box.textContent = "";
    var p = document.createElement("p");
    p.className = "myth__verdict myth__verdict--" + tone;
    var strong = document.createElement("strong");
    strong.textContent = head + " ";
    p.appendChild(strong);
    p.appendChild(document.createTextNode(text));
    box.appendChild(p);
  };

  /* Predict, then reveal */
  Array.prototype.forEach.call(unit.querySelectorAll("[data-reveal]"), function (box) {
    var btn = box.querySelector("[data-reveal-btn]"), out = box.querySelector("[data-reveal-answer]");
    btn.addEventListener("click", function () {
      post(box.getAttribute("data-url")).then(function (r) {
        if (!r.ok) { return; }
        out.textContent = "";
        var p = document.createElement("p");
        p.className = "reveal__text";
        p.textContent = r.json.answer;
        out.appendChild(p);
        btn.hidden = true;
        btn.setAttribute("aria-expanded", "true");
      });
    });
  });

  /* Flip cards: reference text, safe to hold in the page */
  Array.prototype.forEach.call(unit.querySelectorAll("[data-flip]"), function (card) {
    card.addEventListener("click", function () {
      var open = card.getAttribute("aria-expanded") !== "true";
      card.setAttribute("aria-expanded", String(open));
      card.querySelector(".flip__back").hidden = !open;
      card.querySelector(".flip__front").hidden = open;
    });
  });

  /* Myth or fact */
  Array.prototype.forEach.call(unit.querySelectorAll("[data-myth]"), function (box) {
    Array.prototype.forEach.call(box.querySelectorAll("[data-pick]"), function (btn) {
      btn.addEventListener("click", function () {
        if (box.getAttribute("data-done")) { return; }
        post(box.getAttribute("data-url"), { pick: btn.getAttribute("data-pick") }).then(function (r) {
          if (!r.ok) { return; }
          box.setAttribute("data-done", "1");
          Array.prototype.forEach.call(box.querySelectorAll("[data-pick]"), function (b) { b.disabled = true; });
          verdict(box.querySelector("[data-verdict]"), r.json.right ? "right" : "wrong", (r.json.is_fact ? "Fact." : "Myth.") + (r.json.right ? " You got it." : " Not quite."), r.json.why);
        });
      });
    });
  });

  /* Practice check (practice pool only): the server marks it and returns the full answer */
  Array.prototype.forEach.call(unit.querySelectorAll("[data-check]"), function (box) {
    Array.prototype.forEach.call(box.querySelectorAll("[data-choice]"), function (btn) {
      btn.addEventListener("click", function () {
        if (box.getAttribute("data-done")) { return; }
        post(box.getAttribute("data-url"), { m: box.getAttribute("data-m"), u: box.getAttribute("data-u"), question: box.getAttribute("data-q"), choice: btn.getAttribute("data-choice") }).then(function (r) {
          if (!r.ok) { verdict(box.querySelector("[data-verdict]"), "wrong", "Sorry.", r.json.error || "Try again."); return; }
          box.setAttribute("data-done", "1");
          Array.prototype.forEach.call(box.querySelectorAll("[data-choice]"), function (b) { b.disabled = true; });
          verdict(box.querySelector("[data-verdict]"), r.json.right ? "right" : "wrong", r.json.right ? "Right." : "Not quite.", "The answer: " + r.json.right_text + (r.json.hint ? " " + r.json.hint : ""));
        });
      });
    });
  });

  /* Reading: complete at the end */
  var sentinel = unit.querySelector("[data-end-sentinel]");
  if (type === "reading" && sentinel) {
    var bar = unit.querySelector("[data-read-progress]");
    if (bar) { bar.hidden = false; }
    var onScroll = function () {
      var body = unit.querySelector(".prose").getBoundingClientRect();
      if (bar) { bar.style.setProperty("--v", String(Math.max(0, Math.min(100, ((window.innerHeight - body.top) / body.height) * 100)))); }
      if (sentinel.getBoundingClientRect().top < window.innerHeight) { markDone("end"); }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* Film: 80% watched, from the HTML5 video; YouTube reports through the IFrame API */
  var video = unit.querySelector("video[data-mp4]");
  if (video) {
    var seen = 0;
    video.addEventListener("timeupdate", function () {
      if (video.duration) { seen = Math.max(seen, video.currentTime / video.duration); }
      if (seen >= 0.8) { markDone("watched"); }
    });
  }
  var frame = unit.querySelector("iframe[data-yt]");
  if (frame) {
    var script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(script);
    window.onYouTubeIframeAPIReady = function () {
      var player = new window.YT.Player(frame, { events: { onStateChange: function (e) {
        if (e.data !== 1) { return; }
        var timer = window.setInterval(function () {
          var total = player.getDuration();
          if (total && player.getCurrentTime() / total >= 0.8) { window.clearInterval(timer); markDone("watched"); }
        }, 2000);
      } } });
    };
  }

  /* Time on task: a beat every 30 s while the page is visible. The server ignores it for under-18s. */
  if (learner) {
    window.setInterval(function () {
      if (!document.hidden) { post(unit.getAttribute("data-heartbeat-url"), { m: unit.getAttribute("data-m"), u: unit.getAttribute("data-u") }); }
    }, 30000);
  }
})();
