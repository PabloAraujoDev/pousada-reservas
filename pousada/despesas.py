"""Despesas da reserva (conta do hóspede): regras de validação, totais e estorno.

Tudo em centavos inteiros. Aqui não há Flask nem permissão: quem decide o que cada perfil recebe são as rotas
(rotas_despesas.py). O log é imutável (triggers da migração 012): corrigir é estornar.
"""
from datetime import datetime

from .cartao import MSG_CARTAO, _luhn, contem_numero_cartao
from .regras import (CATEGORIAS_DESPESA, MAX_DESPESA_QTD, MAX_DESPESA_UNIT, MAX_SALDO_DESPESAS, tem_texto_visivel, texto_limpo)

MSG_CHARS = "%s contém caracteres não permitidos (controles invisíveis ou de inversão do texto)"


class Recusa(Exception):
    """Pedido recusado por regra de negócio; 'status' é o código HTTP (400, 409 ou 422)."""

    def __init__(self, mensagem, status=422):
        super().__init__(mensagem)
        self.mensagem, self.status = mensagem, status


def reais(centavos):
    """12345 -> 'R$ 123,45' (usado só em mensagens de erro de limite, nunca com valor do usuário)."""
    inteiro, cent = divmod(centavos, 100)
    return "R$ {:,}".format(inteiro).replace(",", ".") + ",%02d" % cent


def _inteiro(v):
    return isinstance(v, int) and not isinstance(v, bool)


def texto_validado(v, rotulo, minimo, maximo):
    """Texto limpo, aparado, com tamanho entre minimo e maximo e sem cara de número de cartão."""
    if not isinstance(v, str):
        raise Recusa("Informe %s" % rotulo)
    if not texto_limpo(v):
        raise Recusa(MSG_CHARS % rotulo.capitalize())
    v = v.strip()
    if not tem_texto_visivel(v):
        raise Recusa("Informe %s" % rotulo)       # só espaços/caracteres invisíveis equivale a vazio
    if not minimo <= len(v) <= maximo:
        raise Recusa("%s deve ter de %d a %d caracteres" % (rotulo.capitalize(), minimo, maximo))
    if contem_numero_cartao(v):
        raise Recusa(MSG_CARTAO)         # nunca repete o texto recebido
    return v


_texto = texto_validado       # (nome público para as notas reaproveitarem a mesma regra)


def _chave_parece_cartao(chave):
    d = chave.replace("-", "").replace("_", "")
    return d.isdigit() and 13 <= len(d) <= 19 and _luhn(d)


def validar_lancamento(corpo):
    """Corpo do POST -> dict limpo (categoria, descricao, quantidade, valor_unit_centavos, chave). Recusa com Recusa."""
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    if corpo.get("categoria") not in CATEGORIAS_DESPESA:
        raise Recusa("Categoria inválida")
    descricao = _texto(corpo.get("descricao"), "a descrição", 2, 80)
    qtd, unit, chave = corpo.get("quantidade"), corpo.get("valor_unit_centavos"), corpo.get("chave")
    if not _inteiro(qtd) or not 1 <= qtd <= MAX_DESPESA_QTD:
        raise Recusa("Quantidade inválida (use um número inteiro de 1 a %d)" % MAX_DESPESA_QTD)
    if not _inteiro(unit) or unit < 1:
        raise Recusa("Valor inválido (informe um valor maior que zero)")
    if unit > MAX_DESPESA_UNIT:
        raise Recusa("Valor acima do máximo permitido (%s)" % reais(MAX_DESPESA_UNIT))
    if chave is not None and not (isinstance(chave, str) and 8 <= len(chave) <= 64 and chave.isascii()
                                  and chave.replace("-", "").replace("_", "").isalnum()):
        raise Recusa("Chave de envio inválida")
    if chave is not None and _chave_parece_cartao(chave):
        raise Recusa("Chave de envio inválida")           # a chave é gravada: nunca um número de cartão disfarçado
    return {"categoria": corpo["categoria"], "descricao": descricao, "quantidade": qtd,
            "valor_unit_centavos": unit, "chave": chave}


def validar_motivo(corpo):
    """Motivo do estorno: 5 a 140 caracteres."""
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    return _texto(corpo.get("motivo"), "o motivo", 5, 140)


def noites(entrada, saida):
    """Noites da estadia (datas AAAA-MM-DD já validadas na reserva)."""
    d = datetime.strptime
    return (d(saida, "%Y-%m-%d") - d(entrada, "%Y-%m-%d")).days


def totais(soma_despesas, n_noites, diaria, com_diaria):
    """Totais da conta. A diária só entra para quem pode ver valores; sem diária cadastrada NÃO há total da estadia."""
    t = {"despesas_centavos": soma_despesas, "noites": n_noites}
    if com_diaria:
        t["diaria_centavos"] = diaria
        if diaria is not None:
            t["diarias_centavos"] = diaria * n_noites
            t["estadia_centavos"] = diaria * n_noites + soma_despesas
    return t


def item(linha, estornos):
    """Linha do banco -> item da API. 'estornos' = {id_do_lancamento: id_do_estorno}."""
    return {"id": linha["id"], "tipo": linha["tipo"], "categoria": linha["categoria"],
            "descricao": linha["descricao"], "quantidade": linha["quantidade"],
            "valor_unit_centavos": linha["valor_unit_centavos"], "total_centavos": linha["total_centavos"],
            "em": linha["em"], "por": linha["usuario_login"], "estorno_de": linha["estorno_de"],
            "estornado": linha["id"] in estornos, "estorno_id": estornos.get(linha["id"]),
            "motivo": linha["motivo"]}


def itens(linhas):
    """Lista de itens, do mais novo para o mais antigo, marcando os lançamentos já estornados."""
    estornos = {l["estorno_de"]: l["id"] for l in linhas if l["estorno_de"]}
    return [item(l, estornos) for l in sorted(linhas, key=lambda x: -x["id"])]


def conferir_saldo(saldo_atual, total_novo):
    """O saldo líquido da reserva não passa de MAX_SALDO_DESPESAS."""
    if saldo_atual + total_novo > MAX_SALDO_DESPESAS:
        raise Recusa("O total das despesas desta reserva passaria do máximo permitido (%s)" % reais(MAX_SALDO_DESPESAS))


# ---------------------------------------------------------------- consultas ao banco

def linhas_da_reserva(con, rid):
    return con.execute("SELECT * FROM despesa_lancamento WHERE reserva_id=? ORDER BY id", (rid,)).fetchall()


def saldo(con, rid):
    """Soma líquida (lançamentos menos estornos) e número de LANÇAMENTOS. Sempre SUM(total_centavos): estorno é negativo."""
    r = con.execute("SELECT COALESCE(SUM(total_centavos),0), COUNT(CASE WHEN tipo='lancamento' THEN 1 END) "
                    "FROM despesa_lancamento WHERE reserva_id=?",
                    (rid,)).fetchone()
    return r[0], r[1]


def conta(con, rid):
    """Estado da conta; sem linha ainda (criada no 1º lançamento) vale o padrão: aberta, pendente, versão 1."""
    r = con.execute("SELECT situacao, quitacao, versao, fechada_em, quitada_em FROM despesa_conta WHERE reserva_id=?",
                    (rid,)).fetchone()
    return dict(r) if r else {"situacao": "aberta", "quitacao": "pendente", "versao": 1, "fechada_em": None,
                              "quitada_em": None}


def reservas_com_saldo(con):
    """[(id, saída, situação da conta)] das reservas ATIVAS com saldo líquido maior que zero. Nunca devolve valores."""
    sql = ("SELECT r.id, r.f, COALESCE(c.situacao,'aberta') FROM reservas r "
           "JOIN despesa_lancamento d ON d.reserva_id = r.id LEFT JOIN despesa_conta c ON c.reserva_id = r.id "
           "WHERE r.status='ativa' GROUP BY r.id HAVING SUM(d.total_centavos) > 0")
    return [tuple(r) for r in con.execute(sql)]


def tem_lancamento(con, rid):
    return con.execute("SELECT 1 FROM despesa_lancamento WHERE reserva_id=? LIMIT 1", (rid,)).fetchone() is not None


def lancamentos_ativos(con, rid):
    """Quantos LANÇAMENTOS da reserva ainda não foram estornados (o que impede, por exemplo, reverter o check-in)."""
    return con.execute("SELECT COUNT(*) FROM despesa_lancamento d WHERE d.reserva_id=? AND d.tipo='lancamento' "
                       "AND NOT EXISTS (SELECT 1 FROM despesa_lancamento e WHERE e.estorno_de = d.id)", (rid,)).fetchone()[0]
