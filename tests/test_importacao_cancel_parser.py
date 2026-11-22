"""Parser da seção CANCELAMENTOS e casamento de nomes. Textos FICTÍCIOS no mesmo formato da planilha real."""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pousada.importador_cancel import ler_cancelamentos, interpretar_cancelamento, tirar_posto  # noqa: E402
from pousada.importador_casar import nomes_parecidos  # noqa: E402

TIT = (None, "CANCELAMENTOS", None, None, None)


def ler(*linhas, mes=7):
    brutas = ler_cancelamentos([TIT] + [(tuple(l) + (None,) * 5)[:5] for l in linhas])
    return [interpretar_cancelamento(b, 2026, mes) for b in brutas]


def um(*lin, mes=7):
    r = ler(lin, mes=mes)
    assert len(r) == 1
    return r[0]


@pytest.mark.parametrize("a, b, unidades", [
    (datetime(2026, 6, 2), "APTO 208 - CEL FULANO TESTE - 03/06 A 07/06", ["208"]),
    ("APTO 305", "NOME TESTE - 24 A 26/07 - WHATSAPP 11/06/26", ["305"]),
    ("204 E 304", "NOME TESTE - 04 A 06/07 - TITULAR DIA 02/07/2026", ["204", "304"]),
    ("303/304", "NOME TESTE - 21 A 23/08 - CANCELOU", ["303", "304"]),
    ("203,204", "NOME TESTE - 21 A 23/07", ["203", "204"]),
    (None, "APTOS 207/208/303 E CHALÉ C - NOME TESTE - 10 A 12/07", ["207", "208", "303", "Chalé C"]),
    ("CHALÉ E", "NOME TESTE - 15 A 19/07", ["Chalé E"]),
    ("CHALE B", "NOME TESTE - 15 A 19/07", ["Chalé B"]),
    ("203/204/205", "NOME TESTE - 27 A 30/07", ["203", "204", "205"]),
    (datetime(2026, 9, 28), "CHALÉ D - NOME TESTE - 02 A 05/07", ["Chalé D"]),
])
def test_unidades_em_varios_formatos(a, b, unidades):
    it = um(a, b)
    assert it["ok"] and it["unidades"] == unidades
    assert it["hospede"] in ("NOME TESTE", "CEL FULANO TESTE")


@pytest.mark.parametrize("b, entrada, saida", [
    ("NOME - 24 A 26/07 - X", "2026-07-24", "2026-07-26"),
    ("NOME - 31/07 A 03/08 - X", "2026-07-31", "2026-08-03"),
    ("NOME - 29 A 02/08 - X", "2026-07-29", "2026-08-02"),          # virada de mês sem o mês da entrada
    ("NOME - 29/07 A 01/08/26 - WHATSAPP 29/07/26", "2026-07-29", "2026-08-01"),
    ("NOME - 23 a 27/07", "2026-07-23", "2026-07-27"),
    ("NOME 24 A 26/07 CANCELOU", "2026-07-24", "2026-07-26"),      # sem hífens
    ("NOME - CANCELOU DIA 09/07/26", None, None),                  # sem período
])
def test_periodos(b, entrada, saida):
    it = um("305", b)
    assert it["ok"] and it["hospede"] == "NOME" and (it["entrada"], it["saida"]) == (entrada, saida)


def test_colunas_c_d_e_e_periodo_so_na_coluna_d():
    it = um("204 E 304", "NOME TESTE", 2, "13/06 A 15/06", "observação qualquer", mes=6)
    assert it["ok"] and it["unidades"] == ["204", "304"] and (it["entrada"], it["saida"]) == ("2026-06-13", "2026-06-15")
    assert it["hospede"] == "NOME TESTE"


def test_so_unidade_e_periodo_ou_so_unidade():
    it = um("203/204/205", None, None, "13/06 A 15/06", None, mes=6)
    assert it["ok"] and it["hospede"] == "" and it["entrada"] == "2026-06-13"
    it = um("CHALE E", None)
    assert not it["ok"] and "nome" in it["motivo"]


@pytest.mark.parametrize("a, b", [(None, "JULIO FULANO CANCELOU A RESERVA DE 29 A 31/05 - 02 APTOS"),
                                  ("TURMA AZUL", "x"), ("999", "NOME - 24 A 26/07"), (None, "texto solto")])
def test_nao_interpretavel_vira_item_informativo(a, b):
    it = um(a, b)
    assert not it["ok"] and it["motivo"] and it["texto"]


def test_cartao_nao_e_repetido():
    it = um("305", "NOME 4111 1111 1111 1111 - 24 A 26/07")
    assert not it["ok"] and it["texto"] == "" and "4111" not in str(it)


def test_secao_termina_em_total_titulo_ou_cabecalho():
    brutas = ler_cancelamentos([(l + (None,) * 5)[:5] for l in [
        TIT, ("305", "A - 24 A 26/07"), (None, "TOTAL PESSOAS MÊS - 108"), ("306", "B - 24 A 26/07"),
        (None, "CANCELAMENTOS"), ("307", "C - 24 A 26/07"), ("APTO", "NOME"), ("308", "D")]])
    assert [b["a"] for b in brutas] == ["305", "307"]


def test_posto_e_nomes_parecidos():
    assert tirar_posto("CEL FULANO DE TAL") == "FULANO DE TAL"
    assert nomes_parecidos("CEL Fulano de Tal", "FULANO DE TAL")
    assert nomes_parecidos("João Antônio Souza", "TEN JOAO ANTONIO DE SOUZA")
    assert not nomes_parecidos("Ana Maria Silva", "Ana Silva")                 # palavra a mais: na dúvida não casa
    assert not nomes_parecidos("Ana Silva", "Bruno Silva")
    assert not nomes_parecidos("Silva", "Souza")
    assert not nomes_parecidos("", "Ana Silva")
