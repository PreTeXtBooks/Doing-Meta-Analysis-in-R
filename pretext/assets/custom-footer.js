(function () {
  function addCustomFooterLink() {
    var footer = document.querySelector(".ptx-page-footer");
    if (!footer || footer.querySelector(".custom-site-footer-link-wrap")) {
      return;
    }

    var wrap = document.createElement("div");
    wrap.className = "custom-site-footer-link-wrap";

    var prefix = document.createElement("span");
    prefix.className = "custom-site-footer-prefix";
    prefix.textContent = "Adapted to PreTeXt by ";

    var link = document.createElement("a");
    link.className = "custom-site-footer-link";
    link.href = "https://www.idems.international/";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "IDEMS International";
    link.setAttribute("aria-label", "Visit IDEMS International");

    wrap.appendChild(prefix);
    wrap.appendChild(link);
    footer.appendChild(wrap);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addCustomFooterLink);
  } else {
    addCustomFooterLink();
  }
})();
