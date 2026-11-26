/* Applies the saved light/dark choice before the page paints (external file: the Content-Security-Policy forbids inline scripts). */
(function () {
  try {
    var saved = localStorage.getItem("nts.theme");
    var dark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (dark) document.documentElement.classList.add("dark");
  } catch (e) { /* storage blocked: stay light */ }
})();
