/* Grafici interattivi sul sito: usa il codice originale del plugin Graphs di Obsidian
   (extra/graphs-plugin.js) con un piccolo "finto Obsidian" intorno. */
(function () {
  "use strict";
  const BASE = (document.querySelector("base") && document.querySelector("base").href) || location.href;
  const url = (p) => new URL(p, BASE).href;
  const LOCAL_YAML = "extra/js-yaml.min.js";
  const CDN_MATHJAX = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js";

  function loadScript(src) {
    return new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = src; s.async = true; s.onload = res; s.onerror = () => rej(new Error("load " + src));
      document.head.appendChild(s);
    });
  }

  // metodi che Obsidian aggiunge agli elementi del DOM
  function domHelpers() {
    const P = HTMLElement.prototype;
    if (P.createEl) return;
    function make(tag, o, cb) {
      if (typeof o === "string") o = { cls: o };
      o = o || {};
      const el = document.createElement(tag);
      if (o.cls) (Array.isArray(o.cls) ? o.cls : String(o.cls).split(/\s+/)).filter(Boolean).forEach((c) => el.classList.add(c));
      if (o.text != null) el.textContent = o.text;
      if (o.attr) for (const k in o.attr) el.setAttribute(k, o.attr[k]);
      if (o.title) el.title = o.title;
      this.appendChild(el);
      if (cb) cb(el);
      return el;
    }
    P.createEl = make;
    P.createDiv = function (o, cb) { return make.call(this, "div", o, cb); };
    P.createSpan = function (o, cb) { return make.call(this, "span", o, cb); };
    P.addClass = function (...c) { this.classList.add(...c); };
    P.removeClass = function (...c) { this.classList.remove(...c); };
    P.hasClass = function (c) { return this.classList.contains(c); };
    P.toggleClass = function (c, v) { this.classList.toggle(c, v); };
    P.empty = function () { this.innerHTML = ""; };
    P.setText = function (t) { this.textContent = t; };
    if (!String.prototype.contains) Object.defineProperty(String.prototype, "contains", { value: function (x) { return this.includes(x); } });
    if (!Array.prototype.contains) Object.defineProperty(Array.prototype, "contains", { value: function (x) { return this.includes(x); } });
  }

  let mathjaxP = null;
  function loadMathJax() {
    if (mathjaxP) return mathjaxP;
    if (!window.MathJax || !window.MathJax.startup) {
      window.MathJax = {
        tex: { inlineMath: [["$", "$"]], processEscapes: true },
        chtml: { adaptiveCSS: false },
        startup: { typeset: false },
      };
    }
    mathjaxP = loadScript(CDN_MATHJAX).then(() => window.MathJax.startup.promise).catch(() => {});
    return mathjaxP;
  }

  function obsidianShim() {
    const chain = () => new Proxy(function () {}, { get: (t, k) => (k === "then" ? undefined : chain()), apply: () => chain() });
    class Plugin {
      constructor(app, manifest) { this.app = app; this.manifest = manifest; this._proc = {}; }
      async loadData() { return { height: 300, width: 700, alignment: "0 auto", transparentBackground: true }; }
      async saveData() {}
      addSettingTab() {} addCommand() {} registerEvent() {} register() {} registerInterval() {}
      registerMarkdownCodeBlockProcessor(lang, fn) { this._proc[lang] = fn; }
    }
    class Dummy { constructor() {} open() {} close() {} }
    return {
      Plugin,
      MarkdownRenderChild: class { constructor(el) { this.containerEl = el; } },
      MarkdownView: class {},
      PluginSettingTab: Dummy, Modal: Dummy, Notice: Dummy, AbstractInputSuggest: Dummy, TFolder: class {},
      Setting: function () { return chain(); },
      loadMathJax,
      parseYaml: (s) => window.jsyaml.load(s),
      debounce: (f) => f,
      normalizePath: (p) => p,
    };
  }

  let pluginP = null;
  function getPlugin() {
    if (pluginP) return pluginP;
    pluginP = (async () => {
      domHelpers();
      window.CodeMirror = window.CodeMirror || { defineMode() {}, getMode() {} };
      await loadScript(url(LOCAL_YAML));
      const code = await (await fetch(url("extra/graphs-plugin.js"))).text();
      const shim = obsidianShim();
      const module = { exports: {} };
      new Function("require", "module", "exports", code)((n) => (n === "obsidian" ? shim : undefined), module, module.exports);
      const Cls = module.exports.default || module.exports;
      const app = {
        workspace: { on() { return {}; }, getActiveFile() { return null; }, getActiveViewOfType() { return null; }, getLeavesOfType() { return []; } },
        vault: {},
      };
      const plugin = new Cls(app, { id: "graphs", dir: "" });
      await plugin.onload();
      return plugin;
    })();
    return pluginP;
  }

  function decode(b64) {
    const bin = atob(b64);
    return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
  }

  function scan() {
    const blocks = document.querySelectorAll(".site-graph:not([data-done])");
    if (!blocks.length) return;
    blocks.forEach((el) => { el.dataset.done = "1"; });
    getPlugin().then((plugin) => {
      blocks.forEach((el) => {
        try { plugin.handleCodeBlock(decode(el.dataset.src), el, el.dataset.g3d === "1", null); }
        catch (e) { el.textContent = "Grafico non disponibile: " + e; }
      });
    }).catch((e) => blocks.forEach((el) => { el.textContent = "Grafico non disponibile: " + e; }));
  }

  function start() {
    scan();
    new MutationObserver(() => scan()).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
