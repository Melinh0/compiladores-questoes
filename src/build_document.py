#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Frame,
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    Spacer,
    BaseDocTemplate,
    PageTemplate,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WIN_FONTS = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")


def _first_font(*candidates: str) -> str:
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "Nenhuma fonte encontrada. Tentei:\n  " + "\n  ".join(candidates)
    )


SANS = _first_font(
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    os.path.join(_WIN_FONTS, "arial.ttf"),
)
SANS_B = _first_font(
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    os.path.join(_WIN_FONTS, "arialbd.ttf"),
)
MONO = _first_font(
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    os.path.join(_WIN_FONTS, "cour.ttf"),
)
SYM = _first_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    os.path.join(_WIN_FONTS, "seguisym.ttf"),
)

PAGE_W, PAGE_H = A4
LM = RM = 57.6
TM = 60
BM = 64
CONTENT_W = PAGE_W - LM - RM


pdfmetrics.registerFont(TTFont("Sans", SANS))
pdfmetrics.registerFont(TTFont("Sans-Bold", SANS_B))
pdfmetrics.registerFont(TTFont("Mono", MONO))
pdfmetrics.registerFont(TTFont("Sym", SYM))
pdfmetrics.registerFontFamily(
    "Sans", normal="Sans", bold="Sans-Bold", italic="Sans", boldItalic="Sans-Bold"
)

_fallback = None


def fallback_chars() -> set[str]:
    global _fallback
    if _fallback is None:
        from fontTools.ttLib import TTFont as _TT

        cmap = _TT(SANS, lazy=True).getBestCmap()
        _fallback = set()
        with open(os.path.join(ROOT, "data", "source.json"), encoding="utf-8") as fh:
            for ch in fh.read():
                if ord(ch) > 127 and ord(ch) not in cmap:
                    _fallback.add(ch)
        _fallback |= {"∅", "∈", "∪", "⊕", "␣", "✓", "✗"}
    return _fallback



THEMES = {
    "light": {
        "PAGE_BG": "#FFFFFF",
        "INK": "#12263F",
        "BLUE": "#0B3D6E",
        "GRUPO": "#14507F",
        "GREEN": "#1F6F45",
        "GREY": "#555555",
        "RULE": "#C9D4E0",
        "ACCENT": "#E3C15A",
        "NOTE_BG": "#FFF6DC",
        "NOTE_BD": "#E3C15A",
        "NOTE_INK": "#5A4400",
        "PRE_INK": "#101010",
        "PRE_BG": "#F2F4F6",
        "BODY_INK": "#000000",
        "TBL_HEAD_BG": "#E9EFF6",
        "FOOTER_INK": "#7A8896",
        "TOC_DOT": "#9AA7B4",
    },
    "dark": {
        "PAGE_BG": "#12161C",
        "INK": "#E6EDF3",
        "BLUE": "#7DB4E8",
        "GRUPO": "#8FC0EC",
        "GREEN": "#6FCF97",
        "GREY": "#A8B3BF",
        "RULE": "#2E3A47",
        "ACCENT": "#D4B45A",
        "NOTE_BG": "#2A2617",
        "NOTE_BD": "#8A7430",
        "NOTE_INK": "#EAD9A0",
        "PRE_INK": "#E0E6EC",
        "PRE_BG": "#1B222B",
        "BODY_INK": "#DDE4EB",
        "TBL_HEAD_BG": "#1C2733",
        "FOOTER_INK": "#7A8896",
        "TOC_DOT": "#5A6774",
    },
}

S: dict = {}
THEME = "light"


def apply_theme(name: str) -> None:
    global THEME
    global PAGE_BG, INK, BLUE, GRUPO, GREEN, GREY, RULE, ACCENT
    global NOTE_BG, NOTE_BD, NOTE_INK, PRE_INK, PRE_BG, BODY_INK
    global TBL_HEAD_BG, FOOTER_INK, TOC_DOT
    pal = THEMES[name]
    THEME = name
    PAGE_BG = colors.HexColor(pal["PAGE_BG"])
    INK = colors.HexColor(pal["INK"])
    BLUE = colors.HexColor(pal["BLUE"])
    GRUPO = colors.HexColor(pal["GRUPO"])
    GREEN = colors.HexColor(pal["GREEN"])
    GREY = colors.HexColor(pal["GREY"])
    RULE = colors.HexColor(pal["RULE"])
    ACCENT = colors.HexColor(pal["ACCENT"])
    NOTE_BG = colors.HexColor(pal["NOTE_BG"])
    NOTE_BD = colors.HexColor(pal["NOTE_BD"])
    NOTE_INK = colors.HexColor(pal["NOTE_INK"])
    PRE_INK = colors.HexColor(pal["PRE_INK"])
    PRE_BG = colors.HexColor(pal["PRE_BG"])
    BODY_INK = colors.HexColor(pal["BODY_INK"])
    TBL_HEAD_BG = colors.HexColor(pal["TBL_HEAD_BG"])
    FOOTER_INK = colors.HexColor(pal["FOOTER_INK"])
    TOC_DOT = pal["TOC_DOT"]

    S.clear()
    S["title"] = ParagraphStyle("title", fontName="Sans-Bold", fontSize=27, leading=32,
                                textColor=BLUE, alignment=TA_LEFT, spaceAfter=10)
    S["subtitle"] = ParagraphStyle("subtitle", fontName="Sans", fontSize=13, leading=18,
                                   textColor=INK, spaceAfter=6)
    S["cover_meta"] = ParagraphStyle("cover_meta", fontName="Sans", fontSize=9.5, leading=14,
                                     textColor=GREY, spaceAfter=4)
    S["h2big"] = ParagraphStyle("h2big", fontName="Sans-Bold", fontSize=16, leading=20,
                                textColor=BLUE, spaceBefore=10, spaceAfter=8,
                                keepWithNext=True)
    S["parte"] = ParagraphStyle("parte", fontName="Sans-Bold", fontSize=24, leading=29,
                                textColor=BLUE, spaceBefore=70, spaceAfter=12)
    S["parte_desc"] = ParagraphStyle("parte_desc", fontName="Sans", fontSize=11, leading=16,
                                     textColor=INK, spaceAfter=8)
    S["grupo"] = ParagraphStyle("grupo", fontName="Sans-Bold", fontSize=13, leading=17,
                                textColor=GRUPO, spaceBefore=16,
                                spaceAfter=5, keepWithNext=True)
    S["grupo_note"] = ParagraphStyle("grupo_note", fontName="Sans", fontSize=9, leading=12.5,
                                     textColor=GREY, spaceAfter=8, leftIndent=8)
    S["h1"] = ParagraphStyle("h1", fontName="Sans-Bold", fontSize=14.5, leading=18,
                             textColor=BLUE, spaceBefore=4, spaceAfter=6, keepWithNext=True)
    S["intro"] = ParagraphStyle("intro", fontName="Sans", fontSize=9, leading=12.5,
                                textColor=GREY, spaceAfter=10, alignment=TA_JUSTIFY)
    S["h2"] = ParagraphStyle("h2", fontName="Sans-Bold", fontSize=12, leading=15,
                             textColor=INK, spaceBefore=15, spaceAfter=5, keepWithNext=True)
    S["h3"] = ParagraphStyle("h3", fontName="Sans-Bold", fontSize=10.5, leading=13.5,
                             textColor=GREEN, spaceBefore=9,
                             spaceAfter=3, keepWithNext=True)
    S["body"] = ParagraphStyle("body", fontName="Sans", fontSize=10, leading=13.6,
                               textColor=BODY_INK, spaceAfter=6, alignment=TA_JUSTIFY)
    S["item"] = ParagraphStyle("item", parent=S["body"], spaceAfter=4, alignment=TA_LEFT)
    S["li"] = ParagraphStyle("li", parent=S["body"], leftIndent=14, bulletIndent=2,
                             spaceAfter=3, alignment=TA_LEFT)
    S["pre"] = ParagraphStyle("pre", fontName="Mono", fontSize=8.6, leading=11.4,
                              textColor=PRE_INK, backColor=PRE_BG,
                              borderPadding=(6, 7, 6, 7), spaceBefore=2, spaceAfter=7,
                              alignment=TA_LEFT, wordWrap="CJK")
    S["note"] = ParagraphStyle("note", fontName="Sans", fontSize=9.4, leading=13,
                               textColor=NOTE_INK, backColor=NOTE_BG,
                               borderColor=NOTE_BD, borderWidth=0.8, borderPadding=(7, 8, 7, 8),
                               spaceBefore=4, spaceAfter=8, leftIndent=0, rightIndent=0)
    S["td"] = ParagraphStyle("td", fontName="Sans", fontSize=8.5, leading=10.6,
                             textColor=BODY_INK)
    S["tdh"] = ParagraphStyle("tdh", fontName="Sans-Bold", fontSize=8.5, leading=10.6,
                              textColor=INK)
    S["toc0"] = ParagraphStyle("toc0", fontName="Sans-Bold", fontSize=11.5, leading=17,
                               textColor=BLUE, spaceBefore=8)
    S["toc1"] = ParagraphStyle("toc1", fontName="Sans-Bold", fontSize=10, leading=14.5,
                               textColor=INK, leftIndent=10)
    S["toc2"] = ParagraphStyle("toc2", fontName="Sans", fontSize=9.6, leading=13.5,
                               textColor=INK, leftIndent=24)
    S["toc3"] = ParagraphStyle("toc3", fontName="Sans", fontSize=9, leading=12.4,
                               textColor=GREY, leftIndent=42)
    S["footer"] = ParagraphStyle("footer", fontName="Sans", fontSize=8, leading=10,
                                 textColor=FOOTER_INK)


apply_theme("light")

from reportlab.lib.enums import TA_CENTER


PARTS = [
    {
        "title": "PARTE I — PROVAS DO MEIO DE PERÍODO (MIDTERMS)",
        "desc": [
            "Todas as questões de prova do meio do material, reunidas num único bloco: "
            "as provas do Prof. André (parciais), as provas oficiais CSE401 de meio de "
            "período e as provas complementares de conteúdo de meio.",
            "Se você está copiando questões de prova do meio para o caderno, copie "
            "desta parte — ela termina na página em que começa a Parte II.",
        ],
        "groups": [
            {
                "title": "1. Provas do Professor André (provas parciais)",
                "note": (
                    "As três provas do Prof. André presentes no material. A 1ª e a 2ª "
                    "vêm com o gabarito oficial resolvido em inglês; a Prova Parcial 1 - "
                    "2023.1 veio em português (fotos do gabarito impresso)."
                ),
                "sections": ["I.1", "I.2", "I.3"],
            },
            {
                "title": "2. Provas oficiais CSE401 — midterms",
                "note": "Classificação herdada da pasta de origem “Provas mid” (inverno 2008, 2009, 2010 e outono 2010).",
                "sections": ["M1", "M2", "M3", "M4"],
            },
            {
                "title": "3. Provas complementares de meio",
                "note": (
                    "au02 e au05 não trazem rótulo de meio/final na fonte; entraram aqui "
                    "porque a prova inteira cobra assuntos de meio de período — expressões "
                    "regulares, scanner, gramáticas, ambiguidade, LR parsing, FIRST/FOLLOW "
                    "e AST (uma única questão, a 9 de au05, é de quadro de pilha)."
                ),
                "sections": ["O1", "O2"],
            },
        ],
    },
    {
        "title": "PARTE II — PROVAS FINAIS",
        "desc": [
            "Todas as questões de prova final do material, reunidas num único bloco: "
            "as provas oficiais CSE401 de final e as provas complementares de conteúdo "
            "de final.",
            "Assuntos típicos desta parte: estruturas de dados em tempo de execução, "
            "geração de código x86/x86-64, quadro de pilha, alocação de registradores, "
            "análise de fluxo, SSA, otimização e agendamento de instruções.",
        ],
        "groups": [
            {
                "title": "1. Provas oficiais CSE401 — finais",
                "note": "Classificação herdada da pasta de origem “Provas finals” (inverno 2009, 2010 e outono 2010).",
                "sections": ["F1", "F2", "F3"],
            },
            {
                "title": "2. Provas complementares de final",
                "note": (
                    "wi08, au09 e au11 não trazem rótulo de meio/final na fonte; entraram "
                    "aqui por cobrirem o curso inteiro — a prova começa em expressão regular "
                    "e termina em x86, alocação de registradores, fluxo de dados e agendamento."
                ),
                "sections": ["O3", "O4", "O5"],
            },
        ],
    },
    {
        "title": "PARTE III — EXERCÍCIOS DOS SLIDES (COM SOLUÇÕES)",
        "desc": [
            "Exercícios marcados como “Exercise” nos slides da aula, com enunciado do "
            "slide e resolução passo a passo. Não são questões de prova, mas fecham o "
            "material e caem nos mesmos assuntos.",
        ],
        "groups": [
            {
                "title": "Exercícios dos slides",
                "sections": ["Exercicio1", "Exercicio2", "Exercicio3", "Exercicio4", "Exercicio5"],
            }
        ],
    },
]

SEC_TITLES = {
    "I.1": "I.1 — Primeira Prova do André · prova do meio (gabarito oficial, inglês)",
    "I.2": "I.2 — Segunda Prova do André · prova do meio (gabarito oficial, inglês)",
    "I.3": "I.3 — Outra primeira prova: Prova Parcial 1 - 2023.1 · prova do meio",
    "M1": "M1 — CSE401 midterm inverno 2008",
    "M2": "M2 — CSE401 midterm inverno 2009",
    "M3": "M3 — CSE401 midterm inverno 2010",
    "M4": "M4 — CSE401 midterm outono 2010",
    "F1": "F1 — CSE401 final inverno 2009",
    "F2": "F2 — CSE401 final inverno 2010",
    "F3": "F3 — CSE401 final outono 2010",
    "O1": "O1 — Prova au02 (outono de 2002) · prova do meio",
    "O2": "O2 — Prova au05 (outono de 2005) · prova do meio",
    "O3": "O3 — CSEP501 inverno 2008 · prova final",
    "O4": "O4 — CSEP501 outono 2009 · prova final",
    "O5": "O5 — CSEP501 outono 2011 · prova final",
    "Exercicio1": "Exercício 1 — Gramática ambígua de expressões aritméticas (slide C-grammars)",
    "Exercicio2": "Exercício 2 — Dangling else (slide C-grammars)",
    "Exercicio3": "Exercício 3 — Que linguagem esta gramática gera? (slide E-lr-construction)",
    "Exercicio4": "Exercício 4 — Arrays 2-D: Fortran × C (slide K-codeshape-1)",
    "Exercicio5": "Exercício 5 — Grafo de interferência e coloração (slide N-backend)",
}

DUPES = [
    ("I.3", "Questão 3", "I.1", "Questão 2"),
    ("M2", "Pergunta 1", "I.1", "Questão 1"),
    ("M2", "Pergunta 3", "I.3", "Questão 2"),
    ("M2", "Pergunta 4", "I.1", "Questão 4"),
    ("M3", "Questão 1", "I.1", "Questão 3"),
    ("M3", "Questão 2", "I.1", "Questão 2"),
    ("M3", "Questão 4", "I.3", "Questão 4"),
    ("M3", "Questão 7", "I.2", "Questão 7 (16 pontos)"),
    ("F2", "Pergunta 1", "I.2", "Questão 1"),
    ("F2", "Pergunta 7", "I.2", "Questão 7 (12 pontos)"),
    ("O2", "Questão 5", "M3", "Questão 5"),
]

NOTE_FINAL = (
    "<b>Nota — fontes e critério desta edição.</b> Fontes: pasta <font face=\"Mono\">Compiladores</font> "
    "extraída de <font face=\"Mono\">Compiladores.zip</font> — <font face=\"Mono\">exames\\Provas de Washington\\"
    "Provas mid</font> e <font face=\"Mono\">Provas finals</font> (classificação oficial de meio/final), "
    "<font face=\"Mono\">exames\\Provas Andre</font> (gabaritos das provas do Prof. André) e "
    "<font face=\"Mono\">Slides\\*.pdf</font> (exercícios da Parte III). "
    "Critério de classificação: provas com rótulo de origem foram mantidas no grupo de origem; as cinco provas "
    "sem rótulo (au02, au05, wi08, au09, au11) foram classificadas pelo conteúdo predominante, como explicado na "
    "página de organização. Critério de repetições: quando a mesma questão aparece duas vezes, fica a primeira "
    "ocorrência e a segunda vira uma nota de referência (o enunciado e a resolução não foram duplicados). "
    "Critério de texto: fim de linha no meio da frase foi removido, listas e rótulos ganharam a quebra de linha "
    "que faltava, e código/figuras foram preservados como no original."
)



def plain(text: str) -> str:
    return re.sub(r"[\x01-\x04]", "", text)


def esc(ch: str) -> str:
    if ch == "&":
        return "&amp;"
    if ch == "<":
        return "&lt;"
    if ch == ">":
        return "&gt;"
    return ch


def to_xml(text: str) -> str:
    fb = fallback_chars()
    out = []
    for ch in text:
        if ch == "\x01":
            out.append("<b>")
        elif ch == "\x02":
            out.append("</b>")
        elif ch == "\x03":
            out.append('<font face="Mono">')
        elif ch == "\x04":
            out.append("</font>")
        elif ch in fb:
            out.append(f'<font face="Sym">{esc(ch)}</font>')
        else:
            out.append(esc(ch))
    return "".join(out)


def toc_line(level: int, text: str, page) -> Paragraph:
    style = S[f"toc{min(level, 3)}"]
    page_str = str(page)
    dot = "."
    text_w = pdfmetrics.stringWidth(text, style.fontName, style.fontSize)
    page_w = pdfmetrics.stringWidth(page_str, style.fontName, style.fontSize)
    dot_w = pdfmetrics.stringWidth(dot, style.fontName, style.fontSize)
    avail = CONTENT_W - style.leftIndent - page_w - 10
    ndots = int(max(0.0, avail - text_w) / dot_w)
    dots = f'<font color="{TOC_DOT}">{dot * ndots}</font> ' if ndots else " "
    return Paragraph(f"{to_xml(text)}{dots}{esc(page_str)}", style)


def qkey(sec_id: str, title: str) -> str:
    return f"{sec_id}|{title}"


def same_title(title: str, prefix: str) -> bool:
    if not title.startswith(prefix):
        return False
    rest = title[len(prefix):]
    return not (rest and rest[0].isdigit())


class Mark(Flowable):

    def __init__(self, key: str, pages: dict):
        super().__init__()
        self.key = key
        self.pages = pages
        self.width = 0
        self.height = 0

    def draw(self):
        self.pages[self.key] = self.canv.getPageNumber()



class Doc(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, pagesize=A4,
                         leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM, **kw)
        frame = Frame(LM, BM, CONTENT_W, PAGE_H - TM - BM, id="body",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                            onPage=self._footer)])

    @staticmethod
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(PAGE_BG)
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(LM, BM - 16, PAGE_W - RM, BM - 16)
        canvas.setFont("Sans", 8)
        canvas.setFillColor(FOOTER_INK)
        canvas.drawCentredString(PAGE_W / 2.0, BM - 30,
                                 f"Compiladores — Questões e Resoluções  |  página {canvas.getPageNumber()}")
        canvas.restoreState()


def make_table(rows: list[list[str]]):
    from reportlab.platypus import Table, TableStyle

    head = [Paragraph(to_xml(c) if c.strip() else " ", S["tdh"]) for c in rows[0]]
    body = [
        [Paragraph(to_xml(c) if c.strip() else " ", S["td"]) for c in r]
        for r in rows[1:]
    ]
    widths = []
    for i in range(len(rows[0])):
        w = max(
            pdfmetrics.stringWidth(plain(c), "Sans", 8.5) for c in (r[i] for r in rows)
        )
        widths.append(min(CONTENT_W / max(1, len(rows[0])) + 60, max(38.0, w + 10)))
    total = sum(widths)
    if total > CONTENT_W:
        widths = [w * CONTENT_W / total for w in widths]
    t = Table([head] + body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, RULE),
                ("BACKGROUND", (0, 0), (-1, 0), TBL_HEAD_BG),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def scaled_image(path: str, w: float, h: float):
    max_w, max_h = CONTENT_W, PAGE_H - TM - BM - 30
    if w <= 0 or h <= 0:
        return None
    f = min(1.0, max_w / w, max_h / h)
    if not os.path.exists(path):
        return None
    return Image(path, width=w * f, height=h * f)


def build_story(data, known, pages, toc):
    secs = {s["id"]: s for s in data["sections"]}
    dupe_map = {}
    for dup_sec, dup_t, org_sec, org_t in DUPES:
        for s in data["sections"]:
            if s["id"] != dup_sec:
                continue
            for q in s["questions"]:
                if same_title(q["title"], dup_t):
                    dupe_map[qkey(dup_sec, q["title"])] = (org_sec, org_t)

    def resolve_title(sec_id: str, prefix: str) -> str:
        for s in data["sections"]:
            if s["id"] != sec_id:
                continue
            for q in s["questions"]:
                if same_title(q["title"], prefix):
                    return q["title"]
        return prefix

    story = []

    story += [
        Spacer(1, 46),
        Paragraph("Compiladores — Questões e Resoluções", S["title"]),
        HRFlowable(width="100%", thickness=2, color=ACCENT,
                   spaceBefore=4, spaceAfter=16),
        Paragraph("Provas do meio de período, provas finais e exercícios — "
                  "enunciados com resolução", S["subtitle"]),
        Spacer(1, 14),
        Paragraph("Documento corrigido e reorganizado para estudo: as provas do meio "
                  "estão todas na Parte I e as provas finais todas na Parte II, com "
                  "sumário e páginas-divisórias.", S["cover_meta"]),
        Paragraph("Questões repetidas aparecem uma única vez (as demais viram nota de "
                  "referência) e o texto foi reflowado — sem fim de linha no meio da frase.",
                  S["cover_meta"]),
        Spacer(1, 22),
        Paragraph("Como este documento está organizado", S["h2big"]),
    ]
    for part in PARTS:
        secs_in = [s for g in part["groups"] for s in g["sections"]]
        story.append(Paragraph(
            f"<b>{part['title']}</b> — {len(secs_in)} seções: "
            + ", ".join((SEC_TITLES.get(s, s).split("—")[-1].strip())[:52]
                        for s in secs_in),
            S["cover_meta"]))
    story += [
        Spacer(1, 10),
        Paragraph("<b>Regras usadas nesta edição</b>", S["h2big"]),
        Paragraph("<b>1. Meio x final.</b> Toda prova com rótulo de origem ficou no seu "
                  "grupo (pastas “Provas mid” e “Provas finals”). As cinco provas sem "
                  "rótulo (au02, au05, csep501wi08, csep501au09, csep501au11) foram "
                  "classificadas pelo conteúdo predominante: au02 e au05 são de meio; "
                  "wi08, au09 e au11 são finais (cobrem o curso inteiro). A 2ª prova do "
                  "André, embora trate de assuntos de fim de curso, é a segunda prova do "
                  "professor — por isso está com as provas do meio; o aviso está no topo "
                  "dela.", S["body"]),
        Paragraph("<b>2. Repetições.</b> Onde a mesma questão aparece em dois lugares, "
                  "fica a primeira ocorrência do documento e a segunda é substituída por "
                  "uma nota com a página exata — você não copia a mesma questão duas vezes "
                  "e continua sabendo que ela existia naquela prova.", S["body"]),
        Paragraph("<b>3. Texto.</b> A transcrição foi reflowada: as linhas quebradas no "
                  "meio da frase foram reunidas, as listas e os rótulos (Passo1, a:, (b), "
                  "Grafo:) ganharam a quebra de linha que faltava, e blocos de código e "
                  "figuras ficaram como no original.", S["body"]),
        PageBreak(),
    ]

    story += [Paragraph("Sumário", S["h2big"]),
              HRFlowable(width="100%", thickness=1, color=RULE, spaceAfter=8)]
    if not toc:
        story.append(Paragraph("…", S["toc0"]))
    for level, text, key in toc:
        page = known.get(key, "—")
        story.append(toc_line(level, text, page))
    story.append(PageBreak())

    for pi, part in enumerate(PARTS):
        if pi:
            story.append(PageBreak())
        story.append(Mark(f"part:{part['title']}", pages))
        story.append(Paragraph(part["title"], S["parte"]))
        story.append(HRFlowable(width="100%", thickness=2, color=ACCENT,
                                spaceAfter=12))
        for d in part["desc"]:
            story.append(Paragraph(d, S["parte_desc"]))
        story.append(Spacer(1, 8))
        story.append(Paragraph("Nesta parte:", S["grupo"]))
        for g in part["groups"]:
            names = [SEC_TITLES.get(s, secs[s]["title"]) for s in g["sections"]]
            story.append(Paragraph("• " + to_xml("  ·  ".join(names)), S["grupo_note"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph("O sumário com a página de cada prova e de cada questão "
                               "está logo após a página de organização.", S["grupo_note"]))

        for g in part["groups"]:
            gkey = f"grp:{part['title']}|{g['title']}"
            story.append(PageBreak())
            story.append(Mark(gkey, pages))
            story.append(Paragraph(g["title"], S["grupo"]))
            if g.get("note"):
                story.append(Paragraph(g["note"], S["grupo_note"]))
            for gi, sid in enumerate(g["sections"]):
                if sid not in secs:
                    continue
                if gi:
                    story.append(PageBreak())
                sec = secs[sid]
                story.append(Mark(f"sec:{sid}", pages))
                story.append(Paragraph(to_xml(SEC_TITLES.get(sid, sec["title"])), S["h1"]))
                story.append(HRFlowable(width="100%", thickness=1, color=RULE,
                                        spaceAfter=8, spaceBefore=2))
                if sec.get("intro"):
                    story.append(Paragraph(to_xml(sec["intro"]), S["intro"]))

                for q in sec["questions"]:
                    key = qkey(sid, q["title"])
                    story.append(Mark(f"q:{key}", pages))
                    story.append(Paragraph(to_xml(q["title"]), S["h2"]))
                    dup = dupe_map.get(key)
                    if dup:
                        org_sec, org_t = dup
                        org_real = resolve_title(org_sec, org_t)
                        org_key = qkey(org_sec, org_real)
                        org_page = known.get(f"q:{org_key}", "—")
                        org_title = SEC_TITLES.get(org_sec, org_sec)
                        story.append(Paragraph(
                            f"<b>Questão repetida.</b> Este enunciado e esta resolução são "
                            f"idênticos aos de <b>{to_xml(org_real)}</b>, de "
                            f"<b>{to_xml(org_title)}</b> (página {org_page}). Não há nada "
                            f"novo aqui — se você já copiou aquela, pode pular esta.",
                            S["note"]))
                        continue
                    for b in q["blocks"]:
                        k = b["k"]
                        if k == "img":
                            img = scaled_image(os.path.join(ROOT, "data", b["f"]),
                                               b.get("w", 0), b.get("h", 0))
                            if img:
                                story += [Spacer(1, 3), img, Spacer(1, 7)]
                        elif k == "table":
                            story.append(Spacer(1, 2))
                            story.append(make_table(b["rows"]))
                            story.append(Spacer(1, 8))
                        elif k == "h3":
                            story.append(Paragraph(to_xml(b["t"]), S["h3"]))
                        elif k == "pre":
                            lines = "<br/>".join(to_xml(l) for l in b["lines"])
                            story.append(Paragraph(lines, S["pre"]))
                        elif k == "li":
                            txt = b["t"].lstrip("•").lstrip()
                            story.append(Paragraph(to_xml(txt), S["li"], bulletText="•"))
                        elif k == "item":
                            story.append(Paragraph(to_xml(b["t"]), S["item"]))
                        else:
                            story.append(Paragraph(to_xml(b["t"]), S["body"]))

    story += [PageBreak(), Paragraph("Nota — fontes e critério de compilação", S["h2big"]),
              HRFlowable(width="100%", thickness=1, color=RULE, spaceAfter=10),
              Paragraph(NOTE_FINAL, S["body"])]
    return story


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "data", "source.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--theme", choices=["light", "dark"], default="light",
                    help="tema do PDF: claro (padrão) ou escuro")
    args = ap.parse_args()
    apply_theme(args.theme)
    out = args.out or os.path.join(
        ROOT, "data",
        "Compiladores_Questoes_e_Resolucoes_reorganizado"
        + ("_dark" if args.theme == "dark" else "") + ".pdf"
    )

    with open(args.src, encoding="utf-8") as fh:
        data = json.load(fh)

    known: dict = {}
    pages: dict = {}
    for _ in range(6):
        pages = {}
        toc = build_toc(data)
        doc = Doc(out)
        story = build_story(data, known, pages, toc)
        doc.build(story)
        if known == pages:
            break
        known = dict(pages)

    print(f"{out}: {doc.page} páginas, {len(pages)} âncoras de página (tema {THEME})")
    return 0


def build_toc(data) -> list:
    toc = []
    for part in PARTS:
        toc.append((0, part["title"], f"part:{part['title']}"))
        for g in part["groups"]:
            toc.append((1, g["title"], f"grp:{part['title']}|{g['title']}"))
            for sid in g["sections"]:
                toc.append((2, SEC_TITLES.get(sid, sid), f"sec:{sid}"))
                for s in data["sections"]:
                    if s["id"] != sid:
                        continue
                    for q in s["questions"]:
                        toc.append((3, q["title"], f"q:{qkey(sid, q['title'])}"))
    return [(lvl, txt, key) for lvl, txt, key in toc]


if __name__ == "__main__":
    sys.exit(main())
