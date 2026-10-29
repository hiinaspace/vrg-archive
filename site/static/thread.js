// Optional enhancements for thread pages: thumbnails from Range-readable packs, spoiler reveal,
// >>N hover previews, dark-mode toggle. Everything works (minus thumbnails) without this script.
(function () {
  "use strict";
  var base = new URL("../data/thumbs/", document.baseURI);
  var store;
  try { store = window.localStorage; } catch (e) { store = null; }

  // ---- theme
  var tb = document.getElementById("theme");
  var saved = store && store.getItem("vrg-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  if (tb) {
    tb.hidden = false;
    tb.addEventListener("click", function () {
      var dark = document.documentElement.dataset.theme === "dark" ||
        (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
      var next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      if (store) store.setItem("vrg-theme", next);
    });
  }

  // ---- spoilers
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".th.sp, s.sp");
    if (t) t.classList.toggle("rv");
  });

  // ---- thumbnails: coalesced Range reads from packs
  var els = Array.prototype.slice.call(document.querySelectorAll(".th[data-t]"));
  var whole = {};
  function fetchRange(pack, off, len) {
    var url = new URL("pack" + pack + ".bin", base).href;
    if (whole[pack]) return whole[pack].then(function (b) { return b.slice(off, off + len); });
    return fetch(url, { headers: { Range: "bytes=" + off + "-" + (off + len - 1) } }).then(function (r) {
      if (r.status === 206) return r.arrayBuffer();
      // host ignored Range: download the pack once and slice it
      whole[pack] = r.arrayBuffer();
      return whole[pack].then(function (b) { return b.slice(off, off + len); });
    });
  }
  function hydrate(el) {
    if (el.dataset.done) return;
    el.dataset.done = "1";
    var p = el.dataset.t.split(",").map(Number);
    fetchRange(p[0], p[1], p[2]).then(function (buf) {
      var img = new Image();
      img.alt = el.textContent;
      img.src = URL.createObjectURL(new Blob([buf], { type: "image/jpeg" }));
      el.textContent = "";
      el.appendChild(img);
    }).catch(function () { /* placeholder stays */ });
  }
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) { if (en.isIntersecting) { io.unobserve(en.target); hydrate(en.target); } });
    }, { rootMargin: "600px" });
    els.forEach(function (el) { io.observe(el); });
  } else els.forEach(hydrate);

  // ---- hover previews for >>N within the page
  var pop;
  document.addEventListener("mouseover", function (e) {
    var a = e.target.closest && e.target.closest("a.ql");
    if (!a) return;
    var h = a.getAttribute("href");
    if (!h || h.charAt(0) !== "#") return;
    var src = document.getElementById(h.slice(1));
    if (!src) return;
    hide();
    pop = document.createElement("div");
    pop.className = "hp";
    var c = src.cloneNode(true);
    c.removeAttribute("id");
    Array.prototype.forEach.call(c.querySelectorAll("[id]"), function (n) { n.removeAttribute("id"); });
    pop.appendChild(c);
    document.body.appendChild(pop);
    var r = a.getBoundingClientRect();
    var left = Math.min(r.right + 8, innerWidth - pop.offsetWidth - 8);
    var top = r.top;
    if (top + pop.offsetHeight > innerHeight - 8) top = Math.max(8, innerHeight - pop.offsetHeight - 8);
    pop.style.left = Math.max(8, left) + "px";
    pop.style.top = top + "px";
    // thumbnails inside the clone reuse the already-loaded object URLs
  });
  function hide() { if (pop) { pop.remove(); pop = null; } }
  document.addEventListener("mouseout", function (e) { if (e.target.closest && e.target.closest("a.ql")) hide(); });
  window.addEventListener("scroll", hide, { passive: true });
})();
