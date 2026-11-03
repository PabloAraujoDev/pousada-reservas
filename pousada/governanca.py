"""Governança: regras PURAS (sem Flask, sem banco) da arrumação das unidades.

Duas camadas separadas:
  A) DERIVADA das reservas ativas (hospedada, saída, chegada...): recalculada a cada consulta, nunca gravada.
  B) REGISTRADA pela equipe (suja, em arrumação, pronta, manutenção, observação): tabela governanca_unidade.

Os valores que o clube ainda vai decidir (dias de enxoval, janela de desfazer, horas) vêm de config.py e
entram aqui como o dicionário `par` (veja parametros()). Nada aqui lê o relógio: quem chama passa `agora`.
"""
from datetime import date, datetime

from .regras import MSG_CARTAO, OCUPADAS, contem_numero_cartao, tem_texto_visivel, texto_limpo

FORMATO = "%Y-%m-%d %H:%M:%S"
ACOES = ("iniciar", "pronta", "suja", "observacao", "manutencao_abrir", "manutencao_fechar")
MAX_TEXTO = 140

# Quem pode cada ação de situação. É regra de PERFIL (a capacidade governanca.atualizar é só a porta de entrada).
# A camareira só "suja" desfazendo o próprio "pronto" ou "iniciar" dentro da janela (veja _camareira_pode_desfazer).
PAPEIS_ACAO = {
    "iniciar": {"camareira", "atendente", "admin"},
    "pronta": {"camareira", "atendente", "admin", "recepcao"},
    "suja": {"recepcao", "atendente", "admin"},
}
GRUPOS = (("Térreo", "1"), ("2º andar", "2"), ("3º andar", "3"), ("Chalés", "C"))


class Recusa(Exception):
    """Ação não permitida ou inválida: status HTTP (403/422/409) e mensagem em português."""

    def __init__(self, status, mensagem, **extra):
        super().__init__(mensagem)
        self.status, self.mensagem, self.extra = status, mensagem, extra


def parametros(conf):
    """Parâmetros de governança a partir de app.config (ou de qualquer dicionário com as mesmas chaves)."""
    return {"dias_troca": conf["GOV_DIAS_TROCA_ENXOVAL"], "dias_vaga": conf["GOV_DIAS_VAGA"],
            "janela_min": conf["GOV_JANELA_DESFAZER_MIN"], "hora_atraso": conf["GOV_HORA_TROCA_ATRASADA"],
            "hora_saida": conf["GOV_HORA_SAIDA"], "hora_entrada": conf["GOV_HORA_ENTRADA"]}


def andar_de(unidade):
    """Nome do grupo da unidade na tela: Térreo, 2º andar, 3º andar ou Chalés."""
    chave = unidade[0]
    return next(nome for nome, c in GRUPOS if c == chave)


def texto_curto(v, rotulo):
    """Observação/motivo: texto limpo, quebras de linha viram espaço, até 140 caracteres. Levanta Recusa 422."""
    if not isinstance(v, str):
        raise Recusa(422, "%s deve ser um texto" % rotulo)
    if not texto_limpo(v):
        raise Recusa(422, "%s contém caracteres não permitidos (controles invisíveis ou de inversão do texto)" % rotulo)
    v = " ".join(v.split())
    if v and not tem_texto_visivel(v):
        v = ""                               # só caracteres invisíveis = vazio
    if len(v) > MAX_TEXTO:                   # tamanho primeiro: o detector de cartão só olha textos curtos
        raise Recusa(422, "%s grande demais (máximo %d caracteres)" % (rotulo, MAX_TEXTO))
    if contem_numero_cartao(v):
        raise Recusa(422, MSG_CARTAO)
    return v


# ---------------------------------------------------------------- camada A: derivada das reservas

def derivar(reservas, dia):
    """Reservas ativas de UMA unidade -> o que acontece nela no `dia` (AAAA-MM-DD).

    estadia: hóspede no meio da estadia (entrou antes do dia e sai depois). No dia da chegada a unidade ainda
    não está "hospedada" (aparece como pronta com "In 14:00"), senão nunca mostraria "pode entrar".
    """
    saida = next((r for r in reservas if r["f"] == dia), None)
    chegada = next((r for r in reservas if r["i"] == dia), None)
    estadia = next((r for r in reservas if r["i"] < dia < r["f"]), None)
    return {"estadia": estadia, "saida": saida, "chegada": chegada, "troca": bool(saida and chegada)}


def _limite(data, hora):
    return "%s %s:00" % (data, hora)


def _suja_automatica(reg, ultima_saida, agora, par):
    """Existe saída já ocorrida (L <= hoje), passou das 12:00 dela, a última arrumação é anterior e ninguém confirmou."""
    if not ultima_saida:
        return False
    corte = _limite(ultima_saida, par["hora_saida"])
    return (agora.strftime(FORMATO) >= corte and (reg["pronto_em"] or "") < corte
            and reg["saida_confirmada"] != ultima_saida)


def situacao_efetiva(reg, der, ultima_saida, agora, par, unidade):
    """(situacao, origem) por prioridade: interditada, manutenção, em arrumação, suja, aguardando saída, hospedada, pronta.

    origem só vale para suja: 'automatica' (regra das 12:00) ou 'registrada'."""
    if unidade in OCUPADAS:
        return "interditada", None
    if reg["manutencao"]:
        return "manutencao", None
    if reg["situacao"] == "em_arrumacao":
        return "em_arrumacao", None
    if reg["situacao"] == "suja" and not der["estadia"]:
        return "suja", "registrada"
    if _suja_automatica(reg, ultima_saida, agora, par):
        return "suja", "automatica"
    if (der["saida"] and reg["saida_confirmada"] != der["saida"]["f"]
            and agora.strftime(FORMATO) < _limite(der["saida"]["f"], par["hora_saida"])):
        return "aguardando_saida", None
    if der["estadia"]:
        return "hospedada", None
    return "pronta", None


def dias_sem_arrumacao(reg, der, hoje):
    """Dias de calendário desde a última arrumação (na estadia, desde a entrada se for mais recente). 0 = hoje."""
    if not reg["pronto_em"]:
        return 0
    base = reg["pronto_em"][:10]
    if der["estadia"]:
        base = max(base, der["estadia"]["i"])
    return max(0, (date.fromisoformat(hoje) - date.fromisoformat(base)).days)


def alertas_de_tempo(situacao, der, dias, par):
    """(alerta_enxoval, pronta_ha_dias): enxoval para quem está hospedado; poeira para unidade vaga e pronta."""
    enxoval = situacao == "hospedada" and dias >= par["dias_troca"]
    vaga = situacao == "pronta" and not der["chegada"] and not der["estadia"] and dias >= par["dias_vaga"]
    return enxoval, (dias if vaga else None)


def atrasada(situacao, der, agora, par, eh_hoje):
    """Chegada hoje e a unidade ainda não está pronta depois da hora limite (só para o dia de hoje)."""
    return bool(eh_hoje and der["chegada"] and situacao in ("suja", "em_arrumacao", "aguardando_saida")
                and agora.strftime("%H:%M") >= par["hora_atraso"])


# ---------------------------------------------------------------- camada B: transições

def _camareira_pode_desfazer(reg, quem, agora, par):
    if reg["situacao"] not in ("pronta", "em_arrumacao") or reg["situacao_por"] != quem["id"] or not reg["situacao_em"]:
        return False
    feito = datetime.strptime(reg["situacao_em"], FORMATO)
    return 0 <= (agora - feito).total_seconds() <= par["janela_min"] * 60


def _checar_perfil(acao, estado, quem, agora, par):
    if acao in ("manutencao_abrir", "manutencao_fechar"):
        if "governanca.manutencao" not in quem["caps"]:
            raise Recusa(403, "Seu perfil não pode abrir ou fechar manutenção")
        return
    if "governanca.atualizar" not in quem["caps"]:
        raise Recusa(403, "Seu perfil não tem permissão para fazer isso")
    if acao == "observacao":
        return
    if quem["papel"] in PAPEIS_ACAO[acao]:
        return
    if acao == "suja" and quem["papel"] == "camareira" and _camareira_pode_desfazer(estado["reg"], quem, agora, par):
        return
    raise Recusa(403, "Seu perfil não pode fazer isso (a camareira só desfaz a própria marcação por %d minutos)" % par["janela_min"]
                 if acao == "suja" else "Seu perfil não pode fazer isso")


def _ja_estava(acao, estado, dados):
    """O resultado desejado já vale? (então a ação é repetida sem efeito: 200 'ja_estava')"""
    reg, sit = estado["reg"], estado["situacao"]
    if acao == "iniciar":
        return reg["situacao"] == "em_arrumacao"
    if acao == "pronta":
        return reg["situacao"] == "pronta" and not (sit == "suja" and estado["origem"] == "automatica")
    if acao == "suja":
        return reg["situacao"] == "suja"
    if acao == "observacao":
        return reg["obs"] == dados["obs"]
    if acao == "manutencao_abrir":
        return bool(reg["manutencao"])
    return not reg["manutencao"]


def _mudancas_situacao(acao, estado, dados, agora):
    """Campos novos da unidade para iniciar/pronta/suja."""
    reg, em = estado["reg"], agora.strftime(FORMATO)
    novo = {"iniciar": "em_arrumacao", "pronta": "pronta", "suja": "suja"}[acao]
    m = {"situacao": novo, "situacao_em": em, "situacao_por": dados["id_usuario"]}
    if acao == "pronta":
        m.update(pronto_em=em, iniciada_em=None)
    elif acao == "iniciar":
        m["iniciada_em"] = em
    if dados["confirmou_saida"] and estado["saida_hoje"]:
        m["saida_confirmada"] = estado["saida_hoje"]
    return m


def _exigir_saida_confirmada(acao, estado, dados):
    if acao in ("iniciar", "suja") and estado["situacao"] == "aguardando_saida" and not dados["confirmou_saida"]:
        raise Recusa(422, "O hóspede já saiu? Confirme a saída para continuar.", precisa_confirmar_saida=True)


def avaliar(acao, estado, quem, agora, par, dados):
    """Decide a ação sobre UMA unidade. Retorna ("ja_estava", None) ou ("ok", campos_a_gravar). Levanta Recusa.

    estado: reg (linha da unidade), situacao, origem, saida_hoje (data de hoje se há saída hoje, senão None).
    quem: id, papel, caps. dados: id_usuario, confirmou_saida, obs, motivo (já validados)."""
    _checar_perfil(acao, estado, quem, agora, par)
    if _ja_estava(acao, estado, dados):
        return "ja_estava", None
    if acao in ("iniciar", "pronta", "suja") and estado["situacao"] == "manutencao":
        raise Recusa(422, "Unidade em manutenção")
    if acao in ("iniciar", "suja"):
        _exigir_saida_confirmada(acao, estado, dados)
    if acao == "observacao":
        return "ok", {"obs": dados["obs"]}
    if acao == "manutencao_abrir":
        return "ok", {"manutencao": 1, "manutencao_motivo": dados["motivo"]}
    if acao == "manutencao_fechar":
        return "ok", {"manutencao": 0, "manutencao_motivo": ""}
    return "ok", _mudancas_situacao(acao, estado, dados, agora)


def acoes_possiveis(estado, quem, agora, par):
    """Lista `pode` de uma unidade: as ações que o usuário poderia fazer agora (só conveniência de tela)."""
    dados = {"id_usuario": quem["id"], "confirmou_saida": True, "obs": "", "motivo": "x"}
    pode = []
    for acao in ("iniciar", "pronta", "suja", "manutencao_abrir", "manutencao_fechar"):
        try:
            if avaliar(acao, estado, quem, agora, par, dados)[0] == "ok":
                pode.append(acao)
        except Recusa:
            pass
    return pode
