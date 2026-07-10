/* Jikji Labs internationalisation runtime.
 *
 * English remains embedded in every page for SEO, accessibility, and no-JS use.
 * Historical translations are applied only when their source English still matches
 * the current DOM. Changed and newly added copy therefore falls back to current
 * English instead of showing an obsolete translation.
 */
(function () {
  "use strict";

  var LANGS = [
    ["en", "English"], ["ko", "한국어"], ["ja", "日本語"],
    ["zh", "简体中文"], ["zh-tw", "繁體中文"], ["fr", "Français"],
    ["de", "Deutsch"], ["es", "Español"], ["pt", "Português"],
    ["it", "Italiano"], ["ru", "Русский"], ["vi", "Tiếng Việt"],
    ["id", "Bahasa Indonesia"]
  ];
  var supported = LANGS.map(function (entry) { return entry[0]; });
  var loaded = { en: true };
  var requestSerial = 0;
  var nodes;
  var runtimeURL = document.currentScript && document.currentScript.src;
  var localeBase = runtimeURL ? new URL("i18n/", runtimeURL).href : "assets/i18n/";

  window.JIKJI_I18N = window.JIKJI_I18N || {};

  function normalise(value) {
    return String(value || "")
      .replace(/<br\s*\/?\s*>/gi, "<br>")
      .replace(/\s+/g, " ")
      .trim();
  }

  function cacheNodes() {
    nodes = [];
    document.querySelectorAll("[data-i18n]").forEach(function (element) {
      nodes.push({
        element: element,
        key: element.getAttribute("data-i18n"),
        english: element.innerHTML
      });
    });
  }

  function translationIsCurrent(node, canonicalEnglish) {
    if (!canonicalEnglish || canonicalEnglish[node.key] === undefined) return false;
    return normalise(canonicalEnglish[node.key]) === normalise(node.english);
  }

  function apply(lang) {
    if (!nodes) cacheNodes();
    var canonicalEnglish = window.JIKJI_I18N.en || {};
    var translations = lang === "en" ? null : window.JIKJI_I18N[lang];

    nodes.forEach(function (node) {
      if (translations && translations[node.key] !== undefined &&
          translationIsCurrent(node, canonicalEnglish)) {
        node.element.innerHTML = translations[node.key];
      } else {
        node.element.innerHTML = node.english;
      }
    });

    document.documentElement.lang = lang;
    document.documentElement.dir = "ltr";
    var selector = document.getElementById("langSel");
    if (selector) selector.value = lang;
    try { localStorage.setItem("jikji-lang", lang); } catch (_) {}
  }

  function load(lang, done) {
    if (lang === "en" || loaded[lang]) { done(); return; }
    var script = document.createElement("script");
    script.src = localeBase + lang + ".js";
    script.onload = function () { loaded[lang] = true; done(); };
    script.onerror = done;
    document.head.appendChild(script);
  }

  function setLanguage(lang) {
    if (supported.indexOf(lang) === -1) lang = "en";
    var request = ++requestSerial;
    load(lang, function () {
      if (request === requestSerial) apply(lang);
    });
  }

  function detectLanguage() {
    var saved;
    try { saved = localStorage.getItem("jikji-lang"); } catch (_) {}
    if (supported.indexOf(saved) !== -1) return saved;
    var browser = (navigator.language || "").toLowerCase();
    if (browser.indexOf("zh") === 0) {
      return /tw|hk|mo|hant/.test(browser) ? "zh-tw" : "zh";
    }
    var base = browser.slice(0, 2);
    return supported.indexOf(base) === -1 ? "en" : base;
  }

  function buildSelector() {
    var selector = document.getElementById("langSel");
    if (!selector || selector.options.length) return;
    LANGS.forEach(function (entry) {
      var option = document.createElement("option");
      option.value = entry[0];
      option.textContent = entry[1];
      selector.appendChild(option);
    });
    selector.addEventListener("change", function () { setLanguage(this.value); });
  }

  function buildNavigation() {
    var toggle = document.querySelector(".nav-toggle");
    var links = document.querySelector(".nav-links");
    if (!toggle || !links) return;
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      links.classList.toggle("is-open", open);
    });
    links.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        toggle.setAttribute("aria-expanded", "false");
        links.classList.remove("is-open");
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        toggle.setAttribute("aria-expanded", "false");
        links.classList.remove("is-open");
        toggle.focus();
      }
    });
  }

  function init() {
    cacheNodes();
    buildSelector();
    buildNavigation();
    setLanguage(detectLanguage());
  }

  window.setLang = setLanguage;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}());
