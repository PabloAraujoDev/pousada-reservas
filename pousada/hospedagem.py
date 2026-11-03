"""Hospedagem (etapa 3A do Resumo da conta): regras PURAS de validação, máscaras e estado. Sem Flask e sem permissão.

Dados pessoais deste módulo: documento, data de nascimento, nacionalidade, profissão, procedência, destino e placa. Eles só
existem se informados, nunca vão para logs, histórico nem mensagens de erro, e as rotas só os devolvem completos a quem
tem hospedes.gerir, ficha.imprimir ou veiculo.editar (os outros recebem máscara ou nada).
"""
import re
from .cartao import MSG_CARTAO, contem_numero_cartao
from .despesas import Recusa, texto_validado
from .regras import data_valida, texto_limpo

TIPOS = ("adulto", "crianca")
MAX_HOSPEDES = 50               # igual ao máximo de pessoas da reserva
CAMPOS_PESSOAIS = ("documento", "nascimento", "nacionalidade", "profissao", "procedencia", "destino")
TEXTOS = {"nacionalidade": ("a nacionalidade", 2, 40), "profissao": ("a profissão", 2, 60),
          "procedencia": ("a procedência", 2, 60), "destino": ("o destino", 2, 60)}
_RE_DOC = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-/ ]{1,18}[0-9A-Za-z]$", re.ASCII)
_RE_ANTIGA = re.compile(r"^[A-Z]{3}[0-9]{4}$")
_RE_MERCOSUL = re.compile(r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$")
BLOQUEIA_REVERSAO_COM_DIARIA = True    # decisão documentada: diária informada (> 0) também impede reverter o check-in


def normalizar_placa(v):
    """Placa antiga (ABC1234) ou Mercosul (ABC1D23): maiúsculas, sem hífen nem espaço. None/'' = sem placa. Levanta Recusa."""
    if v is None or v == "":
        return None
    if not isinstance(v, str) or len(v) > 12 or not v.isascii():
        raise Recusa("Placa inválida (use o formato ABC-1234 ou ABC1D23)")
    p = re.sub(r"[\s\-]", "", v).upper()
    if not (_RE_ANTIGA.match(p) or _RE_MERCOSUL.match(p)):
        raise Recusa("Placa inválida (use o formato ABC-1234 ou ABC1D23)")
    return p


def formatar_placa(p):
    """ABC1234 -> ABC-1234 (a Mercosul fica sem hífen)."""
    return p[:3] + "-" + p[3:] if p and p[3:].isdigit() else p


def mascarar_placa(p):
    return p[:3] + "****" if p else None


def _documento(v):
    if v is None or v == "":
        return None
    if not isinstance(v, str) or not texto_limpo(v):
        raise Recusa("Documento inválido")
    v = v.strip()
    if not _RE_DOC.match(v):
        raise Recusa("Documento inválido (3 a 20 letras, números, ponto, hífen ou barra)")
    if contem_numero_cartao(v):
        raise Recusa(MSG_CARTAO)
    return v


def _nascimento(v, hoje):
    if v is None or v == "":
        return None
    d = data_valida(v)
    if not d or d.year < 1900 or v > hoje:
        raise Recusa("Data de nascimento inválida")
    return v


def mascarar_documento(v):
    """Só os 2 últimos caracteres aparecem: '123.456.789-09' -> '***********09'."""
    return None if not v else "*" * max(len(v) - 2, 1) + v[-2:]


def _texto_opcional(v, rotulo, minimo, maximo):
    if v is None or v == "":
        return None
    return texto_validado(v, rotulo, minimo, maximo)


def validar_pessoa(d, hoje, titular=False):
    """Um hóspede do corpo -> dict limpo. 'titular' não tem nome aqui (o nome é o da reserva). Levanta Recusa."""
    if not isinstance(d, dict):
        raise Recusa("Cada hóspede deve ser um objeto JSON", 400)
    tipo = d.get("tipo", "adulto")
    if tipo not in TIPOS:
        raise Recusa("Tipo de hóspede inválido (use adulto ou criança)")
    out = {"tipo": tipo, "nome": None}
    if not titular:
        out["nome"] = texto_validado(d.get("nome"), "o nome do hóspede", 1, 120)
    out["documento"] = _documento(d.get("documento"))
    out["nascimento"] = _nascimento(d.get("nascimento"), hoje)
    for campo, (rotulo, mn, mx) in TEXTOS.items():
        out[campo] = _texto_opcional(d.get(campo), rotulo, mn, mx)
    ident = d.get("id")
    if ident is not None and (not isinstance(ident, int) or isinstance(ident, bool)):
        raise Recusa("Identificador de hóspede inválido")
    out["id"] = ident
    return out


def validar_lista(corpo, n_pessoas, hoje):
    """Corpo do PUT -> (versao, titular, acompanhantes). Titular + acompanhantes não passam de n_pessoas."""
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    versao = corpo.get("versao")
    if not isinstance(versao, int) or isinstance(versao, bool):
        raise Recusa("Informe a versão da reserva", 400)
    lista = corpo.get("acompanhantes", [])
    if not isinstance(lista, list):
        raise Recusa("A lista de acompanhantes deve ser uma lista", 400)
    if 1 + len(lista) > min(n_pessoas, MAX_HOSPEDES):
        raise Recusa("A reserva tem %d pessoa(s): não cabem mais hóspedes. Aumente o número de pessoas em Alterar estadia." % n_pessoas, 422)
    titular = validar_pessoa(corpo.get("titular") or {}, hoje, titular=True)
    acomp = [validar_pessoa(a, hoje) for a in lista]
    ids = [a["id"] for a in acomp if a["id"] is not None]
    if len(ids) != len(set(ids)):
        raise Recusa("Hóspede repetido na lista", 422)
    return versao, titular, acomp


def estado(r):
    """Estado efetivo da hospedagem: conta_aberta, efetuado ou pendente (só informativo; as contagens do dia seguem as datas)."""
    if r["conta_aberta_em"]:
        return "conta_aberta"
    return "efetuado" if r["checkin_em"] else "pendente"


def campos_diferentes(antigo, novo):
    """Nomes (sem valores) dos campos que mudaram entre duas linhas de hóspede; para o log."""
    return [c for c in ("nome", "tipo") + CAMPOS_PESSOAIS if antigo.get(c) != novo.get(c)]
