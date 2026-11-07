#!/usr/bin/env python3
"""Gera assets/ai-kb.js (base de conhecimento da aba IA) a partir das paginas HTML
do site e dos exemplos .lua em downloads/.  Rode de novo sempre que a documentacao
mudar:   python3 tools/build_ai_kb.py
"""
import json, os, re, sys, time
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAXC = 1500
SKIP = {"referencia.html", "exemplos.html", "ia.html", "index.html"}


def norm(s):
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


def kind_of(f):
    if f.startswith("api-"): return "API"
    if f.startswith("classe-"): return "Classe"
    if f.startswith("exemplo-"): return "Exemplo"
    return "Guia"


def lines_of(el):
    """Converte um elemento em linhas de texto simples."""
    out = []
    n = getattr(el, "name", None)
    if n is None:
        t = norm(str(el))
        return [t] if t else []
    cls = el.get("class") or []
    if n == "table":
        for tr in el.find_all("tr"):
            cells = [norm(c.get_text("")) for c in tr.find_all(["th", "td"])]
            if any(cells): out.append(" | ".join(cells))
    elif n == "div" and "tw" in cls:
        for t in el.find_all("table"): out += lines_of(t)
    elif n == "pre" or ("code" in cls and n == "div"):
        pre = el.find("pre") or el
        out.append("```lua\n" + pre.get_text().strip("\n") + "\n```")
    elif n in ("ul", "ol"):
        for li in el.find_all("li"): out.append("- " + norm(li.get_text("")))
    elif n == "div" and ("cards" in cls):
        for a in el.find_all("a", class_="card"):
            out.append(norm(a.get_text(" - ")))
    elif n == "div" and ("idx" in cls or "chips" in cls):
        out.append("Itens: " + norm(el.get_text(" ")))
    elif n == "div" and "uses" in cls:
        t = norm(el.get_text(" "))
        out.append(t[:350])
    elif n == "button":
        pass
    elif n == "div" and "sig" in cls:
        out.append(norm(el.get_text("")))
    else:
        t = norm(el.get_text(""))
        if t: out.append(t)
    return out


def fn_text(sec):
    parts = []
    h3 = sec.find("h3")
    if h3: parts.append(norm(h3.get_text(" ").lstrip("#")))
    for ch in sec.children:
        if getattr(ch, "name", None) == "h3": continue
        parts += lines_of(ch)
    return "\n".join(p for p in parts if p)


def pack(lines, limit=MAXC):
    """Agrupa linhas em blocos <= limit caracteres (nunca quebra no meio de uma linha)."""
    blocks, cur, size = [], [], 0
    for ln in lines:
        if cur and size + len(ln) > limit:
            blocks.append("\n".join(cur)); cur, size = [], 0
        if len(ln) > limit * 1.6 and ln.startswith("```"):  # codigo enorme: quebra por linhas
            body = ln.split("\n")
            buf, bs = [], 0
            for b in body:
                if bs + len(b) > limit and buf:
                    if cur: blocks.append("\n".join(cur)); cur, size = [], 0
                    blocks.append("\n".join(buf)); buf, bs = [], 0
                buf.append(b); bs += len(b) + 1
            if buf: cur.append("\n".join(buf)); size += bs
            continue
        cur.append(ln); size += len(ln) + 1
    if cur: blocks.append("\n".join(cur))
    return blocks


def html_chunks(path, fname):
    soup = BeautifulSoup(open(path, encoding="utf-8").read(), "html.parser")
    art = soup.find("article")
    if not art: return []
    h1 = art.find("h1")
    title = norm(h1.get_text(" ")) if h1 else fname
    lead = art.find("p", class_="lead")
    k = kind_of(fname)
    chunks = []
    cur_h, cur_a, buf = None, None, []

    def flush():
        nonlocal buf
        if buf:
            for i, b in enumerate(pack(buf)):
                chunks.append(dict(t=title, s=cur_h or "", u=fname + (("#" + cur_a) if cur_a else ""), k=k, x=b))
        buf = []

    if lead: buf.append(norm(lead.get_text(" ")))
    for ch in art.children:
        n = getattr(ch, "name", None)
        if n in (None, "h1") or (n == "p" and "lead" in (ch.get("class") or [])): continue
        if n == "h2":
            flush(); cur_h, cur_a = norm(ch.get_text(" ")), ch.get("id"); continue
        if n == "section" and "fn" in (ch.get("class") or []):
            flush()
            txt = fn_text(ch)
            for b in pack([txt], 2400):
                chunks.append(dict(t=title, s=txt.split("\n")[0], u=fname + "#" + (ch.get("id") or ""), k=k, x=b))
            continue
        if n == "div" and "crumb" in (ch.get("class") or []): continue
        buf += lines_of(ch)
    flush()
    return chunks


def lua_chunks():
    d = os.path.join(ROOT, "downloads")
    out = []
    if not os.path.isdir(d): return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".lua"): continue
        name = f[:-4]
        src = open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
        page = "exemplo-%s.html" % name
        if not os.path.exists(os.path.join(ROOT, page)): page = "exemplos.html"
        lines, buf = [], []
        for ln in src.split("\n"):
            buf.append(ln)
            if not ln.strip() and sum(len(x) for x in buf) > 700:
                lines.append("\n".join(buf)); buf = []
        if buf: lines.append("\n".join(buf))
        parts = pack(["```lua\n" + l.strip("\n") + "\n```" for l in lines if l.strip()], 1700)
        for i, p in enumerate(parts):
            out.append(dict(t="Exemplo " + f, s="parte %d/%d" % (i + 1, len(parts)), u=page, k="Exemplo", x=p))
    return out


def overview():
    soup = BeautifulSoup(open(os.path.join(ROOT, "index.html"), encoding="utf-8").read(), "html.parser")
    lines = ["MODULOS DE API (nome - o que faz):"]
    for h3 in soup.select("article > h3"):
        cards = h3.find_next_sibling("div", class_="cards")
        if not cards or h3.get_text() == "Objetos": continue
        for a in cards.find_all("a", class_="card"):
            b, sp = a.find("b"), a.find("span")
            lines.append("- %s: %s" % (norm(b.get_text()), norm(sp.get_text()) if sp else ""))
    soup = BeautifulSoup(open(os.path.join(ROOT, "classes.html"), encoding="utf-8").read(), "html.parser")
    lines.append("\nCLASSES create.* (nome - o que faz):")
    for a in soup.select(".cards a.card"):
        b, sp = a.find("b"), a.find("span")
        lines.append("- %s: %s" % (norm(b.get_text()), norm(sp.get_text()) if sp else ""))
    return "\n".join(lines)


def main():
    chunks = []
    for f in sorted(os.listdir(ROOT)):
        if not f.endswith(".html") or f in SKIP: continue
        if f.startswith("exemplo-"):
            # Codigo vem de downloads/*.lua; aqui so a descricao curta
            soup = BeautifulSoup(open(os.path.join(ROOT, f), encoding="utf-8").read(), "html.parser")
            h1, lead, chips = soup.find("h1"), soup.find("p", class_="lead"), soup.find("div", class_="chips")
            chunks.append(dict(t="Exemplo " + (norm(h1.get_text()) if h1 else f), s="resumo", u=f, k="Exemplo",
                               x="APIs usadas: " + (norm(chips.get_text(" ")) if chips else "") + "\n" + (norm(lead.get_text()) if lead else "")))
            continue
        chunks += html_chunks(os.path.join(ROOT, f), f)
    chunks += lua_chunks()
    for i, c in enumerate(chunks): c["i"] = i
    kb = dict(built=time.strftime("%Y-%m-%d"), overview=overview(), chunks=chunks)
    dst = os.path.join(ROOT, "assets", "ai-kb.js")
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("window.LS_KB=" + json.dumps(kb, ensure_ascii=False, separators=(",", ":")) + ";")
    print("chunks:", len(chunks), "| bytes:", os.path.getsize(dst))


if __name__ == "__main__":
    main()
