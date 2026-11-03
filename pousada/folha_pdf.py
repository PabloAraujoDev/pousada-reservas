"""Folha da semana em PDF (A4 paisagem): entradas, saídas e totais de cada dia.

Os totais seguem as mesmas regras do mapa e da folha da tela:
  hóspedes na noite = entrada <= dia < saída; café = entrada < dia <= saída.
"""
import io
import os
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config
from .regras import OCUPADAS, UNIDADES

ARQUIVO_LOGO = os.path.join(config.PASTA_ESTATICA, "logo.png")

DIAS_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
RESERVAVEIS = len([u for u in UNIDADES if u not in OCUPADAS])
ORIENTACOES = ("paisagem", "retrato")
MARGEM_MM = 10
# Larguras das colunas (Dia, Entradas, Saídas, Na noite, Café, Livres): somam a largura útil da A4 menos as margens.
LARGURAS_MM = {"paisagem": (30, 98, 98, 17, 17, 17),     # 277 mm
               "retrato": (23, 62, 62, 15, 13, 15)}      # 190 mm


def _br(d):
    return d.strftime("%d/%m/%Y")


def _ordem(apto):
    return UNIDADES.index(apto) if apto in UNIDADES else len(UNIDADES)


def montar_semana(con, inicio, dias=7):
    """Lista de dias com entradas, saídas e totais. Reservas canceladas não entram."""
    fim = inicio + timedelta(days=dias)
    reservas = con.execute(
        "SELECT a, nome, n, i, f FROM reservas WHERE status = 'ativa' AND i <= ? AND f >= ?",
        ((fim).isoformat(), inicio.isoformat())).fetchall()
    resultado = []
    for k in range(dias):
        d = inicio + timedelta(days=k)
        iso = d.isoformat()
        entradas = sorted((r for r in reservas if r["i"] == iso), key=lambda r: _ordem(r["a"]))
        saidas = sorted((r for r in reservas if r["f"] == iso), key=lambda r: _ordem(r["a"]))
        na_noite = [r for r in reservas if r["i"] <= iso < r["f"]]
        resultado.append({
            "data": d, "entradas": entradas, "saidas": saidas,
            "noite": sum(r["n"] for r in na_noite),
            "cafe": sum(r["n"] for r in reservas if r["i"] < iso <= r["f"]),
            "livres": max(0, RESERVAVEIS - len(na_noite)),
        })
    return resultado


def _tamanho_da_fonte(semana, retrato=False):
    """Menos espaço por linha quando há muitas reservas, para tentar caber em uma página.
    No retrato as colunas são mais estreitas (os nomes quebram em mais linhas), então a letra encolhe antes."""
    linhas = sum(max(len(d["entradas"]), len(d["saidas"]), 1) for d in semana)
    if retrato:
        linhas = int(linhas * 1.35)
    for limite, tamanho in ((26, 9.5), (34, 8.5), (44, 7.5), (56, 6.5)):
        if linhas <= limite:
            return tamanho
    return 6


def _lista(reservas, estilo):
    """Uma linha por reserva: 'apto - nome (pessoas)'. O texto é escapado porque o Paragraph lê XML."""
    if not reservas:
        return Paragraph("-", estilo)
    linhas = ["%s - %s (%s)" % (escape(r["a"]), escape(r["nome"]), r["n"]) for r in reservas]
    return Paragraph("<br/>".join(linhas), estilo)


def gerar_pdf(semana, inicio, dias=7, orientacao="paisagem"):
    """Devolve os bytes do PDF (A4 em paisagem ou retrato)."""
    if orientacao not in ORIENTACOES:
        raise ValueError("Orientação inválida")
    retrato = orientacao == "retrato"
    pagina = A4 if retrato else landscape(A4)
    tam = _tamanho_da_fonte(semana, retrato)
    texto = ParagraphStyle("t", fontName="Helvetica", fontSize=tam, leading=tam * 1.2)
    forte = ParagraphStyle("f", parent=texto, fontName="Helvetica-Bold")
    centro = ParagraphStyle("c", parent=texto, alignment=1)
    cab = ParagraphStyle("h", parent=forte, textColor=colors.white)
    titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=14, leading=17)

    linhas = [[Paragraph(t, cab) for t in ("Dia", "Entradas", "Saídas", "Na noite", "Café", "Livres")]]
    for d in semana:
        rotulo = "%s<br/>%s" % (DIAS_SEMANA[d["data"].weekday()], d["data"].strftime("%d/%m/%Y"))
        linhas.append([Paragraph(rotulo, forte), _lista(d["entradas"], texto), _lista(d["saidas"], texto),
                       Paragraph(str(d["noite"]), centro), Paragraph(str(d["cafe"]), centro),
                       Paragraph(str(d["livres"]), centro)])
    tabela = Table(linhas, colWidths=[w * mm for w in LARGURAS_MM[orientacao]], repeatRows=1, splitInRow=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5c63")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#777777")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))

    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(MARGEM_MM * mm, 6 * mm, "Pousada Boa Esperança - folha da semana - gerada em %s" % gerado)
        canvas.drawRightString(pagina[0] - MARGEM_MM * mm, 6 * mm, "Página %d" % doc.page)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=pagina, leftMargin=MARGEM_MM * mm, rightMargin=MARGEM_MM * mm,
                            topMargin=9 * mm, bottomMargin=12 * mm, title="Folha da semana",
                            author="Pousada Boa Esperança")
    ultimo = inicio + timedelta(days=dias - 1)
    doc.build([_cabecalho(Paragraph("Pousada Boa Esperança<br/>Folha da semana - %s a %s" % (_br(inicio), _br(ultimo)), titulo)),
               Spacer(1, 3 * mm), tabela],
              onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()


def _cabecalho(titulo):
    """Título com a logo do clube ao lado (se o arquivo existir)."""
    if not os.path.isfile(ARQUIVO_LOGO):
        return titulo
    logo = Image(ARQUIVO_LOGO, width=13 * mm, height=12.5 * mm)
    t = Table([[logo, titulo]], colWidths=[16 * mm, None])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    t.hAlign = "LEFT"
    return t
