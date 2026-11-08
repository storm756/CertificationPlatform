// Live "Your certificate will read: ..." preview and the guardian fields for 16-17-year-olds.
// The server re-checks everything; this only helps the person fill the form.
(function () {
  var name = document.getElementById("id_certificate_name");
  var preview = document.getElementById("name-preview");
  if (name && preview) {
    var show = function () {
      var v = name.value.replace(/\s+/g, " ").trim();
      preview.textContent = v ? "Your certificate will read: " + v.toUpperCase() : "";
    };
    name.addEventListener("input", show);
    show();
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
