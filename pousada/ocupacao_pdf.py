"""Relatório de ocupação em PDF (A4): uma página por bloco de dias, com a grade unidade x dia e os totais.

Usa os blocos já recortados por ocupacao.dividir (a mesma estrutura que a tela de impressão desenha)."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .folha_pdf import MARGEM_MM, _cabecalho
from .regras import data_valida

SEM = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
VERDE, CINZA, OCUPADA = colors.HexColor("#0f5c63"), colors.HexColor("#d9d9d9"), colors.HexColor("#bfe3e6")
ROTULOS = (("ocupadas", "Ocupadas"), ("livres", "Livres"), ("pct", "Ocupação %"), ("entradas", "Check-ins"),
           ("saidas", "Check-outs"), ("pessoas", "Pessoas"))


def _br(iso):
    return data_valida(iso).strftime("%d/%m/%Y")


def pct_texto(v):
    """72.5 -> '72,5%'; 50.0 -> '50%'."""
    t = ("%.1f" % v).replace(".", ",")
    return (t[:-2] if t.endswith(",0") else t) + "%"


def _texto_celula(c, com_nomes, largura, tam):
    """Uma linha só, cortada com reticências para caber na largura (o PDF não pode vazar para a célula vizinha)."""
    base = (c["grupo"] or c["nome"]) if com_nomes else "Ocupada"
    pre, pos = ("« " if c["antes"] else ""), (" (%d)" % c["n"]) + (" »" if c["depois"] else "")
    while len(base) > 1 and stringWidth(pre + base + pos, "Helvetica", tam) > largura - 4:
        base = base[:-2].rstrip() + "…"
    return escape(pre + base + pos)


def _grade(bloco, com_nomes, retrato, estilo, tam):
    n = len(bloco["dias"])
    cab = [Paragraph("Unidade", estilo["cab"])] + [
        Paragraph("%s<br/>%s" % (SEM[data_valida(d).weekday()], d[8:] + "/" + d[5:7]), estilo["cab"]) for d in bloco["dias"]]
    larg_un = 21 * mm
    larg_dia = ((277 if not retrato else 190) * mm - larg_un) / n
    linhas, estilos, altura = [cab], [], [9 * mm if retrato else 7.5 * mm]
    for k, u in enumerate(bloco["linhas"], start=1):
        linha = [Paragraph(escape(u["a"]), estilo["forte"])] + [""] * n
        if u["interditada"]:
            linha[1] = Paragraph("Interditada (fora de venda)" if n > 3 else "Interditada", estilo["texto"])
            estilos += [("SPAN", (1, k), (n, k)), ("BACKGROUND", (1, k), (n, k), CINZA)]
        for c in u["celulas"]:
            a, z = c["col"] + 1, c["col"] + c["span"]
            linha[a] = Paragraph(_texto_celula(c, com_nomes, larg_dia * (c["span"]), tam), estilo["texto"])
            estilos.append(("BACKGROUND", (a, k), (z, k), OCUPADA))
            if z > a:
                estilos.append(("SPAN", (a, k), (z, k)))
        linhas.append(linha)
        altura.append(6.5 * mm if retrato else 4.9 * mm)
    for chave, rotulo in ROTULOS:
        linhas.append([Paragraph(rotulo, estilo["forte"])] + [
            Paragraph(pct_texto(t[chave]) if chave == "pct" else str(t[chave]), estilo["centro"]) for t in bloco["totais"]])
        altura.append(6 * mm if retrato else 4.9 * mm)
    primeiro_total = len(bloco["linhas"]) + 1
    t = Table(linhas, colWidths=[larg_un] + [larg_dia] * n, rowHeights=altura, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VERDE), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#777777")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5), ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
                           ("BACKGROUND", (0, primeiro_total), (-1, -1), colors.HexColor("#f1f5f5")),
                           ("LINEABOVE", (0, primeiro_total), (-1, primeiro_total), 1.2, colors.black)] + estilos))
    return t


def _resumo(r, estilo):
    p = r["pico"]
    txt = ("<b>Resumo do período</b> (%d dias, %d unidades reserváveis): ocupação média <b>%s</b>; diárias ocupadas <b>%d</b> de %d; "
           "pico <b>%d unidades (%s)</b> em %s; check-ins %d; check-outs %d; pessoas-noite %d."
           % (r["dias"], r["reservaveis"], pct_texto(r["ocupacao_media"]), r["noites_ocupadas"], r["noites_disponiveis"],
              p["ocupadas"], pct_texto(p["pct"]), _br(p["data"]), r["entradas"], r["saidas"], r["pessoas_noites"]))
    return Paragraph(txt, estilo["texto"])


LEGENDA = ("<b>Legenda:</b> célula colorida = unidade ocupada na noite do dia (nome do grupo ou hóspede e nº de pessoas); "
           "« continua do período anterior, » continua depois; cinza = unidade interditada (fora do cálculo); vazio = livre. "
           "Saída e entrada no mesmo dia na mesma unidade é permitida.")


def gerar_pdf(rel, emitido_por, agora=None):
    """Bytes do PDF do relatório (rel = resultado de ocupacao.dividir)."""
    retrato = rel["orientacao"] == "retrato"
    pagina = A4 if retrato else landscape(A4)
    tam = 6.5 if retrato else 6
    base = ParagraphStyle("t", fontName="Helvetica", fontSize=tam, leading=tam * 1.1)
    estilo = {"texto": base, "forte": ParagraphStyle("f", parent=base, fontName="Helvetica-Bold"),
              "centro": ParagraphStyle("c", parent=base, alignment=1),
              "cab": ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", textColor=colors.white, alignment=1),
              "titulo": ParagraphStyle("ti", fontName="Helvetica-Bold", fontSize=13, leading=15),
              "meta": ParagraphStyle("m", fontName="Helvetica", fontSize=8, leading=10)}
    emitido = (agora or datetime.now()).strftime("%d/%m/%Y %H:%M")
    meta = "Emitido em %s por %s" % (emitido, escape(emitido_por))
    peca = []
    for k, bloco in enumerate(rel["blocos"]):
        if k:
            peca.append(PageBreak())
        titulo = "Pousada Boa Esperança<br/>Relatório de ocupação - %s a %s" % (_br(rel["inicio"]), _br(rel["fim"]))
        peca += [_cabecalho(Paragraph(titulo, estilo["titulo"])), Paragraph(meta, estilo["meta"]), Spacer(1, 2 * mm)]
        if k == 0:
            peca += [_resumo(rel["resumo"], estilo), Spacer(1, 1.5 * mm), Paragraph(LEGENDA, estilo["texto"]), Spacer(1, 2 * mm)]
        peca.append(_grade(bloco, rel["com_nomes"], retrato, estilo, tam))
    buf = io.BytesIO()

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(MARGEM_MM * mm, 6 * mm, "Pousada Boa Esperança - relatório de ocupação - %s" % emitido)
        canvas.drawRightString(pagina[0] - MARGEM_MM * mm, 6 * mm, "Página %d" % doc.page)
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=pagina, leftMargin=MARGEM_MM * mm, rightMargin=MARGEM_MM * mm, topMargin=8 * mm,
                            bottomMargin=12 * mm, title="Relatório de ocupação", author="Pousada Boa Esperança")
    doc.build(peca, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
