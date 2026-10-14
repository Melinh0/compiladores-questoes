#!/usr/bin/env python3
"""Extrai o PDF compilado de questões para uma fonte estruturada.

Gera:
  data/source.json  - seções, questões, parágrafos, listas, código e figuras
  data/figs/*.png   - figuras (prints/gabaritos) extraídas do PDF

A fonte estruturada é o arquivo versionável: o PDF final é sempre
reconstruído a partir dela (ver src/build_document.py).

A fonte é a versão anterior à correção (data/_fonte_pre_correcao.pdf), guardada
para que a reconstrução seja sempre reproduzível.

Uso:
  python3 src/extract_document.py [--pdf data/_fonte_pre_correcao.pdf] [--out data/source.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import pymupdf

# Sentinelas de formatação inline (evitam colidir com *, ` ou & do texto).
B, BE = "\x01", "\x02"  # negrito
C, CE = "\x03", "\x04"  # monoespaçado (código)

FOOTER_MARK = "Compiladores — Questões e Resoluções"

# ---------------------------------------------------------------- utilidades


def markup(spans) -> str:
    """Converte spans de uma linha em texto com sentinelas de estilo."""
    out = []
    for s in spans:
        t = s["text"]
        if not t:
            continue
        font = s["font"]
        mono = "Consolas" in font or "Courier" in font or "Mono" in font
        bold = "Bold" in font or bool(s["flags"] & 16)
        if mono:
            out.append(C + t + CE)
        elif bold:
            out.append(B + t + BE)
        else:
            out.append(t)
    return "".join(out)


def balance(text: str) -> str:
    """Garante sentinelas de estilo fechadas dentro do trecho."""
    pairs = ((B, BE), (C, CE))
    for op, cl in pairs:
        if text.count(op) > text.count(cl):
            text += cl * (text.count(op) - text.count(cl))
        elif text.count(cl) > text.count(op):
            text = op * (text.count(cl) - text.count(op)) + text
    return text


def plain(text: str) -> str:
    return re.sub(r"[\x01-\x04]", "", text)


# ------------------------------------------------------- regras de segmentação

RE_BULLET = re.compile(r"^\s*[•▪◦]\s*")
RE_DASH = re.compile(r"^\s*[-–—]\s+")
RE_ITEM_PAREN = re.compile(r"^\s*\(?[a-zA-Z0-9]{1,4}\)[\.\s–-]")
RE_ITEM_NUM = re.compile(r"^\s*\d{1,2}[\.\)]\s")
RE_LABEL_LOWER = re.compile(r"^\s*[a-zà-ú0-9_]{1,6}[:)]")
RE_LABEL_CAP = re.compile(
    r"^\s*[A-ZÀ-Ú][A-Za-zÀ-ú0-9]{1,20}(\s+[A-Za-zÀ-ú0-9()«\"'{\[]+){0,2}\s*[:\-–(«]"
)
RE_LABEL_WORD = re.compile(
    r"^\s*(Passo\d|Bloco\s*\d|Estado\s+\d|Deriva[çc]ão|Leitura|Nota|NOTA|Figura|"
    r"Tabela|Exemplo|Exemplos|Ou\s+seja|L[íi]ngua|Lingua|Resumo|Gram[áa]tica|"
    r"Exercise|Exercises|Question|Questão|Resolução|Enunciado|Origem|Nota\()"
)
RE_CODE = re.compile(
    r"(::=|:=|->|=>|^\s*\{|^\s*\}|^\s*<corpo|^\s*%|"
    r"^\s*(int|long|char|boolean|double|public|private|protected|static|final|void|"
    r"return|else|elif|label|goto|iffalse|elif|movl|movq|pushl|pushq|popl|popq|call|"
    r"jmp|addl|subl|mov|push|pop|add|sub|cmp|lea)\b|"
    r"^\s*[A-Za-z_][A-Za-z0-9_]{0,15}\s*=\s|"
    r"^\s*[A-Za-z_][A-Za-z0-9_]{0,20}\s*\+=)"
)
RE_PIPE = re.compile(r"\s\|\s|\|\s*$")


def is_bullet(line: str) -> bool:
    return bool(RE_BULLET.match(line))


def starts_new(prev: str, line: str) -> bool:
    """Decide se `line` inaugura um novo item dentro de um bloco de texto."""
    p = plain(prev).rstrip()
    s = plain(line).strip()
    if not s:
        return True
    if RE_BULLET.match(line) or RE_DASH.match(line):
        return True
    if RE_ITEM_PAREN.match(s) or RE_ITEM_NUM.match(s):
        return True
    if RE_PIPE.search(s):
        return True
    if RE_CODE.search(s):
        return True
    if p.endswith((",", ";")) and (RE_LABEL_LOWER.match(s) or RE_LABEL_CAP.match(s)):
        # "…; a: …" / "…; equivalente: …" (curto) continua; rótulo novo = quebra
        if RE_LABEL_LOWER.match(s) and len(plain(s).split(":")[0]) > 6:
            return False
    if p.endswith(":"):
        return True
    if RE_LABEL_LOWER.match(s):
        return True
    if RE_LABEL_CAP.match(s) and (p.endswith((".", "?", "!", ")", "”")) or p.endswith(":")):
        return True
    if RE_LABEL_WORD.match(s) and (p.endswith((".", "?", "!", ")", "”")) or p.endswith(":")):
        return True
    if p.endswith(")") and len(p) < 90 and s[:1].isupper():
        return True
    return False


def segment(lines: list[dict]) -> list[dict]:
    """Quebra um bloco de texto em itens (parágrafos/listas/código)."""
    items: list[dict] = []
    cur: dict | None = None
    for ln in lines:
        txt = ln["t"].strip()
        if not txt:
            continue
        if cur is None:
            cur = dict(ln)
            continue
        if starts_new(cur["t"], txt):
            items.append(cur)
            cur = dict(ln)
        else:
            cur = {"t": balance(cur["t"].rstrip() + " " + txt), "mono": cur["mono"]}
    if cur:
        items.append(cur)
    return items


def kind_of_item(text: str, mono_ratio: float) -> str:
    if mono_ratio > 0.6:
        return "code"
    if RE_BULLET.match(text):
        return "li"
    if RE_ITEM_PAREN.match(plain(text)) or RE_ITEM_NUM.match(plain(text)):
        return "item"
    return "p"


def md_bold(text: str) -> str:
    """Converte negrito literal **texto** (herdado da fonte) em sentinela de negrito.

    Só é aplicado fora de trechos de código e apenas quando há exatamente um par,
    para não confundir com o operador de potência ** de uma gramática.
    """
    parts = re.split(r"(\x03[^\x04]*\x04)", text)
    prose = [p for i, p in enumerate(parts) if i % 2 == 0]
    if sum(p.count("**") for p in prose) != 2:
        return text
    out, n = [], 0
    for i, part in enumerate(parts):
        if i % 2:
            out.append(part)
            continue
        buf, k = [], 0
        while True:
            j = part.find("**", k)
            if j < 0:
                buf.append(part[k:])
                break
            buf.append(part[k:j])
            buf.append(B if n == 0 else BE)
            n += 1
            k = j + 2
        out.append("".join(buf))
    return "".join(out)


def row_cells(lines: list[dict]) -> list[str] | None:
    """Uma linha de tabela: todas as 'linhas' do bloco estão na mesma altura.

    O PDF da fonte descreve cada célula como uma linha própria (PyMuPDF as
    separa por causa do vão horizontal), então células lado a lado compartilham
    a mesma y. Código e prosa, em contraste, empilham as linhas na vertical.
    """
    if not (2 <= len(lines) <= 12):
        return None
    ys = [l["y0"] for l in lines]
    if max(ys) - min(ys) > 1.5:
        return None
    cells = [l["t"].strip() for l in sorted(lines, key=lambda l: l["x0"])]
    if any(len(c) > 70 for c in cells):
        return None
    return cells


def looks_code(text: str) -> bool:
    s = plain(text).strip()
    if RE_BULLET.match(s) or RE_ITEM_PAREN.match(s) or RE_ITEM_NUM.match(s):
        return False
    if len(s) > 160:
        return False
    return bool(RE_CODE.search(s))


def merge_code_paragraphs(blocks: list[dict]) -> None:
    """Agrupa parágrafos consecutivos que são código em um único bloco pré-formatado."""
    out: list[dict] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.get("k") == "p" and looks_code(b["t"]):
            lines = []
            j = i
            while j < len(blocks) and blocks[j].get("k") == "p" and looks_code(blocks[j]["t"]):
                lines.append(blocks[j]["t"])
                j += 1
            out.append({"k": "pre", "lines": lines})
            i = j
        else:
            out.append(b)
            i += 1
    blocks[:] = out


# --------------------------------------------------------------- extração


def extract(pdf_path: str, out_json: str, figs_dir: str) -> dict:
    doc = pymupdf.open(pdf_path)
    os.makedirs(figs_dir, exist_ok=True)

    figs: dict[int, str] = {}
    sections: list[dict] = []
    cur_sec: dict | None = None
    cur_q: dict | None = None
    prev_kind: str | None = None

    def new_section(title: str, page: int):
        nonlocal cur_sec, cur_q
        cur_sec = {"id": "", "title": title, "page": page, "intro": None, "questions": []}
        sections.append(cur_sec)
        cur_q = None

    def new_question(title: str, page: int):
        nonlocal cur_q
        if cur_sec is None:
            new_section("Seção", page)
        cur_q = {"title": title, "page": page, "blocks": []}
        cur_sec["questions"].append(cur_q)

    def sink() -> list[dict]:
        nonlocal cur_q
        if cur_q is None:
            if cur_sec is None:
                new_section("Seção", 1)
            new_question("", 1)
        return cur_q["blocks"]

    # ---- tabelas: células lado a lado formam uma linha; linhas consecutivas
    #      formam a tabela.
    table_rows: list[list[str]] = []
    table_page = [0]
    table_y1 = [None]

    def flush_table():
        rows, table_rows[:] = table_rows[:], []
        table_y1[0] = None
        if not rows:
            return
        if len(rows) >= 2:
            cols = max(len(r) for r in rows)
            sink().append(
                {"k": "table", "rows": [r + [""] * (cols - len(r)) for r in rows]}
            )
        else:
            sink().append({"k": "pre", "lines": list(rows[0])})

    def try_table_row(b, lines, pno) -> bool:
        cells = row_cells(lines)
        if cells is None:
            return False
        newpage = table_page[0] != pno
        if table_rows:
            cols = max(len(r) for r in table_rows)
            if newpage and cells == table_rows[0]:
                flush_table()  # cabeçalho repetido: começa outra tabela
            elif not newpage and not (
                2 <= (b["bbox"][1] - table_y1[0]) <= 26 and len(cells) <= cols + 1
            ):
                flush_table()
        table_rows.append(cells)
        table_page[0] = pno
        table_y1[0] = b["bbox"][3]
        return True

    for pno, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        image_rects = {}
        for b in blocks:
            if b["type"] == 1:
                image_rects[tuple(round(v, 1) for v in b["bbox"])] = b
        ordered = sorted(
            [b for b in blocks if b["type"] == 0],
            key=lambda b: (round(b["bbox"][1] / 3.0), b["bbox"][0]),
        )
        image_blocks = [b for b in blocks if b["type"] == 1]

        items = [(b["bbox"][1], b["bbox"][0], b) for b in ordered]
        items += [(b["bbox"][1], b["bbox"][0], b) for b in image_blocks]
        items.sort(key=lambda t: (round(t[0] / 3.0), t[1]))

        for _, _, b in items:
            if b["type"] == 1:
                flush_table()
                fig = save_figure(doc, page, b, figs, figs_dir)
                if fig:
                    x0, y0, x1, y1 = b["bbox"]
                    sink().append(
                        {
                            "k": "img",
                            "f": fig,
                            "w": round(x1 - x0, 1),
                            "h": round(y1 - y0, 1),
                            "src": pno,
                        }
                    )
                continue

            lines = []
            for l in b["lines"]:
                t = markup(l["spans"])
                if not t.strip():
                    continue
                total = sum(len(s["text"]) for s in l["spans"])
                mono = sum(
                    len(s["text"])
                    for s in l["spans"]
                    if "Consolas" in s["font"] or "Courier" in s["font"]
                )
                bold = any(
                    "Bold" in s["font"] or (s["flags"] & 16) for s in l["spans"]
                )
                size = max(s["size"] for s in l["spans"])
                lines.append(
                    {
                        "t": t,
                        "size": round(size, 1),
                        "bold": bold,
                        "mono": (mono / total) if total else 0.0,
                        "x0": round(l["bbox"][0], 1),
                        "y0": round(l["bbox"][1], 1),
                    }
                )
            if not lines:
                continue

            head = plain(lines[0]["t"]).strip()
            if FOOTER_MARK in head and "página" in head:
                continue

            size = max(l["size"] for l in lines)
            bold_frac = sum(1 for l in lines if l["bold"]) / len(lines)
            mono_chars = sum(
                len(plain(l["t"])) * l["mono"] for l in lines
            ) / max(1, sum(len(plain(l["t"])) for l in lines))
            pipe_frac = sum(1 for l in lines if RE_PIPE.search(plain(l["t"]))) / len(lines)

            if size >= 14.0 and bold_frac > 0.6:
                flush_table()
                title = " ".join(plain(l["t"]).strip() for l in lines)
                new_section(re.sub(r"\s+", " ", title), pno)
                prev_kind = "h1"
                continue

            if 11.0 <= size < 14.0 and bold_frac > 0.6:
                flush_table()
                title = " ".join(plain(l["t"]).strip() for l in lines)
                if title.strip() == "Resolução":
                    sink().append({"k": "h3", "t": "Resolução"})
                else:
                    new_question(re.sub(r"\s+", " ", title), pno)
                prev_kind = "h2"
                continue

            if (
                size >= 10.0
                and bold_frac > 0.6
                and plain(lines[0]["t"]).strip().startswith("Resolução")
                and len(lines) == 1
            ):
                sink().append({"k": "h3", "t": plain(lines[0]["t"]).strip()})
                prev_kind = "h3"
                continue

            if size <= 9.2 and bold_frac < 0.5 and prev_kind == "h1":
                flush_table()
                text = " ".join(plain(l["t"]).strip() for l in lines)
                cur_sec["intro"] = re.sub(r"\s+", " ", text).strip()
                prev_kind = "intro"
                continue

            # linha de tabela: reconstrói a grade
            if try_table_row(b, lines, pno):
                prev_kind = "table"
                continue

            # bloco de código / tabela: preserva as linhas
            if mono_chars > 0.5 or pipe_frac > 0.5 or size <= 9.2:
                flush_table()
                sink().append(
                    {"k": "pre", "lines": [balance(plain(l["t"]).rstrip()) for l in lines]}
                )
                prev_kind = "pre"
                continue

            flush_table()
            items_txt = segment(lines)
            for it in items_txt:
                txt = it["t"].strip()
                if not txt:
                    continue
                ratio = it.get("mono", 0.0)
                k = kind_of_item(txt, ratio)
                payload = {"k": k, "t": balance(md_bold(txt))}
                if k == "code":
                    payload = {"k": "pre", "lines": [balance(md_bold(txt))]}
                sink().append(payload)
            merge_code_paragraphs(sink())
            prev_kind = "para"

    flush_table()

    # identificadores curtos das seções (usados nas referências cruzadas)
    for sec in sections:
        m = re.match(r"^([A-Za-z]\.[\w]+|[MF]\d|O\d|Exercicio\d+)\b", sec["title"])
        sec["id"] = m.group(1) if m else sec["title"].split(" ")[0]
        sec.setdefault("intro", None)

    return {"source": os.path.basename(pdf_path), "sections": sections}


def save_figure(doc, page, block, figs: dict, figs_dir: str) -> str | None:
    bbox = tuple(round(v, 1) for v in block["bbox"])
    for im in page.get_images(full=True):
        xref = im[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for r in rects:
            key = tuple(round(v, 1) for v in r)
            if key == bbox:
                if xref in figs:
                    return figs[xref]
                pix = pymupdf.Pixmap(doc, xref)
                if pix.alpha:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                elif pix.colorspace is None or pix.colorspace.n != 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                name = f"fig_{xref:04d}.png"
                pix.save(os.path.join(figs_dir, name))
                figs[xref] = f"figs/{name}"
                return figs[xref]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pdf", default="data/_fonte_pre_correcao.pdf"
    )
    ap.add_argument("--out", default="data/source.json")
    ap.add_argument("--figs", default="data/figs")
    args = ap.parse_args()

    data = extract(args.pdf, args.out, args.figs)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    n_sec = len(data["sections"])
    n_q = sum(len(s["questions"]) for s in data["sections"])
    n_blocks = sum(
        len(q["blocks"]) for s in data["sections"] for q in s["questions"]
    )
    print(f"{args.out}: {n_sec} seções, {n_q} questões, {n_blocks} blocos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
