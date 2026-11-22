"""Ajudantes dos testes de importação com cancelamentos/atualizações (planilhas FICTÍCIAS)."""
from pousada.db import conectar
from tests.test_importacao import HOJE, NOV, OUT, previa, xlsx  # noqa: F401

CAB = (None, "CANCELAMENTOS")
BASE = {NOV: [(201, "Ana Teste", 2, "05/11 A 07/11", "PAGO"), None,
              (202, "Bruno Teste", 3, "10/11 A 12/11", ""), None,
              ("CHALE A", "Carla Teste", 4, "15/11 A 18/11", "")]}


def sql(app, comando, args=(), gravar=False):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return [tuple(r) for r in con.execute(comando, args).fetchall()]
    finally:
        con.close()


def corpo(j):
    """O que a tela envia ao confirmar, com as caixas padrão da prévia."""
    marcadas = {p["id"] for p in j["cancelamentos"]["propostas"] if p["marcada"]}
    linhas, atual = [], []
    for l in j["linhas"]:
        dados = {"aba": l["aba"], "linha": l["linha"], "nome": l["hospede"], "extras": "\n".join(l["extras"]), "n": l["n"],
                 "i": l["entrada"], "f": l["saida"], "p": l["pagamento"], "o": l["texto_pagamento"], "grupo": l["grupo"]}
        if l["status"] in ("ok", "aviso") and all(d in marcadas for d in l.get("depende_de", [])):
            linhas.append(dict(dados, a=l["apto"]))
        if l["status"] == "atualizacao":
            a = l["atualizacao"]
            atual.append(dict(dados, id=a["id"], versao=a["versao"], selo=a["selo"], selo_em=a["selo_em"]))
    canc = [{"id": p["id"], "versao": p["versao"], "origem": p["origem"], "aba": p["aba"], "linha": p["linha"], "selo": p["selo"], "selo_em": p["selo_em"]}
            for p in j["cancelamentos"]["propostas"] if p["id"] in marcadas]
    return {"arquivo": "t.xlsx", "linhas": linhas, "pedidos": [], "cancelamentos": canc, "atualizacoes": atual}


def importar_base(cli):
    j = previa(cli, BASE, abas=[NOV]).get_json()
    r = cli.post("/api/importar/confirmar", json=corpo(j))
    assert r.status_code == 201 and r.get_json()["criadas"] == 3
    return r.get_json()["lote_id"]


def ids(cli):
    return {(x["a"], x["nome"]): x["id"] for x in cli.get("/api/reservas").get_json()}
