"""Regras de negócio: unidades, validação de datas, conflitos, café e hóspedes."""
import re
from datetime import datetime

from .cartao import MSG_CARTAO, contem_numero_cartao  # noqa: F401  (reexportados: regras é o ponto único)

UNIDADES = (["101", "102", "103", "104"]
            + [str(x) for x in range(201, 209)]
            + [str(x) for x in range(301, 309)]
            + ["Chalé " + c for c in "ABCDE"])
OCUPADAS = {"104"}  # unidades que não aceitam reserva
PAGAMENTOS = ("pago", "parcial", "pousada", "gratis", "pendente")


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def data_valida(texto):
    """Devolve date se o texto AAAA-MM-DD for uma data real, senão None."""
    if not isinstance(texto, str) or len(texto) != 10 or not texto.isascii():   # sem dígitos de outros alfabetos
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


# Limites aceitos pelo servidor (o formulário também usa estes valores)
MAX_NOME, MAX_GRUPO, MAX_TEXTO = 120, 120, 1000     # nome/grupo; extras e observações
ANO_MIN, ANO_MAX = 2020, 2100
MAX_NOITES = 365
MAX_PESSOAS = 50

# Caracteres de controle (NUL etc., menos quebra de linha e tab), "surrogates" soltos e os que invertem o
# sentido do texto (U+202A-202E, U+2066-2069: servem para disfarçar nomes) nunca entram no banco.
_RE_PROIBIDOS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff\u202a-\u202e\u2066-\u2069]")


def texto_limpo(v):
    """True se v é texto sem caracteres proibidos (veja _RE_PROIBIDOS)."""
    return isinstance(v, str) and not _RE_PROIBIDOS.search(v)


_EM_BRANCO = "⠀ㅤᅟᅠ᠎"      # parecem espaço mas são "letras" (braile em branco, preenchimentos de hangul)


def tem_texto_visivel(v):
    """True se v tem ao menos um caractere que aparece na tela (não só espaços, zero-width ou braile em branco)."""
    return any(c.isprintable() and not c.isspace() and c not in _EM_BRANCO for c in v)


def _texto(d, campo, maximo, rotulo, cartao=True):
    """Lê um campo de texto opcional. Retorna (texto, None) ou (None, erro). cartao=False não confere número de cartão."""
    v = d.get(campo)
    if v is None:
        return "", None
    if not texto_limpo(v):
        return None, "%s contém caracteres não permitidos (controles invisíveis ou de inversão do texto)" % rotulo
    v = v.strip()
    if v and not tem_texto_visivel(v):
        v = ""                               # só caracteres invisíveis = vazio (o nome vazio já é recusado)
    if len(v) > maximo:
        return None, "%s grande demais (máximo %d caracteres)" % (rotulo, maximo)
    if cartao and contem_numero_cartao(v):
        return None, MSG_CARTAO          # nunca repete o texto recebido
    return v, None


def status_do_erro(erro):
    """Status HTTP de uma mensagem de validar_reserva: 422 para número de cartão, 400 para o resto."""
    return 422 if erro == MSG_CARTAO else 400


def _pessoas_validas(n):
    """n precisa ser inteiro de verdade de 1 a 50 (bool e float são recusados)."""
    return isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= MAX_PESSOAS


TIPOS_HOSPEDE = ("socio", "convidado")
MAX_DIARIA_CENTAVOS = 100000000      # R$ 1.000.000,00

# Despesas (conta do hóspede): limites que o banco também confere (migração 012)
CATEGORIAS_DESPESA = ("restaurante", "bar", "lavanderia", "outros")
MAX_DESPESA_UNIT = 1000000           # R$ 10.000,00 por unidade
MAX_DESPESA_QTD = 99
MAX_LANCAMENTOS = 200                # linhas (lançamentos + estornos) por reserva
MAX_SALDO_DESPESAS = MAX_DIARIA_CENTAVOS


def validar_unidade(a):
    """Unidade existente e que aceita reservas. Retorna (unidade, None) ou (None, erro)."""
    a = a.strip() if isinstance(a, str) else ""
    if a not in UNIDADES:
        return None, "Unidade inexistente"
    if a in OCUPADAS:
        return None, "A unidade %s está ocupada e não aceita reservas" % a
    return a, None


def validar_periodo(entrada, saida):
    """Datas reais (ASCII), anos aceitos, saída depois da entrada e estadia curta o bastante.

    Retorna ((i, f) em AAAA-MM-DD, None) ou (None, erro)."""
    i, f = data_valida(entrada), data_valida(saida)
    if not i:
        return None, "Data de entrada inválida"
    if not f:
        return None, "Data de saída inválida"
    if not (ANO_MIN <= i.year <= ANO_MAX and ANO_MIN <= f.year <= ANO_MAX):
        return None, "O ano das datas deve estar entre %d e %d" % (ANO_MIN, ANO_MAX)
    if f <= i:
        return None, "A saída deve ser depois da entrada"
    if (f - i).days > MAX_NOITES:
        return None, "Estadia longa demais (máximo %d noites)" % MAX_NOITES
    return (i.isoformat(), f.isoformat()), None


def validar_destino(a, i, f):
    """Valida o que o movimento no mapa pode mudar (unidade e datas). Retorna ({a,i,f}, None) ou (None, erro)."""
    a, erro = validar_unidade(a)
    if erro:
        return None, erro
    periodo, erro = validar_periodo(i, f)
    if erro:
        return None, erro
    return {"a": a, "i": periodo[0], "f": periodo[1]}, None


def validar_tipo(v):
    """Sócio do clube ou convidado; vazio = não informado. Retorna (valor ou None, erro)."""
    if v is None or v == "":
        return None, None
    if v not in TIPOS_HOSPEDE:     # também recusa números, listas e booleanos
        return None, "Tipo de hóspede inválido (use sócio ou convidado)"
    return v, None


def validar_diaria(v):
    """Valor da diária em centavos: inteiro de verdade de 0 a MAX_DIARIA_CENTAVOS, ou None (não informado)."""
    if v is None:
        return None, None
    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= MAX_DIARIA_CENTAVOS:
        return None, "Valor da diária inválido"
    return v, None


def _validar_tipo_e_diaria(d, dados):
    """Acrescenta a dados as chaves 'tipo' e 'diaria_centavos' SÓ se vieram em d (na edição, ausente = mantém o atual)."""
    for chave, validar in (("tipo", validar_tipo), ("diaria_centavos", validar_diaria)):
        if chave in d:
            dados[chave], erro = validar(d[chave])
            if erro:
                return erro
    return None


def validar_reserva(d, texto_antigo=()):
    """Valida e normaliza os dados. Retorna (dados, None) ou (None, mensagem de erro).

    texto_antigo: campos que o usuário não pode alterar e vêm do que já está gravado (não conferem cartão aqui;
    a varredura de dados antigos cuida deles)."""
    if not isinstance(d, dict):
        return None, "Dados inválidos"
    a, erro = validar_unidade(d.get("a", ""))
    if erro:
        return None, erro
    nome, erro = _texto(d, "nome", MAX_NOME, "Nome", "nome" not in texto_antigo)
    if erro:
        return None, erro
    if not nome:
        return None, "Informe o nome do hóspede"
    n = d.get("n", 1)
    if not _pessoas_validas(n):
        return None, "Número de pessoas inválido (use um número inteiro de 1 a %d)" % MAX_PESSOAS
    periodo, erro = validar_periodo(d.get("i"), d.get("f"))
    if erro:
        return None, erro
    p = d.get("p", "pendente")
    p = "pendente" if p is None else p
    p = p.strip() or "pendente" if isinstance(p, str) else p
    if p not in PAGAMENTOS:
        return None, "Forma de pagamento inválida"
    extras, erro = _texto(d, "extras", MAX_TEXTO, "Extras", "extras" not in texto_antigo)
    if erro:
        return None, erro
    o, erro = _texto(d, "o", MAX_TEXTO, "Observações")
    if erro:
        return None, erro
    # grupo: None = "não informado" (na edição, mantém o que já existe)
    grupo = None
    if d.get("grupo") is not None:
        grupo, erro = _texto(d, "grupo", MAX_GRUPO, "Grupo", "grupo" not in texto_antigo)
        if erro:
            return None, erro
    dados = {"a": a, "nome": nome, "extras": extras, "n": n, "i": periodo[0], "f": periodo[1],
             "p": p, "o": o, "grupo": grupo}
    erro = _validar_tipo_e_diaria(d, dados)
    return (None, erro) if erro else (dados, None)


def existe_conflito(con, a, i, f, ignorar_id=None):
    """Há reserva ATIVA (cancelada não conta) na mesma unidade que se sobrepõe a [i, f)? Sair e entrar no mesmo dia é permitido."""
    sql = "SELECT id FROM reservas WHERE status = 'ativa' AND a = ? AND i < ? AND f > ?"
    args = [a, f, i]
    if ignorar_id is not None:
        sql += " AND id <> ?"
        args.append(ignorar_id)
    return con.execute(sql + " LIMIT 1", args).fetchone() is not None


def cafe_do_dia(con, dia):
    """Café da manhã: soma de n com i < dia <= f."""
    return con.execute("SELECT COALESCE(SUM(n),0) FROM reservas WHERE status = 'ativa' AND i < ? AND ? <= f", (dia, dia)).fetchone()[0]


def hospedes_na_noite(con, dia):
    """Hóspedes dormindo na noite do dia: i <= dia < f."""
    return con.execute("SELECT COALESCE(SUM(n),0) FROM reservas WHERE status = 'ativa' AND i <= ? AND ? < f", (dia, dia)).fetchone()[0]
