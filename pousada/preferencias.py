"""Preferências de tela de cada usuário (quais menus aparecem, aba ao abrir, período do mapa).

ATENÇÃO: isto é só ESTÉTICA. Ocultar um menu NUNCA concede acesso e NUNCA remove permissão: quem não pode
continua levando 403 na API, e quem pode continua podendo mesmo com o menu escondido. O servidor nem conhece
as permissões de cada menu; só valida o formato por lista branca (qualquer chave ou valor desconhecido é recusado).
"""
import json

ABAS = ("mapa", "calendario", "folha", "buscar", "governanca", "camareiras", "canceladas", "historico", "usuarios")
MENUS = ABAS + ("importar", "nova")
SEMANAS = (7, 14, 28)
PADRAO = {"menus_ocultos": [], "aba_inicial": None, "mapa_semanas": None,   # None em mapa_semanas = 14 (a tela decide)
          "resumo_recolhido": None}      # faixa "Resumo da conta" recolhida? None = aberta (padrão)


def _menus_ocultos(valor):
    if valor is None:
        return []
    if not isinstance(valor, list) or len(valor) > len(MENUS):
        raise ValueError("Lista de menus ocultos inválida")
    if any(not isinstance(v, str) or v not in MENUS for v in valor):
        raise ValueError("Menu desconhecido na lista de menus ocultos")
    if len(set(valor)) != len(valor):
        raise ValueError("Menu repetido na lista de menus ocultos")
    return [m for m in MENUS if m in valor]          # ordem fixa: o mesmo conjunto sempre gera o mesmo texto


def _aba_inicial(valor):
    if valor is None:
        return None
    if not isinstance(valor, str) or valor not in ABAS:
        raise ValueError("Aba inicial desconhecida")
    return valor


def _mapa_semanas(valor):
    if valor is None:
        return None
    if type(valor) is not int or valor not in SEMANAS:       # bool e decimal (14.0) não valem
        raise ValueError("Período do mapa inválido: use 7, 14 ou 28 dias")
    return valor


def _resumo_recolhido(valor):
    if valor is None:
        return None
    if type(valor) is not bool:          # só verdadeiro/falso (0, 1 e texto não valem)
        raise ValueError("Valor inválido para a faixa do Resumo da conta")
    return valor


_CAMPOS = {"menus_ocultos": _menus_ocultos, "aba_inicial": _aba_inicial, "mapa_semanas": _mapa_semanas,
           "resumo_recolhido": _resumo_recolhido}


def _conferir_conjunto(prefs):
    """Regras que olham o conjunto: a aba inicial não pode estar oculta e alguma aba tem de sobrar."""
    ocultos = prefs["menus_ocultos"]
    if prefs["aba_inicial"] in ocultos:
        raise ValueError("A aba escolhida para abrir não pode estar entre os menus ocultos")
    if all(a in ocultos for a in ABAS):
        raise ValueError("Deixe pelo menos uma aba visível")


def aplicar(atuais, corpo):
    """Preferências novas = as atuais com as chaves enviadas trocadas. Levanta ValueError (português) se algo for inválido."""
    if not isinstance(corpo, dict) or not corpo:
        raise ValueError("Envie as preferências em um objeto JSON")
    if any(k not in _CAMPOS for k in corpo):
        raise ValueError("Campo desconhecido nas preferências")
    novas = dict(atuais)
    for chave, valor in corpo.items():
        novas[chave] = _CAMPOS[chave](valor)           # null ou [] volta ao padrão
    _conferir_conjunto(novas)
    return novas


def ler(texto):
    """Preferências guardadas -> dicionário completo. Texto corrompido ou valor inválido cai no padrão (nunca derruba o login)."""
    try:
        bruto = json.loads(texto)
    except (TypeError, ValueError):
        bruto = None
    prefs = dict(PADRAO)
    for chave, validar in _CAMPOS.items():
        try:
            prefs[chave] = validar(bruto.get(chave)) if isinstance(bruto, dict) else PADRAO[chave]
        except ValueError:
            prefs[chave] = PADRAO[chave]
    try:
        _conferir_conjunto(prefs)
    except ValueError:
        prefs = dict(PADRAO)
    return prefs


def serializar(prefs):
    return json.dumps(prefs, separators=(",", ":"))
