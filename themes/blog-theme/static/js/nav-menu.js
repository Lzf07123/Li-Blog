(function () {
  "use strict";

  var header = document.querySelector(".site-header");
  if (!header) return;

  var ticking = false;
  function update() {
    header.classList.toggle("is-scrolled", window.scrollY > 8);
    ticking = false;
  }
  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(update);
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  update();
})();

(function () {
  "use strict";

  var menus = Array.prototype.slice.call(document.querySelectorAll("[data-mobile-menu]"));
  if (!menus.length) return;

  function closeAll(except) {
    menus.forEach(function (wrap) {
      var details = wrap.querySelector("details");
      if (details && details !== except && details.open) {
        details.removeAttribute("open");
      }
    });
  }

  function focusTrigger(details) {
    var summary = details && details.querySelector("summary");
    if (summary) summary.focus();
  }

  document.addEventListener("click", function (event) {
    menus.forEach(function (wrap) {
      var details = wrap.querySelector("details");
      if (details && details.open && !wrap.contains(event.target)) {
        details.removeAttribute("open");
      }
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    menus.forEach(function (wrap) {
      var details = wrap.querySelector("details");
      if (details && details.open) {
        details.removeAttribute("open");
        focusTrigger(details);
      }
    });
  });

  menus.forEach(function (wrap) {
    var details = wrap.querySelector("details");
    if (!details) return;
    var summary = details.querySelector("summary");
    if (summary) {
      summary.setAttribute("aria-expanded", details.open ? "true" : "false");
      details.addEventListener("toggle", function () {
        summary.setAttribute("aria-expanded", details.open ? "true" : "false");
      });
    }
    Array.prototype.forEach.call(details.querySelectorAll("a"), function (link) {
      link.addEventListener("click", function () {
        details.removeAttribute("open");
      });
    });
  });

  window.addEventListener("resize", closeAll);
})();
