/* Jikji Labs — i18n runtime
 * English text is baked into each page (SEO + no-JS friendly).
 * Non-English languages live in assets/i18n/<lang>.js and are lazy-loaded,
 * overlaying the baked English. Missing keys fall back to English.
 */
(function(){
  "use strict";
  var LANGS = [
    ["en","English"],["ko","한국어"],["ja","日本語"],
    ["zh","简体中文"],["zh-tw","繁體中文"],["fr","Français"],
    ["de","Deutsch"],["es","Español"],["pt","Português"],
    ["it","Italiano"],["ru","Русский"],["vi","Tiếng Việt"],
    ["id","Bahasa Indonesia"]
  ];
  var SUPPORTED = LANGS.map(function(x){return x[0];});
  window.JIKJI_I18N = window.JIKJI_I18N || {};
  var loaded = {en:true};
  var nodes = null; // cached [data-i18n] elements with their baked English

  function cacheNodes(){
    nodes = [];
    document.querySelectorAll("[data-i18n]").forEach(function(el){
      el._en = el.innerHTML;
      nodes.push(el);
    });
  }

  function apply(lang){
    if(!nodes) cacheNodes();
    var dict = (lang !== "en" && window.JIKJI_I18N[lang]) || null;
    nodes.forEach(function(el){
      var k = el.getAttribute("data-i18n");
      if(dict && dict[k] !== undefined) el.innerHTML = dict[k];
      else el.innerHTML = el._en;
    });
    document.documentElement.lang = lang;
    var sel = document.getElementById("langSel");
    if(sel) sel.value = lang;
    try{ localStorage.setItem("jikji-lang", lang); }catch(e){}
  }

  function loadLang(lang, cb){
    if(lang === "en" || loaded[lang]){ cb(); return; }
    var s = document.createElement("script");
    s.src = "assets/i18n/" + lang + ".js";
    s.onload = function(){ loaded[lang] = true; cb(); };
    s.onerror = function(){ cb(); }; // fall back to English silently
    document.head.appendChild(s);
  }

  window.setLang = function(lang){
    if(SUPPORTED.indexOf(lang) === -1) lang = "en";
    loadLang(lang, function(){ apply(lang); });
  };

  function detect(){
    var saved = null;
    try{ saved = localStorage.getItem("jikji-lang"); }catch(e){}
    if(saved && SUPPORTED.indexOf(saved) !== -1) return saved;
    var nav = (navigator.language || "").toLowerCase();
    if(nav.indexOf("zh") === 0) return /tw|hk|mo|hant/.test(nav) ? "zh-tw" : "zh";
    var p = nav.slice(0,2);
    return SUPPORTED.indexOf(p) !== -1 ? p : "en";
  }

  function buildSelector(){
    var sel = document.getElementById("langSel");
    if(!sel || sel.options.length) return;
    LANGS.forEach(function(x){
      var o = document.createElement("option");
      o.value = x[0]; o.textContent = x[1];
      sel.appendChild(o);
    });
    sel.addEventListener("change", function(){ window.setLang(this.value); });
  }

  function init(){
    cacheNodes();
    buildSelector();
    window.setLang(detect());
  }
  if(document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init);
  else init();
})();
