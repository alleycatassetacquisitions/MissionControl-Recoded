/* AlleycatTV kiosk style injection — hides cursor and scrollbars on all pages. */
(function () {
  "use strict";

  const CSS = `
    *, *::before, *::after {
      cursor: none !important;
    }
    ::-webkit-scrollbar {
      display: none !important;
      width: 0 !important;
      height: 0 !important;
    }
    html, body {
      scrollbar-width: none !important;
      -ms-overflow-style: none !important;
      overflow: hidden !important;
    }
  `;

  function injectStyle() {
    const existing = document.getElementById("__alleycattv_kiosk__");
    if (existing) return;
    const style = document.createElement("style");
    style.id = "__alleycattv_kiosk__";
    style.textContent = CSS;
    (document.head || document.documentElement).appendChild(style);
  }

  // Inject immediately and also after DOM is ready (some SPAs re-render the head)
  injectStyle();
  document.addEventListener("DOMContentLoaded", injectStyle);
  document.addEventListener("readystatechange", injectStyle);
})();
