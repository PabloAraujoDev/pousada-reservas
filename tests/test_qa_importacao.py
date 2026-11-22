"""QA da importação-fonte-da-verdade: regressões achadas na simulação com a planilha real (dados FICTÍCIOS aqui)."""
import pytest

from pousada.importador_casar import nomes_parecidos
from tests.apoio_importacao_cancel import corpo, previa, sql
from tests.test_importacao import NOV, OUT, app  # noqa: F401  (fixture com HOJE fixo)


def confirmar(cli, j):
    r = cli.post("/api/importar/confirmar", json=corpo(j))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


@pytest.mark.parametrize("a,b,esperado", [
    ("JOAO SILVA", "JOSE SILVA", False),            # sobrenome comum não basta
    ("MARIA SILVA", "MARTA SILVA", False),
    ("CAP SILVA", "TEN SILVA", False),              # postos diferentes, uma só palavra
    ("JOSE SANTOS", "JOSE SANTANA", False),
    ("CEL JOSE DA SILVA", "TEN JOSE DA SILVA", True),   # promoção: mesmo hóspede
    ("ALEXANDER FERREIRA DE MAGALHAES", "Alexsander Ferreira de Magalhães", True),
    ("SILVA JOAO", "JOAO SILVA", True),
    ("Ana Teste", "Ana Teste Junior", False),         # sufixo: na dúvida não casa
    ("ANA PAULA SILVA", "ANA CLARA SILVA", False),
    ("RAFAEL MOURA", "RAFAELA MOURA", False),
])
def test_nomes_parecidos_prudente(a, b, esperado):
    assert nomes_parecidos(a, b) is esperado


def test_reimportar_mesma_planilha_com_virada_de_mes_nao_propoe_nada(cli):
    """Mesma reserva nas abas de outubro e novembro com o nome escrito diferente: 1ª importação fica com a de outubro;
    reimportar a MESMA planilha não pode propor 'atualizar' com a versão de novembro."""
    planilha = {OUT: [(201, "Alexander Ferreira Magalhaes", 2, "29/10 A 01/11", "PAGO"), (None, "Anair Magalhaes", None, None, None)],
                NOV: [(201, "Alexsander Ferreira Magalhaes", 2, "29/10 A 01/11", "")]}
    j = previa(cli, planilha).get_json()
    c1 = confirmar(cli, j)
    antes = sql(cli.application, "SELECT id, nome, extras, p, o, versao FROM reservas")
    j2 = previa(cli, planilha).get_json()
    assert j2["contadores"].get("atualizacoes", 0) == 0
    assert [l["status"] for l in j2["linhas"] if l["status"] == "atualizacao"] == []
    assert c1["criadas"] == len(antes) == 1
    assert sql(cli.application, "SELECT id, nome, extras, p, o, versao FROM reservas") == antes


def test_atualizar_com_n_pessoas_vazio_na_planilha_mantem_o_n_do_sistema(cli):
    base = {NOV: [(201, "Ana Teste Souza", 4, "05/11 A 07/11", "PAGO")]}
    confirmar(cli, previa(cli, base, abas=[NOV]).get_json())
    nova = {NOV: [(201, "Ana Teste Souza", None, "05/11 A 08/11", "PAGO")]}
    j = previa(cli, nova, abas=[NOV]).get_json()
    assert j["contadores"]["atualizacoes"] == 1
    confirmar(cli, j)
    n, f = sql(cli.application, "SELECT n, f FROM reservas")[0]
    assert (n, f) == (4, "2026-11-08")


def test_atualizar_com_campos_de_texto_vazios_na_planilha_nao_apaga_o_do_sistema(cli):
    base = {NOV: [(201, "Ana Teste Souza", 2, "05/11 A 07/11", "TURMA AMIGOS - PAGO"), (None, "Acompanhante Um", None, None, None)]}
    confirmar(cli, previa(cli, base, abas=[NOV]).get_json())
    nova = {NOV: [(201, "Ana Teste Souza", 2, "05/11 A 08/11", "")]}
    j = previa(cli, nova, abas=[NOV]).get_json()
    assert j["contadores"]["atualizacoes"] == 1
    rotulos = [d["campo"] for l in j["linhas"] if l["status"] == "atualizacao" for d in l["atualizacao"]["diferencas"]]
    assert "extras" not in rotulos and "o" not in rotulos and "grupo" not in rotulos
    confirmar(cli, j)
    extras, o, grupo = sql(cli.application, "SELECT extras, o, grupo FROM reservas")[0]
    assert extras == "Acompanhante Um" and o == "TURMA AMIGOS - PAGO" and grupo.startswith("TURMA")


def test_sumiu_em_massa_vem_desmarcado_e_avisa(app, cli):
    grade = [(201 + k, "Hospede Numero %d Silva" % k, 2, "05/11 A 07/11", "") for k in range(0, 8)]
    confirmar(cli, previa(cli, {NOV: grade}, abas=[NOV]).get_json())
    # planilha cortada: sobraram 2 das 8 reservas deste mês
    j = previa(cli, {NOV: grade[:2]}, abas=[NOV]).get_json()
    sumiu = [p for p in j["cancelamentos"]["propostas"] if p["confianca"] == "sumiu"]
    assert len(sumiu) == 6 and not any(p["marcada"] for p in sumiu)
    assert j["cancelamentos"]["aviso_massa"] == [{"mes": "2026-11", "sumiram": 6, "total": 8}]
    # poucas reservas sumindo continua marcado (caso normal)
    j = previa(cli, {NOV: grade[:7]}, abas=[NOV]).get_json()
    sumiu = [p for p in j["cancelamentos"]["propostas"] if p["confianca"] == "sumiu"]
    assert len(sumiu) == 1 and sumiu[0]["marcada"] and j["cancelamentos"]["aviso_massa"] == []
