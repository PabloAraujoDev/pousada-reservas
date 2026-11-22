"""Gravação (sempre REVALIDADA, dentro da transação da importação) de cancelamentos e atualizações de reservas existentes.

Cada função devolve a lista de problemas (vazia = tudo certo); quem chama desfaz a transação se houver problema.
Só mexe nos campos que a planilha fornece (nome, extras, n, i, f, p, o, grupo): diária, tipo, hóspedes, placa,
pagamentos, notas e governança nunca são tocados.
"""
import hashlib
import hmac
import json

from .historico import diferenca, registrar
from .importador import aba_curta, chave_importacao, sem_acento_maiusc
from .importador_casar import CAMPOS_PLANILHA, PRESERVAR_SE_VAZIO, motivo_bloqueio, nomes_parecidos, sobrepoe
from .regras import agora, agora_local, existe_conflito, validar_reserva

LIMITE_ALTERACOES = 500


# ---- selo: a prévia assina o que propõe; o servidor só aceita o que ele mesmo propôs (o cliente não decide a origem).
# O selo é amarrado ao usuário que leu a planilha e vence em 2 horas; a chave é derivada da chave secreta com prefixo
# de domínio (não serve para mais nada no sistema).

VALIDADE_SELO = 2 * 3600
TOLERANCIA_RELOGIO = 300
MSG_SELO = "%s que não veio da sua prévia (ou a prévia venceu): refaça a prévia"


class Selagem:
    """Chave derivada + usuário + hora, para assinar na prévia e conferir na confirmação."""

    def __init__(self, chave_secreta, usuario_id, agora_ts):
        self.chave = hmac.new(str(chave_secreta).encode("utf-8"), b"importacao-selo-v1", hashlib.sha256).digest()
        self.usuario, self.agora = usuario_id, agora_ts


def selagem_da_requisicao(config, usuario_id):
    """Selagem de agora (os testes fixam config AGORA)."""
    return Selagem(config["SECRET_KEY"], usuario_id, (config.get("AGORA") or agora_local()).timestamp())


def _selo(sel, partes):
    msg = json.dumps([sel.usuario] + partes, ensure_ascii=False, separators=(",", ":"))
    return hmac.new(sel.chave, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def selo_cancelamento(sel, it):
    return _selo(sel, ["c", it.get("selo_em"), it.get("id"), it.get("versao"), it.get("origem"), it.get("aba"), it.get("linha")])


def selo_atualizacao(sel, it):
    return _selo(sel, ["u", it.get("selo_em"), it.get("id"), it.get("versao")] + [it.get(c) for c in CAMPOS_PLANILHA])


def selar_previa(previa, sel):
    """Põe o selo (e a hora em que foi dado) em cada proposta de cancelamento e em cada atualização da prévia."""
    em = int(sel.agora)
    for p in previa["cancelamentos"]["propostas"]:
        p["selo_em"] = em
        p["selo"] = selo_cancelamento(sel, p)
    for l in previa["linhas"]:
        if l.get("status") == "atualizacao":
            dados = {"nome": l["hospede"], "extras": "\n".join(l["extras"]), "n": l["n"], "i": l["entrada"], "f": l["saida"],
                     "p": l["pagamento"], "o": l["texto_pagamento"], "grupo": l["grupo"]}
            l["atualizacao"]["selo_em"] = em
            l["atualizacao"]["selo"] = selo_atualizacao(sel, dict(dados, id=l["atualizacao"]["id"], versao=l["atualizacao"]["versao"],
                                                                   selo_em=em))


def conferir_selos(cancelamentos, atualizacoes, sel):
    """Problemas (lista) dos itens sem selo válido (da prévia deste usuário, ainda dentro da validade)."""
    problemas = []
    for itens, fn, rotulo in ((cancelamentos, selo_cancelamento, "Cancelamento"), (atualizacoes, selo_atualizacao, "Atualização")):
        for k, it in enumerate(itens):
            if not isinstance(it, dict) or not _selo_ok(it, fn(sel, it), sel):
                problemas.append(dict(_ref(it, k), motivo=MSG_SELO % rotulo))
            elif it.get("aba") and not aba_curta(it["aba"]):
                problemas.append(dict(_ref(it, k), motivo="Título de aba inválido"))
    return problemas


def _selo_ok(it, esperado, sel):
    selo, em = it.get("selo"), it.get("selo_em")
    if not isinstance(em, int) or isinstance(em, bool) or not -TOLERANCIA_RELOGIO <= sel.agora - em <= VALIDADE_SELO:
        return False
    if not (isinstance(selo, str) and len(selo) == 64 and selo.isascii() and all(c in "0123456789abcdef" for c in selo)):
        return False
    return hmac.compare_digest(selo.encode("ascii"), esperado.encode("ascii"))


def _ref(it, k):
    aba = it.get("aba") if isinstance(it, dict) else ""
    return {"aba": aba_curta(aba),
            "linha": it.get("linha") if isinstance(it, dict) and isinstance(it.get("linha"), int) else None, "indice": k}


def _descr(r):
    return "%s (%s a %s)" % (r["a"], r["i"][8:10] + "/" + r["i"][5:7], r["f"][8:10] + "/" + r["f"][5:7])


def _carregar(con, it, ref, hoje_iso, problemas, exige_importada=False):
    """Reserva ativa, na versão que o administrador viu e sem check-in/conta. None (e um problema) se não puder mexer."""
    rid, versao = (it.get("id"), it.get("versao")) if isinstance(it, dict) else (None, None)
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (rid, versao)):
        problemas.append(dict(ref, motivo="Item de reserva inválido"))
        return None
    r = con.execute("SELECT * FROM reservas WHERE id=?", (rid,)).fetchone()
    motivo = ""
    if not r:
        motivo = "A reserva #%d não existe mais" % rid
    elif r["status"] != "ativa":
        motivo = "A reserva %s já não está ativa" % _descr(r)
    elif r["versao"] != versao:
        motivo = "A reserva %s foi alterada por outra pessoa depois da prévia; leia a planilha de novo" % _descr(r)
    elif exige_importada and (r["lote_id"] is None or r["i"] < hoje_iso):
        motivo = "A reserva %s não pode ser cancelada por ausência na planilha (criada à mão ou já iniciada)" % _descr(r)
    else:
        motivo = motivo_bloqueio(con, r)
        motivo = "A reserva %s não foi alterada: %s" % (_descr(r), motivo.lower()) if motivo else ""
    if motivo:
        problemas.append(dict(ref, motivo=motivo))
        return None
    return r


def _guardar(con, lote_id, r, tipo, antes):
    con.execute("INSERT INTO importacao_alteracao (lote_id, reserva_id, tipo, antes, versao_depois) VALUES (?,?,?,?,?)",
                (lote_id, r["id"], tipo, json.dumps(antes, ensure_ascii=False), r["versao"] + 1))


def aplicar_cancelamentos(con, itens, lote_id, ator, hoje_iso, sel):
    problemas = []
    for k, it in enumerate(itens):
        ref = _ref(it, k)
        if not isinstance(it, dict) or not _selo_ok(it, selo_cancelamento(sel, it), sel):
            problemas.append(dict(ref, motivo=MSG_SELO % "Cancelamento"))
            continue
        r = _carregar(con, it, ref, hoje_iso, problemas, exige_importada=it.get("origem") == "sumiu" if isinstance(it, dict) else False)
        if r is None:
            continue
        if it.get("origem") == "sumiu":
            motivo = "Cancelada: reserva de importação anterior que não consta mais na planilha importada"
        else:
            motivo = "Cancelada conforme planilha importada (aba %s, linha %s)" % (ref["aba"] or "?", ref["linha"] or "?")
        t = agora()
        con.execute("UPDATE reservas SET status='cancelada', motivo_cancelamento=?, cancelado_por=?, cancelado_em=?, alterado=?,"
                    " versao=versao+1 WHERE id=?", (motivo[:300], ator["login"], t, t, r["id"]))
        _guardar(con, lote_id, r, "cancelamento", {"status": "ativa"})
        registrar(con, "cancelar", "reserva", r["id"], {"status": "ativa"}, {"status": "cancelada", "lote": lote_id}, ator)
    return problemas


def aplicar_atualizacoes(con, itens, lote_id, ator, hoje_iso, sel):
    problemas = []
    for k, it in enumerate(itens):
        ref = _ref(it, k)
        if not isinstance(it, dict) or not _selo_ok(it, selo_atualizacao(sel, it), sel):
            problemas.append(dict(ref, motivo=MSG_SELO % "Atualização"))
            continue
        r = _carregar(con, it, ref, hoje_iso, problemas)
        if r is None:
            continue
        dados, erro = validar_reserva(dict({c: it.get(c) for c in CAMPOS_PLANILHA}, a=r["a"]))
        if erro:
            problemas.append(dict(ref, motivo="Atualização da reserva %s recusada: %s" % (_descr(r), erro)))
            continue
        if not sobrepoe(dados["i"], dados["f"], r["i"], r["f"]) or not nomes_parecidos(dados["nome"], r["nome"]):
            problemas.append(dict(ref, motivo="A atualização da reserva %s não corresponde à reserva do sistema" % _descr(r)))
            continue
        if existe_conflito(con, r["a"], dados["i"], dados["f"], ignorar_id=r["id"]):
            problemas.append(dict(ref, motivo="Conflito: %s já está reservada por outra pessoa no novo período" % r["a"]))
            continue
        if sem_acento_maiusc(dados["nome"]) == sem_acento_maiusc(r["nome"]):
            dados["nome"] = r["nome"]                  # só maiúsculas/acentos diferentes: não é mudança
        for c in PRESERVAR_SE_VAZIO:                   # mesma regra da prévia: planilha em branco não apaga texto do sistema
            if not (dados[c] or "").strip() and (r[c] or "").strip():
                dados[c] = r[c]
        grupo = dados["grupo"] if dados["grupo"] is not None else r["grupo"]
        chave = chave_importacao(r["a"], dados["i"], dados["f"], dados["nome"]) if r["chave_import"] else None
        _guardar(con, lote_id, r, "atualizacao", {c: r[c] for c in CAMPOS_PLANILHA} | {"chave_import": r["chave_import"]})
        con.execute("UPDATE reservas SET nome=?, extras=?, n=?, i=?, f=?, p=?, o=?, grupo=?, chave_import=?, alterado=?,"
                    " versao=versao+1 WHERE id=?",
                    (dados["nome"], dados["extras"], dados["n"], dados["i"], dados["f"], dados["p"], dados["o"], grupo,
                     chave, agora(), r["id"]))
        antes, depois = diferenca(r, {**dados, "tipo": r["tipo"]})
        registrar(con, "alterar", "reserva", r["id"], antes, dict(depois, lote=lote_id), ator)
    return problemas


def desfazer_alteracoes(con, lote_id, ator):
    """Reverte cancelamentos e atualizações do lote, só nas reservas que ninguém mexeu depois. Devolve (revertidas, puladas)."""
    revertidas = puladas = 0
    for a in con.execute("SELECT * FROM importacao_alteracao WHERE lote_id=? ORDER BY id DESC", (lote_id,)).fetchall():
        r = con.execute("SELECT * FROM reservas WHERE id=?", (a["reserva_id"],)).fetchone()
        antes = json.loads(a["antes"])
        if not r or r["versao"] != a["versao_depois"] or motivo_bloqueio(con, r):
            puladas += 1               # mexeram nela depois (ou já tem check-in, conta aberta, despesa ou pagamento): não reverte
            continue
        if a["tipo"] == "cancelamento":
            if existe_conflito(con, r["a"], r["i"], r["f"], ignorar_id=r["id"]):
                puladas += 1
                continue
            con.execute("UPDATE reservas SET status='ativa', motivo_cancelamento=NULL, cancelado_por=NULL, cancelado_em=NULL,"
                        " alterado=?, versao=versao+1 WHERE id=?", (agora(), r["id"]))
            registrar(con, "reativar", "reserva", r["id"], {"status": "cancelada"}, {"status": "ativa", "lote": lote_id}, ator)
        else:
            if existe_conflito(con, r["a"], antes["i"], antes["f"], ignorar_id=r["id"]):
                puladas += 1
                continue
            con.execute("UPDATE reservas SET nome=?, extras=?, n=?, i=?, f=?, p=?, o=?, grupo=?, chave_import=?, alterado=?,"
                        " versao=versao+1 WHERE id=?", tuple(antes[c] for c in CAMPOS_PLANILHA) + (antes["chave_import"], agora(), r["id"]))
            ant, dep = diferenca(r, dict(antes, a=r["a"], tipo=r["tipo"]))
            registrar(con, "alterar", "reserva", r["id"], ant, dict(dep, lote=lote_id), ator)
        revertidas += 1
    con.execute("DELETE FROM importacao_alteracao WHERE lote_id=?", (lote_id,))
    return revertidas, puladas
