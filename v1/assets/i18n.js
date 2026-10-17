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
    document.querySelectorAll("[data-i18n], [data-i18n-alt]").forEach(function (element) {
      var attribute = element.hasAttribute("data-i18n-alt") ? "alt" : null;
      nodes.push({
        element: element,
        key: element.getAttribute(attribute ? "data-i18n-alt" : "data-i18n"),
        attribute: attribute,
        english: attribute ? element.getAttribute(attribute) : element.innerHTML
      });
    });
  }

  function translationIsCurrent(node, canonicalEnglish, lang) {
    if (!canonicalEnglish || canonicalEnglish[node.key] === undefined) return false;
    if (!window.JIKJI_I18N_SOURCE ||
        window.JIKJI_I18N_SOURCE[lang] !== window.JIKJI_I18N_REVISION) return false;
    return normalise(canonicalEnglish[node.key]) === normalise(node.english);
  }

  function apply(lang) {
    if (!nodes) cacheNodes();
    var canonicalEnglish = window.JIKJI_I18N.en || {};
    var translations = lang === "en" ? null : window.JIKJI_I18N[lang];

    nodes.forEach(function (node) {
      if (translations && translations[node.key] !== undefined &&
          translationIsCurrent(node, canonicalEnglish, lang)) {
        if (node.attribute) node.element.setAttribute(node.attribute, translations[node.key]);
        else node.element.innerHTML = translations[node.key];
      } else {
        if (node.attribute) node.element.setAttribute(node.attribute, node.english);
        else node.element.innerHTML = node.english;
      }
    });

    document.documentElement.lang = lang;
    document.documentElement.dir = "ltr";
    var selector = document.getElementById("langSel");
    var messages = lang === "en" ? canonicalEnglish : (translations || canonicalEnglish);
    if (selector) {
      selector.value = lang;
      selector.setAttribute("aria-label", messages["a11y.language"] || canonicalEnglish["a11y.language"] || "Language");
    }
    var languageLabel = document.querySelector(".lang-label .sr-only");
    if (languageLabel) languageLabel.textContent = messages["a11y.language"] || canonicalEnglish["a11y.language"] || "Language";
    var toggle = document.querySelector(".nav-toggle");
    if (toggle) {
      var toggleKey = toggle.getAttribute("aria-expanded") === "true" ? "a11y.nav.close" : "a11y.nav.open";
      toggle.setAttribute("aria-label", messages[toggleKey] || canonicalEnglish[toggleKey] || "Navigation");
    }
    document.querySelectorAll("[data-english-notice]").forEach(function (notice) {
      notice.hidden = lang === "en";
    });
    try { localStorage.setItem("jikji-lang", lang); } catch (_) {}
  }

  function load(lang, done) {
    if (lang === "en" || loaded[lang]) { done(true); return; }
    var script = document.createElement("script");
    script.src = localeBase + lang + ".js";
    script.onload = function () { loaded[lang] = true; done(true); };
    script.onerror = function () { done(false); };
    document.head.appendChild(script);
  }

  function setLanguage(lang) {
    if (supported.indexOf(lang) === -1) lang = "en";
    var request = ++requestSerial;
    load(lang, function (available) {
      if (request === requestSerial) apply(available ? lang : "en");
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
    function setOpen(open, restoreFocus) {
      toggle.setAttribute("aria-expanded", String(open));
      links.classList.toggle("is-open", open);
      var lang = document.documentElement.lang || "en";
      var messages = window.JIKJI_I18N[lang] || window.JIKJI_I18N.en || {};
      var key = open ? "a11y.nav.close" : "a11y.nav.open";
      toggle.setAttribute("aria-label", messages[key] || (open ? "Close navigation" : "Open navigation"));
      if (restoreFocus) toggle.focus();
    }
    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true", false);
    });
    links.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        setOpen(false, false);
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setOpen(false, true);
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
