"""Casamento da planilha com as reservas do sistema: atualizações, cancelamentos e "sumiu da planilha".

Nada aqui grava. A gravação (sempre revalidada) está em importador_aplicar.py.
"""
import difflib
import re

from .importador_cancel import tirar_posto
from .importador import sem_acento_maiusc

BAGATELA = {"DOS", "DAS", "DEL", "VON", "VAN"}
CAMPOS_PLANILHA = ("nome", "extras", "n", "i", "f", "p", "o", "grupo")
PRESERVAR_SE_VAZIO = ("extras", "o", "grupo")      # texto que também se edita no sistema: vazio na planilha não apaga
ROTULOS = {"nome": "Nome", "extras": "Acompanhantes", "n": "Pessoas", "i": "Entrada", "f": "Saída", "p": "Pagamento",
           "o": "Observação", "grupo": "Grupo"}


def sobrepoe(i1, f1, i2, f2):
    return i1 < f2 and i2 < f1


def _chaves(nome):
    return {t for t in nome.split() if len(t) >= 3 and t not in BAGATELA}


def _um_erro_de_digitacao(a, b):
    """Palavras que diferem em UM caractere (troca, falta ou sobra), só se ambas têm 6+ letras e a diferença
    não é a letra final a/o/e (gênero: RAFAEL/RAFAELA, DANIEL/DANIELA)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 6 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        dif = [k for k in range(len(a)) if a[k] != b[k]]
        return len(dif) == 1 and dif[0] != len(a) - 1
    curta, longa = (a, b) if len(a) < len(b) else (b, a)
    for k in range(len(longa)):
        if longa[:k] + longa[k + 1:] == curta:
            return k != len(longa) - 1 or longa[k] not in "AOES"
    return False


def nomes_parecidos(a, b):
    """Mesmo hóspede? Sem acento, caixa e posto. Estrito: na dúvida NÃO casa (vira "nova reserva + sumiu", que o
    administrador vê). Exige as mesmas palavras-chave (sem DE/DA/DOS...), na mesma quantidade: sufixo (JUNIOR, NETO,
    COSTA) e prenome diferente (ANA PAULA x ANA CLARA, JOAO SILVA x JOSE SILVA) não casam. Só se perdoa erro de
    digitação de 1 caractere em palavra com 6+ letras (nunca o a/o final). Nome de uma só palavra: só se o texto
    inteiro, com o posto, for igual."""
    inteiro_a, inteiro_b = " ".join(sem_acento_maiusc(a).replace(".", " ").split()), " ".join(sem_acento_maiusc(b).replace(".", " ").split())
    x, y = tirar_posto(sem_acento_maiusc(a)), tirar_posto(sem_acento_maiusc(b))
    if not x or not y:
        return False
    if len(x.split()) < 2 or len(y.split()) < 2:
        return inteiro_a == inteiro_b
    kx, ky = sorted(_chaves(x)), sorted(_chaves(y))
    if len(kx) < 2 or len(kx) != len(ky):
        return False
    resto = list(ky)
    for p in kx:                                      # cada palavra precisa de uma par ainda não usada
        par = next((q for q in resto if _um_erro_de_digitacao(p, q)), None)
        if par is None:
            return False
        resto.remove(par)
    return True


def motivo_bloqueio(con, r):
    """Por que esta reserva NÃO pode ser cancelada/alterada pela importação ('' se pode)."""
    if r["checkin_em"]:
        return "O check-in já foi feito"
    if r["conta_aberta_em"]:
        return "Apartamento liberado com a conta ainda aberta"
    if con.execute("SELECT 1 FROM despesa_lancamento WHERE reserva_id=? LIMIT 1", (r["id"],)).fetchone():
        return "A conta tem despesas lançadas"
    if con.execute("SELECT 1 FROM pagamento WHERE reserva_id=? LIMIT 1", (r["id"],)).fetchone():
        return "A conta tem pagamentos registrados"
    return ""


def escolher_alvo(item, candidatas):
    """Reserva ATIVA do sistema que a linha da planilha atualiza (mesmo apto, período sobreposto, nome parecido)."""
    achadas = [r for r in candidatas if r["status"] == "ativa" and sobrepoe(item["entrada"], item["saida"], r["i"], r["f"])
               and nomes_parecidos(item["hospede"], r["nome"])]
    achadas.sort(key=lambda r: ((r["i"], r["f"]) != (item["entrada"], item["saida"]),
                                -difflib.SequenceMatcher(None, sem_acento_maiusc(r["nome"]), sem_acento_maiusc(item["hospede"])).ratio()))
    return achadas[0] if achadas else None


def _txt(v):
    return re.sub(r"\s+", " ", v or "").strip()


def _mostrar(campo, v):
    """Valor como aparece na prévia (datas dd/mm/aaaa)."""
    t = str(v if v is not None else "")[:200]
    return "%s/%s/%s" % (t[8:10], t[5:7], t[:4]) if campo in ("i", "f") and len(t) == 10 else t


def diferencas(r, item):
    """Campo a campo: o que a planilha traz de diferente da reserva do sistema (só os campos da planilha)."""
    novo = {"nome": item["hospede"], "extras": "\n".join(item["extras"]), "n": item["n"], "i": item["entrada"],
            "f": item["saida"], "p": item["pagamento"], "o": item["texto_pagamento"], "grupo": item["grupo"] or ""}
    out = []
    for c in CAMPOS_PLANILHA:
        if c == "n" and item.get("n_estimado"):
            continue                                  # planilha sem nº de pessoas: não mexe no que está no sistema
        antes, depois = r[c], novo[c]
        if c in PRESERVAR_SE_VAZIO and not _txt(depois) and _txt(antes):
            continue                                  # planilha em branco não apaga o que foi escrito no sistema
        igual = sem_acento_maiusc(antes) == sem_acento_maiusc(depois) if c == "nome" else (
            _txt(antes) == _txt(depois) if isinstance(antes, str) else antes == depois)
        if not igual:
            out.append({"campo": c, "rotulo": ROTULOS[c], "antes": _mostrar(c, antes), "depois": _mostrar(c, depois)})
    return out


def _dados_prop(r, **extra):
    return dict({"id": r["id"], "versao": r["versao"], "apto": r["a"], "nome": r["nome"], "entrada": r["i"],
                 "saida": r["f"]}, **extra)


def casar_cancelamento(item, aba, por_apto, hoje_iso, incluir_passadas):
    """[(unidade, reserva, confianca, motivo)] e [unidades sem casamento] para um item interpretado (ok)."""
    achadas, faltam = [], []
    for u in item["unidades"]:
        melhor = None
        for r in por_apto.get(u, []):
            if r["status"] != "ativa" or (r["f"] < hoje_iso and not incluir_passadas):
                continue
            parecido = bool(item["hospede"]) and nomes_parecidos(item["hospede"], r["nome"])
            if item["entrada"]:
                if not sobrepoe(item["entrada"], item["saida"], r["i"], r["f"]):
                    continue
                igual = (item["entrada"], item["saida"]) == (r["i"], r["f"])
                if parecido:
                    cand = (3 + igual, r, "alta", "mesmo apto, período e nome parecido")
                elif igual:
                    cand = (1, r, "media", "mesmo apto e período, mas o nome é diferente")
                else:
                    continue
            elif parecido:
                cand = (2, r, "media", "mesmo apto e nome parecido; a linha não tem período")
            else:
                continue
            if melhor is None or cand[0] > melhor[0]:
                melhor = cand
        if melhor:
            achadas.append((u,) + melhor[1:])
        else:
            faltam.append(u)
    return achadas, faltam
