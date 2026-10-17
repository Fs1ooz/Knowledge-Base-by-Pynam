#!/usr/bin/env python3
"""Sistema il sito esportato da Webpage HTML Export.

Uso:  python3 postprocess.py <cartella del sito> <cartella del vault>

- rimette i grafici del plugin Graphs (definizione presa dalla nota .md)
- ricostruisce le colonne di Advanced Multi Column (%% col-start/col-break/col-end %%)
- aggiunge a ogni pagina CSS e JS di extra/
Si puo' rilanciare quante volte si vuole: le pagine gia' sistemate non cambiano.
"""
import base64, html, json, os, re, sys

SITE, VAULT = sys.argv[1], sys.argv[2]
MARK = "<!--site-extra-->"
HEAD_INJECT = (MARK + '<link rel="stylesheet" href="extra/graphs.css"><link rel="stylesheet" href="extra/site.css">'
               '<script defer src="extra/site.js"></script>')

# ---------------------------------------------------------------- utilita' HTML
TAG_RE = re.compile(r"<(/?)div\b[^>]*>", re.I)

def match_div(s, start):
    """dato l'indice di un '<div', restituisce l'indice subito dopo il suo '</div>'"""
    depth = 0
    for m in TAG_RE.finditer(s, start):
        if m.group(1):
            depth -= 1
            if depth == 0:
                return m.end()
        else:
            if not m.group(0).endswith("/>"):
                depth += 1
    raise ValueError("div non chiuso")

def children(s, open_end, close_start):
    """figli <div> diretti tra open_end e close_start: lista di (start, end)"""
    out, i = [], open_end
    while True:
        j = s.find("<div", i, close_start)
        if j < 0:
            break
        # salta testo/spazi tra i figli (non dovrebbe esserci altro)
        e = match_div(s, j)
        out.append((j, e))
        i = e
    return out

def classes(tag):
    m = re.search(r'class="([^"]*)"', tag)
    return m.group(1).split() if m else []

# ---------------------------------------------------------------- markdown: blocchi
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([\w-]*)")
HEADING = re.compile(r"^ {0,3}(#{1,6})(\s|$)")
HR = re.compile(r"^ {0,3}([-*_])(\s*\1){2,}\s*$")
LIST = re.compile(r"^ {0,3}([-*+]|\d{1,9}[.)])\s")
QUOTE = re.compile(r"^ {0,3}>")
TABLE = re.compile(r"^\s*\|")
MARKER = re.compile(r"^%%\s*(col-start|col-break|col-end)(?:\s*:(.*?))?\s*%%$")
COMMENT_ONLY = re.compile(r"^(\s*%%.*?%%\s*)+$", re.S)

def strip_frontmatter(lines):
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return lines[i + 1:]
    return lines

def md_blocks(text):
    """approssima le 'sezioni' di Obsidian: ogni blocco = un div el-* nell'HTML"""
    lines = strip_frontmatter(text.split("\n"))
    blocks, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        m = FENCE.match(ln)
        if m:
            fence = m.group(1); j = i + 1
            while j < n and not lines[j].strip().startswith(fence[0] * len(fence)):
                j += 1
            blocks.append(("pre", lines[i:j + 1], m.group(2))); i = j + 1; continue
        if ln.strip().startswith("$$"):
            j = i
            if not (ln.strip().endswith("$$") and len(ln.strip()) > 2):
                j = i + 1
                while j < n and "$$" not in lines[j]:
                    j += 1
            blocks.append(("math", lines[i:j + 1], None)); i = j + 1; continue
        m = HEADING.match(ln)
        if m:
            blocks.append(("h%d" % len(m.group(1)), [ln], None)); i += 1; continue
        if HR.match(ln):
            blocks.append(("hr", [ln], None)); i += 1; continue
        if QUOTE.match(ln):
            j = i + 1
            while j < n and lines[j].strip() and (QUOTE.match(lines[j]) or not (HEADING.match(lines[j]) or FENCE.match(lines[j]) or HR.match(lines[j]) or (LIST.match(lines[j]) and (not re.match(r"^ {0,3}\d", lines[j]) or re.match(r"^ {0,3}1[.)]\s", lines[j]))))):
                j += 1
            blocks.append(("quote", lines[i:j], None)); i = j; continue
        if TABLE.match(ln):
            j = i + 1
            while j < n and TABLE.match(lines[j]):
                j += 1
            blocks.append(("table", lines[i:j], None)); i = j; continue
        if LIST.match(ln):
            j = i + 1
            while j < n:
                l2 = lines[j]
                if not l2.strip():
                    # lista "larga": continua se dopo la riga vuota riprende la lista o un rientro
                    k = j + 1
                    if k < n and (LIST.match(lines[k]) or lines[k].startswith(("  ", "\t"))):
                        j = k; continue
                    break
                if HEADING.match(l2) or FENCE.match(l2) or HR.match(l2):
                    break
                j += 1
            blocks.append(("list", lines[i:j], None)); i = j; continue
        # paragrafo (le righe successive non vuote ne fanno parte, finche' un altro blocco non lo interrompe)
        j = i + 1
        in_comment = ln.count("%%") % 2 == 1
        kind = "p"
        while j < n:
            l2 = lines[j]
            if in_comment:
                if l2.count("%%") % 2 == 1:
                    in_comment = False
                j += 1; continue
            if not l2.strip():
                break
            if re.match(r"^ {0,3}(=+|-+)\s*$", l2):   # titolo "setext"
                kind = "h1" if "=" in l2 else "h2"; j += 1; break
            if HEADING.match(l2) or FENCE.match(l2) or QUOTE.match(l2) or HR.match(l2) or l2.strip().startswith("$$"):
                break
            if LIST.match(l2) and (not re.match(r"^ {0,3}\d", l2) or re.match(r"^ {0,3}1[.)]\s", l2)):
                break
            if l2.count("%%") % 2 == 1:
                in_comment = True
            j += 1
        blocks.append((kind, lines[i:j], None))
        i = j
    return blocks

def el_kind(cls):
    for c in cls:
        if c.startswith("el-"):
            return c[3:]
    return None

# ---------------------------------------------------------------- stili colonne (come Advanced Multi Column)
BG = {"transparent": "transparent", "primary": "var(--background-primary)", "secondary": "var(--background-secondary)",
      "alt": "var(--background-primary-alt)", "accent-soft": "color-mix(in srgb, var(--interactive-accent) 14%, transparent)",
      "red-soft": "rgba(239, 68, 68, 0.14)", "orange-soft": "rgba(245, 158, 11, 0.14)", "yellow-soft": "rgba(234, 179, 8, 0.14)",
      "green-soft": "rgba(34, 197, 94, 0.14)", "cyan-soft": "rgba(6, 182, 212, 0.14)", "blue-soft": "rgba(59, 130, 246, 0.14)",
      "pink-soft": "rgba(236, 72, 153, 0.14)"}
COL = {"gray": "var(--background-modifier-border)", "accent": "var(--interactive-accent)", "muted": "var(--text-muted)",
       "text": "var(--text-normal)", "secondary": "var(--background-secondary)", "red": "#ef4444", "orange": "#f59e0b",
       "yellow": "#eab308", "green": "#22c55e", "cyan": "#06b6d4", "blue": "#3b82f6", "pink": "#ec4899"}

def truthy(v):
    return v.strip().lower() in ("1", "true", "yes", "on")

def parse_args(arg):
    """'47,b:accent-soft,bc:cyan,sb:1' -> (width, style dict)"""
    width, st = 0, {}
    for tok in (arg or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if re.fullmatch(r"\d+(\.\d+)?", tok):
            width = float(tok); continue
        if ":" not in tok:
            continue
        k, v = [x.strip() for x in tok.split(":", 1)]
        k = k.lower()
        if k == "b" and v in BG: st["bg"] = v
        elif k == "bc" and v in COL: st["bc"] = v
        elif k in ("t", "tc") and v in COL: st["tc"] = v
        elif k == "sb": st["sb"] = truthy(v)
        elif k == "sep": st["sep"] = truthy(v)
        elif k == "sc" and v in COL: st["sc"] = v
        elif k == "ss": st["ss"] = v
        elif k == "sw" and v.isdigit(): st["sw"] = int(v)
    return width, st

def col_style(st):
    css = {}
    if "bg" in st: css["--columns-col-bg"] = BG[st["bg"]]
    if "tc" in st: css["--columns-col-text"] = COL[st["tc"]]
    if "sb" in st or "bc" in st:
        show = st.get("sb", "bc" in st)
        css["--columns-col-border-color"] = COL[st.get("bc", "gray")]
        css["--columns-col-border-width"] = "1px" if show else "0px"
    return css

def style_attr(css, extra=""):
    s = ";".join("%s:%s" % kv for kv in css.items())
    if extra:
        s = (s + ";" if s else "") + extra
    return (' style="%s"' % html.escape(s, quote=True)) if s else ""

# ---------------------------------------------------------------- colonne
def build_columns(s, md_text, log):
    if "col-start" not in md_text or "columns-site" in s:
        return s, False
    m = re.search(r'<div class="markdown-preview-sizer[^"]*"[^>]*>', s)
    if not m:
        return s, False
    sizer_start = m.start()
    sizer_end = match_div(s, sizer_start)
    close_start = s.rfind("</div>", 0, sizer_end)
    kids = children(s, m.end(), close_start)
    els = [(a, b) for a, b in kids if el_kind(classes(s[a:s.find(">", a) + 1])) and "mod-frontmatter" not in classes(s[a:s.find(">", a) + 1])]
    blocks = md_blocks(md_text)
    if len(els) != len(blocks):
        log("  colonne saltate: %d blocchi nell'HTML, %d nella nota" % (len(els), len(blocks)))
        return s, False
    for (a, b), blk in zip(els, blocks):
        k = el_kind(classes(s[a:s.find(">", a) + 1]))
        if blk[0].startswith("h") and k != blk[0]:
            log("  colonne saltate: struttura diversa (%s vs %s)" % (k, blk[0]))
            return s, False

    # sequenza di eventi: ("el", html) oppure ("start"/"break"/"end", args)
    events = []
    for (a, b), blk in zip(els, blocks):
        chunk = s[a:b]
        if blk[0] != "p":
            events.append(("el", chunk)); continue
        text = "\n".join(blk[1])
        mk_lines = [(idx, MARKER.match(l.strip())) for idx, l in enumerate(blk[1])]
        markers = [(idx, mm) for idx, mm in mk_lines if mm]
        if not markers:
            events.append(("el", chunk)); continue
        content_idx = [idx for idx, l in enumerate(blk[1]) if l.strip() and not MARKER.match(l.strip())]
        only_markers = re.sub(r"%%.*?%%", "", text, flags=re.S).strip() == ""
        before = [mm for idx, mm in markers if not content_idx or idx < content_idx[0]]
        after = [mm for idx, mm in markers if content_idx and idx > content_idx[0]]
        for mm in before:
            events.append((mm.group(1)[4:], mm.group(2)))
        if not only_markers:
            events.append(("el", chunk))
        for mm in after:
            events.append((mm.group(1)[4:], mm.group(2)))

    # costruzione annidata
    out = []
    stack = []  # ogni livello: {"cols": [(args, [html])], "args": ...}
    def emit(x):
        if stack and stack[-1]["cols"]:
            stack[-1]["cols"][-1][1].append(x)
        elif stack:
            stack[-1]["pre"].append(x)
        else:
            out.append(x)
    def render(level):
        _, cst = parse_args(level["args"])
        cont_css = {}
        if "bg" in cst: cont_css["--columns-block-bg"] = BG[cst["bg"]]
        if "bc" in cst: cont_css["--columns-block-border-color"] = COL[cst["bc"]]
        parts = ['<div class="columns-container columns-ui columns-reading columns-site%s"%s>' % (
            " columns-custom-style" if cont_css else "", style_attr(cont_css))]
        cols = level["cols"]
        total = sum(parse_args(a)[0] for a, _ in cols)
        for ci, (args, items) in enumerate(cols):
            width, st = parse_args(args)
            if total > 100:
                width = 0
            if ci > 0 and parse_args(cols[ci - 1][0])[1].get("sep"):
                pst = parse_args(cols[ci - 1][0])[1]
                sep_css = {"--sep-color": COL[pst.get("sc", "gray")]}
                if "sw" in pst: sep_css["--sep-width"] = "%dpx" % pst["sw"]
                if pst.get("ss") in ("solid", "dashed", "dotted", "double"): sep_css["--sep-style"] = pst["ss"]
                parts.append('<div class="column-separator-visual"%s></div>' % style_attr(sep_css))
            css = col_style(st)
            flex = ("flex:0 1 calc(%g%% - 16px)" % width) if width > 0 else ""
            parts.append('<div class="column-item%s"%s><div class="column-preview markdown-rendered">' % (
                " columns-custom-style" if css else "", style_attr(css, flex)))
            parts.extend(items)
            parts.append("</div></div>")
        parts.append("</div>")
        return "".join(level["pre"]) + "".join(parts)
    for kind, val in events:
        if kind == "el":
            emit(val)
        elif kind == "start":
            stack.append({"args": val, "cols": [], "pre": []})
        elif kind == "break":
            if stack:
                stack[-1]["cols"].append((val, []))
        elif kind == "end":
            if stack:
                lvl = stack.pop()
                emit(render(lvl))
    while stack:  # col-start senza col-end: chiude comunque
        emit(render(stack.pop()))

    first, last = els[0][0], els[-1][1]
    s = s[:first] + "".join(out) + s[last:]
    return s, True

# ---------------------------------------------------------------- grafici
GRAPH_DIV = re.compile(r'<div class="block-language-(graph3d|graph)"[^>]*>')

def md_graphs(md_text):
    out, lines, i = [], md_text.split("\n"), 0
    while i < len(lines):
        m = re.match(r"^((?:\s*>)*\s*)(`{3,}|~{3,})\s*(graph3d|graph)\s*$", lines[i])
        if m:
            prefix_re = re.compile(r"^(?:\s*>)*\s?")
            fence = m.group(2); body = []; j = i + 1
            depth = m.group(1).count(">")
            while j < len(lines):
                l = lines[j]
                stripped = l
                for _ in range(depth):
                    stripped = re.sub(r"^\s*>\s?", "", stripped, count=1)
                if stripped.strip().startswith(fence):
                    break
                body.append(stripped); j += 1
            out.append((m.group(3), "\n".join(body)))
            i = j + 1; continue
        i += 1
    return out

def fix_graphs(s, md_text, log):
    found = list(GRAPH_DIV.finditer(s))
    if not found:
        return s, False
    defs = md_graphs(md_text)
    if len(defs) != len(found):
        log("  grafici saltati: %d nell'HTML, %d nella nota" % (len(found), len(defs)))
        return s, False
    pieces, pos = [], 0
    for m, (kind, src) in zip(found, defs):
        end = match_div(s, m.start())
        b64 = base64.b64encode(src.encode("utf-8")).decode("ascii")
        pieces.append(s[pos:m.start()])
        pieces.append('<div class="site-graph" data-g3d="%d" data-src="%s"></div>' % (1 if kind == "graph3d" else 0, b64))
        pos = end
    pieces.append(s[pos:])
    return "".join(pieces), True

# ---------------------------------------------------------------- pagina
def process_page(path, md_path, log):
    s = open(path, encoding="utf-8").read()
    orig = s
    md_text = open(md_path, encoding="utf-8").read() if md_path and os.path.exists(md_path) else ""
    # AMC nascondeva gli elementi originali: via le sue classi
    s = s.replace(" amc-rv-hidden", "").replace("amc-rv-hidden ", "").replace(' class="amc-rv-hidden"', "")
    s = s.replace(" amc-reading-columns-active", "")
    if md_text:
        s, _ = fix_graphs(s, md_text, log)
        s, _ = build_columns(s, md_text, log)
    if MARK not in s and "</head>" in s:
        s = s.replace("</head>", HEAD_INJECT + "</head>", 1)
    if s != orig:
        open(path, "w", encoding="utf-8").write(s)
        return True
    return False

def compress_images():
    """PNG pesanti in allegati/: ridimensiona (max 1600px) e riduce a 256 colori.
    Gia' compresse = PNG a palette, quindi rilanciare non le tocca."""
    try:
        from PIL import Image
    except ImportError:
        print("Pillow non installato: immagini non compresse"); return
    folder = os.path.join(SITE, "allegati")
    if not os.path.isdir(folder):
        return
    done = saved = 0
    for f in os.listdir(folder):
        if not f.lower().endswith(".png"):
            continue
        p = os.path.join(folder, f)
        s0 = os.path.getsize(p)
        if s0 < 150_000:
            continue
        try:
            im = Image.open(p)
            if im.mode == "P":
                continue
            im.load()
            im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "PA") else "RGB")
            w, h = im.size
            if w > 1600:
                im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
            q = im.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
            import io
            b = io.BytesIO(); q.save(b, "PNG", optimize=True)
            if b.tell() < s0 * 0.9:
                open(p, "wb").write(b.getvalue()); done += 1; saved += s0 - b.tell()
        except Exception as e:
            print("immagine saltata:", f, e)
    if done:
        print("immagini compresse: %d (%.0f MB risparmiati)" % (done, saved / 1e6))

def update_graphs_engine():
    src = os.path.join(VAULT, ".obsidian", "plugins", "graphs", "main.js")
    dst = os.path.join(SITE, "extra", "graphs-plugin.js")
    if os.path.exists(src):
        data = open(src, "rb").read()
        if not os.path.exists(dst) or open(dst, "rb").read() != data:
            open(dst, "wb").write(data); print("motore grafici aggiornato")

def main():
    if not sys.argv[3:]:
        compress_images()
        update_graphs_engine()
    meta = json.load(open(os.path.join(SITE, "site-lib", "metadata.json"), encoding="utf-8"))
    targets = {}
    for src, tgt in meta.get("sourceToTarget", {}).items():
        if tgt.endswith(".html") and src.endswith(".md"):
            targets[tgt] = os.path.join(VAULT, src)
    changed = 0
    only = set(sys.argv[3:])
    for tgt, md in sorted(targets.items()):
        if only and tgt not in only:
            continue
        p = os.path.join(SITE, tgt)
        if not os.path.exists(p):
            continue
        msgs = []
        try:
            if process_page(p, md, msgs.append):
                changed += 1
        except Exception as e:
            msgs.append("  ERRORE: %r" % e)
        if msgs:
            print(tgt); [print(x) for x in msgs]
    # index.html e altre pagine fuori dalla mappa
    print("pagine modificate:", changed)

if __name__ == "__main__":
    main()
