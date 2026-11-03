"""Importação da planilha Excel de reservas (leitura, prévia e gravação).

Funções pequenas e independentes, para facilitar os testes:
  - leitura: ler_grade, listar_abas
  - interpretação de textos: normalizar_apto, calcular_periodo, interpretar_pagamento, extrair_grupo
  - prévia (nada é gravado): montar_previa
  - gravação em uma única transação: confirmar_importacao
  - desfazer: desfazer_lote
"""
import difflib
import re
import unicodedata
from datetime import date

from .db import transacao
from .historico import registrar, resumo_reserva
from .regras import OCUPADAS, UNIDADES, MSG_CARTAO, agora, contem_numero_cartao, data_valida, texto_limpo, validar_reserva

MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7,
         "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
MESES_PADRAO = (10, 11, 12)      # abas marcadas por padrão: outubro, novembro e dezembro
LIMITE_LINHAS = 5000             # segurança: lê no máximo isto por aba
LIMITE_LINHAS_CONFIRMAR = 5000   # segurança: o máximo de reservas aceitas numa confirmação
LIMITE_PEDIDOS_CONFIRMAR = 1000  # idem, para a lista de espera
MAX_TEXTO_PEDIDO = 1000
ESTADIA_LONGA = 45               # acima disso gera um aviso (provável erro de digitação)


class ErroLinha(Exception):
    """Problema encontrado em uma linha da planilha (categoria + motivo legível)."""

    def __init__(self, categoria, motivo):
        super().__init__(motivo)
        self.categoria = categoria
        self.motivo = motivo


# ---------------------------------------------------------------- textos

def sem_acento_maiusc(valor):
    """Texto em MAIÚSCULAS, sem acentos e com espaços simples."""
    t = unicodedata.normalize("NFD", str(valor if valor is not None else ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").upper()
    return re.sub(r"\s+", " ", t).strip()


def texto_celula(v):
    """Converte o valor de uma célula em texto (números inteiros sem '.0')."""
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):     # NaN e infinito (ex.: 1e999) não viram texto
            return ""
        if v == int(v):
            return str(int(v))
    return re.sub(r"[ \t\r\f\v]+", " ", str(v)).strip()


def chave_importacao(apto, entrada, saida, nome):
    """Identifica uma reserva: mesmo apto + entrada + saída + nome normalizado."""
    return "|".join([str(apto), str(entrada), str(saida), sem_acento_maiusc(nome)])


# ---------------------------------------------------------------- abas

def mes_ano_da_aba(titulo, primeiras_linhas=()):
    """Descobre (mês, ano) pelo nome da aba; o ano pode estar no nome ou nas primeiras linhas."""
    t = sem_acento_maiusc(titulo)
    mes = next((n for nome, n in MESES.items() if nome in t), None)
    ano = None
    candidatos = [t] + [sem_acento_maiusc(x) for x in primeiras_linhas]
    for c in candidatos:
        m = re.search(r"\b(20\d\d)\b", c)
        if m:
            ano = int(m.group(1))
            break
    if mes is None:  # tenta o título dentro da planilha ("HOSPEDAGEM ... - OUTUBRO 2026")
        for c in candidatos[1:]:
            mes = next((n for nome, n in MESES.items() if nome in c), None)
            if mes:
                break
    return mes, ano


def linhas_da_aba(ws):
    """Lista de tuplas (A..E) já como valores; o índice + 1 é o número da linha original."""
    limite = min(ws.max_row or 0, LIMITE_LINHAS)
    if limite < 1:
        return []
    return [tuple((list(r) + [None] * 5)[:5])
            for r in ws.iter_rows(min_row=1, max_row=limite, max_col=5, values_only=True)]


def listar_abas(wb):
    """Abas que parecem ter reservas: [{titulo, mes, ano, ws}] (abas vazias como Plan1 ficam de fora)."""
    abas = []
    for ws in wb.worksheets:
        linhas = linhas_da_aba(ws)
        if not any(any(texto_celula(c) for c in lin) for lin in linhas):
            continue
        mes, ano = mes_ano_da_aba(ws.title, [texto_celula(l[0]) or texto_celula(l[1]) for l in linhas[:5]])
        if mes is None:
            continue
        abas.append({"titulo": ws.title, "mes": mes, "ano": ano, "linhas": linhas})
    return abas


# ---------------------------------------------------------------- leitura da grade

def _titulo_secao(a, b):
    """'espera', 'cancel' ou None, conforme os títulos que encerram a grade de reservas."""
    for t in (sem_acento_maiusc(b), sem_acento_maiusc(a)):
        if t.startswith("LISTA DE ESPERA"):
            return "espera"
        if t.startswith("CANCELAMENTO"):
            return "cancel"
    return None


def ler_grade(linhas):
    """Separa as linhas da aba em reservas brutas e linhas da lista de espera.

    Devolve (reservas, espera, n_cancelamentos). Cada reserva bruta tem:
    linha, apto, hospede, pessoas, periodo, texto_e, extras[].
    A grade começa em uma linha com "APTO" na coluna A e termina nos títulos
    "LISTA DE ESPERA" / "CANCELAMENTOS" (um novo cabeçalho "APTO" reabre a grade).
    """
    reservas, espera, n_canc = [], [], 0
    modo, atual = "fora", None
    for numero, lin in enumerate(linhas, start=1):
        a, b, c, d, e = (texto_celula(x) for x in lin)
        a_n = sem_acento_maiusc(a)
        if a_n == "APTO":
            modo, atual = "grade", None
            continue
        secao = _titulo_secao(a, b)
        if secao:
            modo, atual = secao, None
            continue
        if modo == "espera":
            if b:
                espera.append({"linha": numero, "texto": b})
            continue
        if modo == "cancel":
            if b or a:
                n_canc += 1
            continue
        if modo != "grade":
            continue
        if not (a or b or c or d or e):          # linha vazia separa as reservas
            atual = None
            continue
        if a_n.startswith("HOSPEDAGEM") or a_n.startswith("OBS") or (
                lin[0] is not None and not isinstance(lin[0], (int, float, str))):
            atual = None
            continue
        if a:
            if not (b or c or d or e):           # só o número do apto: linha em branco do mapa
                atual = None
                continue
            atual = {"linha": numero, "apto": a, "hospede": b, "pessoas": c, "periodo": d,
                     "texto_e": e, "extras": []}
            reservas.append(atual)
        elif d:                                  # tem período mas não tem apto
            atual = {"linha": numero, "apto": "", "hospede": b, "pessoas": c, "periodo": d,
                     "texto_e": e, "extras": []}
            reservas.append(atual)
        elif b and atual is not None:            # acompanhante da reserva de cima
            atual["extras"].append(b)
    return reservas, espera, n_canc


# ---------------------------------------------------------------- interpretação

_MAPA_UNIDADES = {sem_acento_maiusc(u): u for u in UNIDADES}


def normalizar_apto(valor):
    """'101' / 101 / 'CHALE A' / 'Chalé a' / 'APTO 305' -> nome da unidade, ou None se não existir."""
    t = sem_acento_maiusc(texto_celula(valor))
    t = re.sub(r"^(APARTAMENTO|APTO|APT|AP)\.?\s*", "", t)
    m = re.fullmatch(r"CHALE\s*([A-Z])", t)
    if m:
        t = "CHALE " + m.group(1)
    return _MAPA_UNIDADES.get(t)


def sugerir_apto(valor):
    """Unidade mais parecida com o texto digitado (ou None)."""
    t = re.sub(r"^(APARTAMENTO|APTO|APT|AP)\.?\s*", "", sem_acento_maiusc(texto_celula(valor)))
    achou = difflib.get_close_matches(t, list(_MAPA_UNIDADES), n=1, cutoff=0.5)
    return _MAPA_UNIDADES[achou[0]] if achou else None


_RE_PERIODO = re.compile(r"(\d{1,2})(?:\s*/\s*(\d{1,2})?)?\s*(?:ATE|A|-)\s*(\d{1,2})\s*/\s*(\d{1,2})")


def achar_periodo(texto):
    """Localiza 'dd/mm A dd/mm' (aceita 'a', '-', sem espaços, e entrada só com o dia)."""
    return _RE_PERIODO.search(sem_acento_maiusc(texto))


def calcular_periodo(texto, ano, mes_aba, ano_seguinte_se_antigo=False):
    """Converte o texto do período em (entrada, saída, avisos) com datas ISO.

    Regras: ano = ano da aba; saída antes da entrada vira ano seguinte;
    na aba de janeiro, entrada em dezembro pertence ao ano anterior.
    Levanta ErroLinha para datas impossíveis (ex.: 31/11) ou saída <= entrada.
    """
    if not texto_celula(texto):
        raise ErroLinha("periodo", "Período não informado")
    m = achar_periodo(texto)
    if not m:
        raise ErroLinha("periodo", "Período não reconhecido (use dd/mm A dd/mm)")
    avisos = []
    dia_e, dia_s, mes_s = int(m.group(1)), int(m.group(3)), int(m.group(4))
    if m.group(2):
        mes_e = int(m.group(2))
    else:
        mes_e = mes_s if dia_e <= dia_s else (mes_s - 1 or 12)
        avisos.append("Mês da entrada não informado: assumido %02d" % mes_e)
    if not (1 <= mes_e <= 12 and 1 <= mes_s <= 12):
        raise ErroLinha("data_invalida", "Data inválida (%02d/%02d a %02d/%02d)" % (dia_e, mes_e, dia_s, mes_s))
    base = ano + 1 if (ano_seguinte_se_antigo and mes_aba and mes_aba - mes_e > 6) else ano
    ano_e = base - 1 if (mes_aba == 1 and mes_e == 12) else base
    ano_s = ano_e if (mes_s, dia_s) >= (mes_e, dia_e) else ano_e + 1
    try:
        entrada = date(ano_e, mes_e, dia_e)
    except ValueError:
        raise ErroLinha("data_invalida", "Data inválida (%02d/%02d)" % (dia_e, mes_e))
    try:
        saida = date(ano_s, mes_s, dia_s)
    except ValueError:
        raise ErroLinha("data_invalida", "Data inválida (%02d/%02d)" % (dia_s, mes_s))
    if saida <= entrada:
        raise ErroLinha("saida_invalida", "A saída deve ser depois da entrada")
    if (saida - entrada).days > ESTADIA_LONGA:
        avisos.append("Estadia de %d noites: confira as datas" % (saida - entrada).days)
    return entrada.isoformat(), saida.isoformat(), avisos


def interpretar_pagamento(texto):
    """Interpreta o texto livre da coluna E (ordem de prioridade fixa)."""
    t = sem_acento_maiusc(texto)
    if re.search(r"GRATUIDADE|GRATUIT|CORTESIA|GRATIS", t):
        return "gratis"
    if re.search(r"(?<!\d)[1-9]\d?\s*%", t) or re.search(r"PARCIAL|SINAL", t):
        return "parcial"
    if re.search(r"\bPAGO\b", t):
        return "pago"
    if re.search(r"POUSADA|ACERT|VAI PAGAR", t):
        return "pousada"
    return "pendente"


def extrair_grupo(hospede, texto_e):
    """Nome do grupo: o próprio hóspede se começar com TURMA/GRUPO, ou o início do texto E."""
    if re.match(r"^(TURMA|GRUPO)\b", sem_acento_maiusc(hospede)):
        return re.sub(r"\s+", " ", hospede).strip()[:120]
    if sem_acento_maiusc(texto_e).startswith("TURMA"):
        return re.sub(r"\s+", " ", texto_e.split(" - ")[0]).strip()[:120]
    return ""


def interpretar_pessoas(texto, extras):
    """(n, estimado): número da coluna C; se vazio, 1 + acompanhantes."""
    m = re.match(r"\d+", texto_celula(texto))
    if m:
        return int(m.group(0)[:9]), False        # só 9 dígitos: o int() de um número gigante dá erro
    return 1 + len(extras), True


# ---------------------------------------------------------------- lista de espera

_RE_TELEFONE = re.compile(r"\(?\d{2}\)?[\s.-]*9?\d{4}[\s.-]?\d{4}")


def interpretar_pedido(texto, ano, mes_aba):
    """Linha livre 'NOME - 03 PESSOAS - 03 A 06/12 - telefone' -> dados do pedido (melhor esforço)."""
    texto = re.sub(r"\s+", " ", texto).strip()
    partes = [p.strip() for p in re.split(r"\s+-+\s*|\s*-+\s+", texto) if p.strip()]
    nome = (partes[0] if partes else texto)[:120]
    mp = re.search(r"(\d{1,4})\s*PESS", sem_acento_maiusc(texto))
    entrada = saida = None
    try:
        entrada, saida, _ = calcular_periodo(texto, ano, mes_aba, ano_seguinte_se_antigo=True)
    except ErroLinha:
        pass
    mt = _RE_TELEFONE.search(texto)
    return {"nome": nome, "pessoas": int(mp.group(1)) if mp else None, "entrada": entrada,
            "saida": saida, "contato": mt.group(0).strip() if mt else "", "observacao": texto}


# ---------------------------------------------------------------- prévia

def _sobrepoe(i1, f1, i2, f2):
    return i1 < f2 and i2 < f1


def _quase_igual(item, aceitas_apto, aba):
    """Reserva de outra aba, mesmo apto e datas, com nome quase igual (erro de digitação)? Devolve-a ou None."""
    for o in aceitas_apto:
        if o["aba"] != aba and (o["entrada"], o["saida"]) == (item["entrada"], item["saida"]):
            if difflib.SequenceMatcher(None, sem_acento_maiusc(o["hospede"]),
                                       sem_acento_maiusc(item["hospede"])).ratio() >= 0.9:
                return o
    return None


def _carregar_existentes(con):
    por_apto = {}
    for r in con.execute("SELECT id, a, nome, i, f, chave_import, status FROM reservas"):
        por_apto.setdefault(r["a"], []).append(dict(r))
    return por_apto


def _interpretar_reserva(bruta, ano, mes_aba):
    """Converte uma linha bruta em dados normalizados. Levanta ErroLinha se não der."""
    apto = normalizar_apto(bruta["apto"])
    grupo = extrair_grupo(bruta["hospede"], bruta["texto_e"])
    item = {"linha": bruta["linha"], "apto": apto or "", "apto_original": bruta["apto"],
            "hospede": re.sub(r"\s+", " ", bruta["hospede"]).strip(), "extras": list(bruta["extras"]),
            "grupo": grupo, "pagamento": interpretar_pagamento(bruta["texto_e"]),
            "texto_pagamento": bruta["texto_e"], "avisos": [], "entrada": None, "saida": None}
    item["n"], estimado = interpretar_pessoas(bruta["pessoas"], bruta["extras"])
    item["n_estimado"] = estimado
    _recusar_cartao(item, bruta)
    if apto in OCUPADAS:
        raise _Ignorada(item, "ocupado", "Unidade %s está ocupada: linha ignorada" % apto)
    if not apto:
        sug = sugerir_apto(bruta["apto"])
        motivo = "Apto inexistente: '%s'" % bruta["apto"] if bruta["apto"] else "Apto não informado"
        if sug:
            motivo += " (sugestão: %s)" % sug
        item["sugestao"] = sug
        raise _Erro(item, "apto_inexistente", motivo)
    try:
        item["entrada"], item["saida"], av = calcular_periodo(bruta["periodo"], ano, mes_aba)
        item["avisos"].extend(av)
    except ErroLinha as e:
        raise _Erro(item, e.categoria, e.motivo)
    if not item["hospede"]:
        raise _Erro(item, "hospede", "Nome do hóspede não informado")
    if item["n"] > 50:
        raise _Erro(item, "pessoas", "Número de pessoas inválido")
    if estimado:
        item["avisos"].append("Nº de pessoas vazio: assumido %d (hóspede + acompanhantes)" % item["n"])
    return item


def _recusar_cartao(item, bruta):
    """Linha com número de cartão em qualquer texto NÃO entra: vira erro na prévia, sem repetir o número."""
    textos = [bruta["hospede"], bruta["texto_e"], bruta["apto"]] + list(bruta["extras"]) + [item["grupo"] or ""]
    if any(contem_numero_cartao(t) for t in textos if isinstance(t, str)):
        item.update(hospede="(oculto)", extras=[], texto_pagamento="", grupo="", apto_original="")
        raise _Erro(item, "cartao", MSG_CARTAO)


class _Erro(Exception):
    def __init__(self, item, categoria, motivo):
        super().__init__(motivo)
        self.item, self.categoria, self.motivo = item, categoria, motivo


class _Ignorada(_Erro):
    pass


def descrever_abas(abas, selecionadas):
    return [{"titulo": a["titulo"], "mes": a["mes"], "ano": a["ano"],
             "selecionada": a["titulo"] in selecionadas} for a in abas]


def montar_previa(wb, con, hoje, titulos=None, incluir_passadas=False):
    """Lê a planilha e devolve a prévia completa. NÃO grava nada no banco."""
    abas = listar_abas(wb)
    if titulos is None:
        titulos = [a["titulo"] for a in abas if a["mes"] in MESES_PADRAO]
    titulos = set(titulos)
    existentes = _carregar_existentes(con)
    pedidos_banco = {(sem_acento_maiusc(r["nome"]), sem_acento_maiusc(r["observacao"]))
                     for r in con.execute("SELECT nome, observacao FROM pedidos")}
    vistas, aceitas = {}, {}      # chave -> origem ; apto -> reservas válidas da planilha
    linhas_out, pedidos_out, vistos_ped = [], [], set()
    n_canc = cartoes_espera = 0
    hoje_iso = hoje.isoformat()
    for aba in abas:
        if aba["titulo"] not in titulos:
            continue
        ano = aba["ano"] or hoje.year
        aviso_ano = [] if aba["ano"] else ["Ano não encontrado na aba: assumido %d" % ano]
        brutas, espera, canc = ler_grade(aba["linhas"])
        n_canc += canc
        for bruta in brutas:
            saida_linha = {"aba": aba["titulo"], "id": len(linhas_out)}
            try:
                item = _interpretar_reserva(bruta, ano, aba["mes"])
                item["avisos"].extend(aviso_ano)
                status, categoria, motivo, conflitos = "ok", "", "", []
                chave = chave_importacao(item["apto"], item["entrada"], item["saida"], item["hospede"])
                if chave in vistas:
                    o = vistas[chave]
                    raise _Ignorada(item, "repetida", "Repetida na virada do mês (igual à linha %d da aba %s): fundida"
                                    % (o[1], o[0]))
                parecida = _quase_igual(item, aceitas.get(item["apto"], []), aba["titulo"])
                if parecida:
                    raise _Ignorada(item, "repetida", "Repetida na virada do mês (quase igual à linha %d da aba %s, "
                                    "só o nome tem pequena diferença): fundida" % (parecida["linha"], parecida["aba"]))
                vistas[chave] = (aba["titulo"], item["linha"])
                if item["saida"] < hoje_iso and not incluir_passadas:
                    raise _Ignorada(item, "encerrada", "Reserva já encerrada (saída antes de hoje)")
                dup = [r for r in existentes.get(item["apto"], [])
                       if r["chave_import"] == chave or (r["i"] == item["entrada"] and r["f"] == item["saida"]
                                                         and sem_acento_maiusc(r["nome"]) == sem_acento_maiusc(item["hospede"]))]
                if dup:
                    raise _Ignorada(item, "ja_importada", "Já importada (existe no sistema)")
                for r in existentes.get(item["apto"], []):
                    if r["status"] == "ativa" and _sobrepoe(item["entrada"], item["saida"], r["i"], r["f"]):
                        conflitos.append({"origem": "banco", "id": r["id"], "nome": r["nome"],
                                          "entrada": r["i"], "saida": r["f"]})
                for o in aceitas.get(item["apto"], []):
                    if _sobrepoe(item["entrada"], item["saida"], o["entrada"], o["saida"]):
                        conflitos.append({"origem": "planilha", "aba": o["aba"], "linha": o["linha"],
                                          "nome": o["hospede"], "entrada": o["entrada"], "saida": o["saida"]})
                if conflitos:
                    item["conflitos"] = conflitos
                    motivo = "Conflito: " + "; ".join(_descrever_conflito(c) for c in conflitos)
                    if any(c["origem"] == "planilha" and c["aba"] != aba["titulo"] and
                           (c["entrada"], c["saida"]) == (item["entrada"], item["saida"]) for c in conflitos):
                        motivo += " - mesmas datas em outra aba: talvez seja a mesma reserva com o nome escrito diferente"
                    raise _Erro(item, "conflito", motivo)
                aceitas.setdefault(item["apto"], []).append(dict(item, aba=aba["titulo"]))
                if item["avisos"]:
                    status, motivo = "aviso", "; ".join(item["avisos"])
                saida_linha.update(item, status=status, categoria=categoria, motivo=motivo)
            except _Ignorada as e:
                saida_linha.update(e.item, status="ignorada", categoria=e.categoria, motivo=e.motivo)
            except _Erro as e:
                saida_linha.update(e.item, status="erro", categoria=e.categoria, motivo=e.motivo)
            saida_linha.setdefault("conflitos", [])
            linhas_out.append(saida_linha)
        for esp in espera:
            if contem_numero_cartao(esp["texto"]):
                cartoes_espera += 1          # item da lista de espera com cartão não entra na prévia
                continue
            p = interpretar_pedido(esp["texto"], ano, aba["mes"])
            k = sem_acento_maiusc(p["observacao"])
            if k in vistos_ped:
                continue
            vistos_ped.add(k)
            p.update(aba=aba["titulo"], linha=esp["linha"],
                     ja_importado=(sem_acento_maiusc(p["nome"]), k) in pedidos_banco)
            pedidos_out.append(p)
    cont = {"prontas": 0, "avisos": 0, "erros": 0, "ignoradas": 0}
    for l in linhas_out:
        cont[{"ok": "prontas", "aviso": "avisos", "erro": "erros", "ignorada": "ignoradas"}[l["status"]]] += 1
    cont["lista_espera"] = len([p for p in pedidos_out if not p["ja_importado"]])
    cont["cancelamentos"] = n_canc
    cont["espera_com_cartao"] = cartoes_espera
    return {"abas": descrever_abas(abas, titulos), "linhas": linhas_out, "pedidos": pedidos_out,
            "contadores": cont, "hoje": hoje_iso}


def _br(iso):
    return "%s/%s" % (iso[8:10], iso[5:7])


def _descrever_conflito(c):
    if c["origem"] == "banco":
        return "reserva já cadastrada #%s de %s (%s a %s)" % (c["id"], c["nome"], _br(c["entrada"]), _br(c["saida"]))
    return "linha %s da aba %s, %s (%s a %s)" % (c["linha"], c["aba"], c["nome"], _br(c["entrada"]), _br(c["saida"]))


# ---------------------------------------------------------------- gravação

class ImportacaoRecusada(Exception):
    """A confirmação foi recusada (nada foi gravado). 'problemas' lista o que deu errado."""

    def __init__(self, problemas, conflito):
        super().__init__("Importação recusada")
        self.problemas = problemas
        self.conflito = conflito


def _inserir(con, d, lote_id, chave):
    t = agora()
    return con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,lote_id,chave_import,criado,alterado,versao) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                       (d["a"], d["nome"], d["extras"], d["n"], d["i"], d["f"], d["p"], d["o"], d["grupo"] or "",
                        lote_id, chave, t, t)).lastrowid


def _linha_ja_existe(con, dados, chave):
    mesmos = con.execute("SELECT id, nome FROM reservas WHERE a=? AND i=? AND f=?",
                         (dados["a"], dados["i"], dados["f"])).fetchall()
    return con.execute("SELECT 1 FROM reservas WHERE chave_import=?", (chave,)).fetchone() is not None or any(
        sem_acento_maiusc(m["nome"]) == sem_acento_maiusc(dados["nome"]) for m in mesmos)


def _gravar_linhas(con, linhas, lote_id, ator):
    """Valida e grava cada linha. Devolve (criadas, ignoradas, problemas, houve_conflito)."""
    problemas, criadas, ignoradas, conflito = [], 0, [], False
    for k, bruto in enumerate(linhas):
        ref = {"aba": str(bruto.get("aba", "")) if isinstance(bruto, dict) else "",
               "linha": bruto.get("linha") if isinstance(bruto, dict) else None, "indice": k}
        dados, erro = validar_reserva(bruto)
        if erro:
            problemas.append(dict(ref, motivo=erro))
            continue
        chave = chave_importacao(dados["a"], dados["i"], dados["f"], dados["nome"])
        if _linha_ja_existe(con, dados, chave):
            ignoradas.append(dict(ref, motivo="Já importada"))
            continue
        choque = con.execute("SELECT id, nome, i, f FROM reservas WHERE status='ativa' AND a=? AND i<? AND f>?",
                             (dados["a"], dados["f"], dados["i"])).fetchone()
        if choque:
            conflito = True
            problemas.append(dict(ref, motivo="Conflito: %s já está reservada por %s (%s a %s)" % (
                dados["a"], choque["nome"], _br(choque["i"]), _br(choque["f"]))))
            continue
        novo = _inserir(con, dados, lote_id, chave)
        registrar(con, "importar", "reserva", novo, None, dict(resumo_reserva(dados), lote=lote_id), ator)
        criadas += 1
    return criadas, ignoradas, problemas, conflito


def confirmar_importacao(con, arquivo, usuario, linhas, pedidos, ator=None, sha256=None):
    """Grava as linhas aprovadas. REVALIDA tudo dentro de uma transação: tudo ou nada.

    Reservas idênticas às que já existem são ignoradas (não é erro).
    Conflito de datas, apto inexistente etc. recusam a importação inteira (ImportacaoRecusada).
    """
    if not isinstance(linhas, list) or not isinstance(pedidos, list):
        raise ImportacaoRecusada([{"motivo": "Dados inválidos"}], False)
    if len(linhas) > LIMITE_LINHAS_CONFIRMAR or len(pedidos) > LIMITE_PEDIDOS_CONFIRMAR:
        raise ImportacaoRecusada([{"motivo": "Itens demais numa só importação (máximo %d reservas e %d pedidos)"
                                   % (LIMITE_LINHAS_CONFIRMAR, LIMITE_PEDIDOS_CONFIRMAR)}], False)
    with transacao(con):
        lote_id = con.execute(
            "INSERT INTO importacoes (arquivo, criado, usuario, total, criadas, sha256) VALUES (?,?,?,?,0,?)",
            (_texto_pedido(arquivo, 200), agora(), (ator or {}).get("login") or _texto_pedido(usuario, 80),
             len(linhas), sha256)).lastrowid
        criadas, ignoradas, problemas, conflito = _gravar_linhas(con, linhas, lote_id, ator)
        if problemas:
            raise ImportacaoRecusada(problemas, conflito)
        pedidos_criados = _gravar_pedidos(con, pedidos, lote_id)
        con.execute("UPDATE importacoes SET criadas=? WHERE id=?", (criadas, lote_id))
        registrar(con, "importar", "importacao", lote_id, None,
                  {"lote": lote_id, "criadas": criadas, "ignoradas": len(ignoradas), "pedidos": pedidos_criados,
                   "sha256": sha256}, ator)
    return {"lote_id": lote_id, "criadas": criadas, "ignoradas": len(ignoradas),
            "detalhes_ignoradas": ignoradas, "pedidos_criados": pedidos_criados}


def _texto_pedido(v, maximo):
    """Texto de um pedido da lista de espera: só texto sem caracteres proibidos, cortado no limite."""
    return v.strip()[:maximo] if texto_limpo(v) else ""


def _gravar_pedidos(con, pedidos, lote_id):
    criados = 0
    for p in pedidos:
        if not isinstance(p, dict):
            continue
        nome = _texto_pedido(p.get("nome", ""), 120)
        obs = _texto_pedido(p.get("observacao", ""), MAX_TEXTO_PEDIDO)
        contato = _texto_pedido(p.get("contato", ""), 80)
        if not nome or any(contem_numero_cartao(t) for t in (nome, obs, contato)):
            continue                      # pedido com número de cartão não entra (a reserva é recusada com aviso)
        if con.execute("SELECT 1 FROM pedidos WHERE nome=? AND observacao=?", (nome, obs)).fetchone():
            continue
        pessoas = p.get("pessoas")
        if not (isinstance(pessoas, int) and not isinstance(pessoas, bool) and 0 < pessoas <= 1000):
            pessoas = None
        entrada, saida = (data_valida(p.get(c)) for c in ("entrada", "saida"))
        con.execute("INSERT INTO pedidos (nome,pessoas,entrada,saida,contato,observacao,criado,situacao,lote_id) "
                    "VALUES (?,?,?,?,?,?,?, 'aberto', ?)",
                    (nome, pessoas, entrada.isoformat() if entrada else None, saida.isoformat() if saida else None,
                     contato, obs, agora(), lote_id))
        criados += 1
    return criados


def desfazer_lote(con, lote_id, ator=None):
    """Remove só as reservas (e pedidos ainda abertos) criados por esse lote. None se o lote não existe."""
    with transacao(con):
        if not con.execute("SELECT 1 FROM importacoes WHERE id=?", (lote_id,)).fetchone():
            return None
        for r in con.execute("SELECT * FROM reservas WHERE lote_id=?", (lote_id,)).fetchall():
            registrar(con, "desfazer", "reserva", r["id"], dict(resumo_reserva(r), lote=lote_id), None, ator)
        removidas = con.execute("DELETE FROM reservas WHERE lote_id=?", (lote_id,)).rowcount
        pedidos = con.execute("DELETE FROM pedidos WHERE lote_id=? AND situacao='aberto'", (lote_id,)).rowcount
        registrar(con, "desfazer", "importacao", lote_id, None,
                  {"lote": lote_id, "removidas": removidas, "pedidos": pedidos}, ator)
    return {"removidas": removidas, "pedidos_removidos": pedidos}
