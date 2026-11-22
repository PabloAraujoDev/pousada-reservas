"""Montagem da PRÉVIA da importação (nada é gravado): lê a planilha, casa com o sistema e propõe
reservas novas, atualizações, cancelamentos e "sumiu da planilha". A leitura/interpretação das linhas e a gravação
ficam em importador.py."""
import difflib

from .importador import (MESES_PADRAO, _br, _Erro, _Ignorada, _interpretar_reserva, chave_importacao, interpretar_pedido,
                         ler_grade, listar_abas, sem_acento_maiusc)
from .regras import contem_numero_cartao


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
    for r in con.execute("SELECT id, a, nome, extras, n, i, f, p, o, grupo, chave_import, status, versao, lote_id, checkin_em, conta_aberta_em "
                          "FROM reservas"):
        por_apto.setdefault(r["a"], []).append(dict(r))
    return por_apto


def descrever_abas(abas, selecionadas):
    return [{"titulo": a["titulo"], "mes": a["mes"], "ano": a["ano"],
             "selecionada": a["titulo"] in selecionadas} for a in abas]


def montar_previa(wb, con, hoje, titulos=None, incluir_passadas=False):
    """Lê a planilha e devolve a prévia completa. NÃO grava nada no banco."""
    from .importador_casar import escolher_alvo
    abas = listar_abas(wb)
    if titulos is None:
        titulos = [a["titulo"] for a in abas if a["mes"] in MESES_PADRAO]
    titulos = set(titulos)
    existentes = _carregar_existentes(con)
    pedidos_banco = {(sem_acento_maiusc(r["nome"]), sem_acento_maiusc(r["observacao"]))
                     for r in con.execute("SELECT nome, observacao FROM pedidos")}
    vistas, aceitas = {}, {}      # chave -> origem ; apto -> reservas válidas da planilha
    linhas_out, pedidos_out, vistos_ped = [], [], set()
    cartoes_espera = 0
    hoje_iso = hoje.isoformat()
    grades = {a["titulo"]: ler_grade(a["linhas"]) for a in abas if a["titulo"] in titulos}      # cada aba é lida uma vez só
    canc = _preparar_cancelamentos(con, abas, titulos, existentes, hoje, incluir_passadas, grades)
    liberaveis = {p["id"] for p in canc["propostas"] if not p["bloqueio"]}
    for aba in abas:
        if aba["titulo"] not in titulos:
            continue
        ano = aba["ano"] or hoje.year
        aviso_ano = [] if aba["ano"] else ["Ano não encontrado na aba: assumido %d" % ano]
        brutas, espera, _ = grades[aba["titulo"]]
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
                alvo = escolher_alvo(item, existentes.get(item["apto"], []))
                if alvo:
                    _preparar_atualizacao(con, item, alvo)
                dup = [] if alvo else [r for r in existentes.get(item["apto"], [])
                       if r["chave_import"] == chave or (r["i"] == item["entrada"] and r["f"] == item["saida"]
                                                         and sem_acento_maiusc(r["nome"]) == sem_acento_maiusc(item["hospede"]))]
                if dup:
                    raise _Ignorada(item, "ja_importada", "Já importada (existe no sistema)")
                depende = []
                for r in existentes.get(item["apto"], []):
                    if r["status"] == "ativa" and _sobrepoe(item["entrada"], item["saida"], r["i"], r["f"])                             and not (alvo and r["id"] == alvo["id"]):
                        if r["id"] in liberaveis:
                            depende.append(r["id"])
                            continue
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
                if depende:
                    item["depende_de"] = depende
                    item["avisos"].append("Depende do cancelamento marcado da reserva existente (#%s)" % ", #".join(map(str, depende)))
                if item.get("atualizacao"):
                    status, motivo = "atualizacao", "Atualiza a reserva existente: " + ", ".join(
                        d["rotulo"] for d in item["atualizacao"]["diferencas"])
                elif item["avisos"]:
                    status, motivo = "aviso", "; ".join(item["avisos"])
                saida_linha.update(item, status=status, categoria=categoria, motivo=motivo)
            except _Ignorada as e:
                if e.categoria in ("ja_importada", "atualizacao_bloqueada"):
                    # já está no sistema: continua valendo como "linha lida" para a fusão de abas e os conflitos,
                    # senão reimportar a mesma planilha daria um resultado diferente da primeira importação
                    aceitas.setdefault(e.item["apto"], []).append(dict(e.item, aba=aba["titulo"]))
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
    cont = {"prontas": 0, "avisos": 0, "erros": 0, "ignoradas": 0, "atualizacoes": 0}
    for l in linhas_out:
        cont[{"ok": "prontas", "aviso": "avisos", "erro": "erros", "ignorada": "ignoradas",
              "atualizacao": "atualizacoes"}[l["status"]]] += 1
    cont.update(_contar_cancelamentos(canc))
    cont["lista_espera"] = len([p for p in pedidos_out if not p["ja_importado"]])
    cont["espera_com_cartao"] = cartoes_espera
    return {"abas": descrever_abas(abas, titulos), "linhas": linhas_out, "pedidos": pedidos_out,
            "contadores": cont, "hoje": hoje_iso, "cancelamentos": canc}


def _preparar_cancelamentos(con, abas, titulos, existentes, hoje, incluir_passadas, grades):
    """Lê a seção CANCELAMENTOS e a grade das abas escolhidas e monta as propostas (nada é gravado)."""
    from .importador_cancel import interpretar_cancelamento, ler_cancelamentos
    from .importador_propostas import LIMITE_ITENS, montar_cancelamentos
    grade, itens, meses, truncado = [], [], set(), False
    for aba in abas:
        if aba["titulo"] not in titulos:
            continue
        ano = aba["ano"] or hoje.year
        lidas = 0
        for bruta in grades[aba["titulo"]][0]:
            try:
                it = _interpretar_reserva(bruta, ano, aba["mes"])
            except _Erro as e:
                it = e.item
            if it.get("apto"):
                grade.append({k: it[k] for k in ("apto", "entrada", "saida", "hospede")})
                lidas += 1
        if lidas:                      # aba sem nenhuma reserva lida (arquivo errado?) não serve para dizer o que "sumiu"
            meses.add((ano, aba["mes"]))
        for b in ler_cancelamentos(aba["linhas"], LIMITE_ITENS + 1 - len(itens)):
            if len(itens) >= LIMITE_ITENS:                  # o resto não é nem interpretado (custo de CPU)
                truncado = True
                break
            itens.append((aba["titulo"], interpretar_cancelamento(b, ano, aba["mes"])))
    por_apto = {}
    for lista in existentes.values():
        for r in lista:
            por_apto.setdefault(r["a"], []).append(r)
    return montar_cancelamentos(con, por_apto, itens, grade, meses, hoje.isoformat(), incluir_passadas, truncado) | {"total": len(itens)}


def _contar_cancelamentos(canc):
    p = canc["propostas"]
    conta = lambda f: len([x for x in p if f(x)])
    return {"cancelamentos": canc["total"], "cancel_alta": conta(lambda x: x["confianca"] == "alta" and not x["bloqueio"]),
            "cancel_media": conta(lambda x: x["confianca"] == "media" and not x["bloqueio"]),
            "cancel_sumiu": conta(lambda x: x["confianca"] == "sumiu" and not x["bloqueio"]),
            "cancel_bloqueadas": conta(lambda x: bool(x["bloqueio"])),
            "cancel_nao_encontradas": len(canc["nao_encontradas"]), "cancel_nao_identificadas": len(canc["nao_identificadas"])}


def _preparar_atualizacao(con, item, alvo):
    """Linha da planilha que corresponde a uma reserva ativa do sistema: guarda o alvo e as diferenças (ou deixa sem)."""
    from .importador_casar import diferencas, motivo_bloqueio
    dif = diferencas(alvo, item)
    if not dif:
        raise _Ignorada(item, "ja_importada", "Já importada (existe no sistema)")
    bloqueio = motivo_bloqueio(con, alvo)
    if bloqueio:
        raise _Ignorada(item, "atualizacao_bloqueada", "Existe no sistema com dados diferentes, mas não será atualizada: " + bloqueio.lower())
    if item.get("n_estimado"):
        item["n"] = alvo["n"]                          # planilha sem nº de pessoas: o que está no sistema vale
    item["atualizacao"] = {"id": alvo["id"], "versao": alvo["versao"], "nome": alvo["nome"], "entrada": alvo["i"],
                           "saida": alvo["f"], "diferencas": dif}


def _descrever_conflito(c):
    if c["origem"] == "banco":
        return "reserva já cadastrada #%s de %s (%s a %s)" % (c["id"], c["nome"], _br(c["entrada"]), _br(c["saida"]))
    return "linha %s da aba %s, %s (%s a %s)" % (c["linha"], c["aba"], c["nome"], _br(c["entrada"]), _br(c["saida"]))
