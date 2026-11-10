// Live "Your certificate will read: ..." preview and the guardian fields for 16-17-year-olds.
// The server re-checks everything; this only helps the person fill the form.
(function () {
  var name = document.getElementById("id_certificate_name");
  var preview = document.querySelector("[data-cert-preview]");
  if (name && preview) {
    var show = function () {
      var v = name.value.replace(/\s+/g, " ").trim();
      preview.textContent = v ? v.toUpperCase() : "—";
    };
    name.addEventListener("input", show);
    show();
  }
  var pw = document.getElementById("id_password");
  var meter = document.querySelector("[data-pw-meter]");
  var pwText = document.querySelector("[data-pw-text]");
  if (pw && meter) {
    // The wording comes from the template (translated there), like the Show/Hide labels.
    var MIN_LENGTH = 10; // Django's minimum: the server validates it, this only guides the person
    var words = {
      empty: pwText ? pwText.textContent : "",
      short: pwText ? pwText.getAttribute("data-short") : "",
      levels: pwText ? (pwText.getAttribute("data-levels") || "").split("|") : []
    };
    var update = function () {
      var v = pw.value, score = 0, text = words.empty;
      if (v.length > 0 && v.length < MIN_LENGTH) {
        score = 1; // one bar, whatever characters were typed
        text = words.short;
      } else if (v.length >= MIN_LENGTH) {
        score = 1;
        if (v.length >= 14) { score += 1; }
        if (/[a-z]/.test(v) && /[A-Z0-9]/.test(v)) { score += 1; }
        if (/[^A-Za-z0-9]/.test(v) || v.split(/\s+/).length >= 3) { score += 1; }
        text = words.levels[score - 1] || words.levels[0] || "";
      }
      meter.setAttribute("data-score", String(score));
      if (pwText) { pwText.textContent = text; }
    };
    pw.addEventListener("input", update);
    update();
  }
  var dob = document.getElementById("id_date_of_birth");
  var guardian = document.getElementById("guardian-fields");
  if (dob && guardian) {
    var check = function () {
      if (!dob.value) { return; }
      var born = new Date(dob.value), now = new Date();
      var age = now.getFullYear() - born.getFullYear();
      var m = now.getMonth() - born.getMonth();
      if (m < 0 || (m === 0 && now.getDate() < born.getDate())) { age -= 1; }
      guardian.classList.toggle("hidden", !(age >= 16 && age < 18));
    };
    dob.addEventListener("change", check);
    check();
  }
})();
