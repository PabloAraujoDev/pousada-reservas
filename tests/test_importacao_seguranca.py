"""Endurecimento da importação: assinatura, zip bomb, limites, hash do arquivo e nada gravado em disco."""
import builtins
import io
import json
import zipfile
from datetime import date

import openpyxl
import pytest

from pousada.validacao_xlsx import MAX_ABAS, sha256_do_arquivo
from tests.test_importacao import corpo_confirmar, planilha_limpa, xlsx

HOJE = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _hoje(app):
    app.config["HOJE"] = HOJE


def enviar(cli, conteudo, nome="lista.xlsx", **form):
    dados = {"arquivo": (io.BytesIO(conteudo), nome)}
    dados.update(form)
    return cli.post("/api/importar/previa", data=dados, content_type="multipart/form-data")


def zip_de(partes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in partes.items():
            z.writestr(nome, conteudo)
    return buf.getvalue()


ESTRUTURA = {"[Content_Types].xml": "<x/>", "xl/workbook.xml": "<x/>"}


def test_arquivo_sem_assinatura_pk_e_recusado(cli):
    r = enviar(cli, b"%PDF-1.4 isto e um pdf disfarcado" + b"0" * 100)
    assert r.status_code == 400 and "assinatura" in r.get_json()["erro"]
    r = enviar(cli, b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    assert r.status_code == 400


def test_zip_que_nao_e_planilha_e_recusado(cli):
    r = enviar(cli, zip_de({"qualquer.txt": "oi"}))
    assert r.status_code == 400 and "estrutura" in r.get_json()["erro"]
    r = enviar(cli, b"PK\x03\x04" + b"lixo" * 50)                       # começa com PK mas está quebrado
    assert r.status_code == 400


def test_zip_bomb_por_tamanho_descompactado(cli):
    bomba = zip_de(dict(ESTRUTURA, **{"xl/worksheets/sheet1.xml": "0" * (60 * 1024 * 1024)}))
    assert len(bomba) < 1024 * 1024                                     # pequeno no disco, enorme na memória
    r = enviar(cli, bomba)
    assert r.status_code == 400 and "descompactada" in r.get_json()["erro"]


def test_zip_bomb_por_taxa_de_compressao(cli):
    bomba = zip_de(dict(ESTRUTURA, **{"xl/worksheets/sheet1.xml": "0" * (8 * 1024 * 1024)}))
    r = enviar(cli, bomba)
    assert r.status_code == 400 and "compressão" in r.get_json()["erro"]


def test_partes_demais(cli):
    partes = dict(ESTRUTURA)
    partes.update({"xl/p%d.xml" % k: str(k) for k in range(600)})
    assert enviar(cli, zip_de(partes)).status_code == 400


def test_abas_demais(cli):
    wb = openpyxl.Workbook()
    for k in range(MAX_ABAS + 1):
        wb.create_sheet("BOA ESPERANÇA OUTUBRO %d" % k)
    buf = io.BytesIO()
    wb.save(buf)
    r = enviar(cli, buf.getvalue())
    assert r.status_code == 400 and "abas demais" in r.get_json()["erro"]


def test_planilha_normal_continua_funcionando_e_devolve_o_hash(cli):
    conteudo = xlsx(planilha_limpa())
    r = enviar(cli, conteudo)
    assert r.status_code == 200
    j = r.get_json()
    assert j["sha256"] == sha256_do_arquivo(conteudo) and len(j["sha256"]) == 64 and j["importado_antes"] is None


def test_mesmo_arquivo_gera_aviso_mas_nao_bloqueia_nem_duplica(cli):
    conteudo = xlsx(planilha_limpa())
    j = enviar(cli, conteudo).get_json()
    corpo = dict(corpo_confirmar(j), sha256=j["sha256"])
    primeira = cli.post("/api/importar/confirmar", json=corpo)
    assert primeira.status_code == 201 and primeira.get_json()["criadas"] == 3
    assert primeira.get_json()["importado_antes"] is None
    j2 = enviar(cli, conteudo).get_json()
    assert j2["importado_antes"]["lote_id"] == primeira.get_json()["lote_id"]       # aviso na prévia
    assert j2["importado_antes"]["usuario"] == "admin"
    segunda = cli.post("/api/importar/confirmar", json=dict(corpo_confirmar(j2, ("ok", "aviso", "ignorada")), sha256=j2["sha256"]))
    assert segunda.status_code == 201 and segunda.get_json()["criadas"] == 0        # idempotência por chave continua
    assert segunda.get_json()["importado_antes"] is not None                        # aviso na confirmação
    assert len(cli.get("/api/reservas").get_json()) == 3


def test_arquivo_alterado_tem_outro_hash(cli):
    a = enviar(cli, xlsx(planilha_limpa())).get_json()["sha256"]
    outra = planilha_limpa()
    primeira_aba = next(iter(outra))
    outra[primeira_aba] = list(outra[primeira_aba]) + [["301", "Outro Hóspede", 1, "20/10 A 22/10", ""]]
    assert enviar(cli, xlsx(outra)).get_json()["sha256"] != a


def test_sha256_invalido_e_ignorado(app, cli):
    j = enviar(cli, xlsx(planilha_limpa())).get_json()
    r = cli.post("/api/importar/confirmar", json=dict(corpo_confirmar(j), sha256="<script>"))
    assert r.status_code == 201
    j2 = enviar(cli, xlsx(planilha_limpa())).get_json()
    assert j2["importado_antes"] is None                                           # nada gravado com valor inválido


def test_historico_do_lote_guarda_o_hash(cli):
    j = enviar(cli, xlsx(planilha_limpa())).get_json()
    lote = cli.post("/api/importar/confirmar", json=dict(corpo_confirmar(j), sha256=j["sha256"])).get_json()["lote_id"]
    reg = cli.get("/api/historico?entidade=importacao&acao=importar").get_json()[0]
    assert reg["entidade_id"] == lote and reg["depois"]["sha256"] == j["sha256"] and reg["depois"]["criadas"] == 3


def test_previa_nao_grava_nada_em_disco(cli, monkeypatch):
    conteudo = xlsx(planilha_limpa())
    abrir_original = builtins.open
    escritas = []

    def vigiar(arquivo, modo="r", *a, **k):
        if any(c in str(modo) for c in "wax+"):
            escritas.append(str(arquivo))
        return abrir_original(arquivo, modo, *a, **k)
    monkeypatch.setattr(builtins, "open", vigiar)
    assert enviar(cli, conteudo).status_code == 200
    assert escritas == []
