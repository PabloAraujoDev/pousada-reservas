"""Quem pode o quê. Cada papel recebe uma lista de capacidades; cada rota exige uma (ou mais de uma, alternativas)."""
from functools import wraps

from flask import g

from .erros import ErroApi

TODAS = frozenset({
    "reservas.ver",                 # lista completa de reservas
    "reservas.ver_resumo",          # lista reduzida (sem nome, extras, observações, pagamento)
    "reservas.criar", "reservas.editar",
    "reservas.editar_pagamento",    # só os campos p (pagamento) e o (observações)
    "reservas.cancelar", "reservas.reativar", "reservas.ver_canceladas",
    "reservas.excluir_definitivo",
    "folha.ver",                    # folha da semana e CSV do período
    "export.completo",              # CSV com todas as reservas
    "camareiras.ver",
    "importar", "pedidos.ver",
    "usuarios", "backup",
    "historico.completo", "historico.resumo", "historico.reserva",
    "valores.ver",                  # ver o valor da diária (só no detalhe da reserva e no CSV completo)
    "valores.editar",               # informar/alterar o valor da diária
    "governanca.ver",               # tela de arrumação das unidades (sem dados do hóspede para quem não tem reservas.ver)
    "governanca.atualizar",         # iniciar, pronto, suja, observação (o que cada perfil pode é refinado em governanca.py)
    "governanca.manutencao",        # abrir e fechar manutenção
    "despesas.ver",                 # conta de consumo da reserva (valores!) e a contagem de contas abertas
    "despesas.lancar",              # lançar consumo na conta
    "despesas.estornar",            # estornar lançamento (nova linha negativa, com motivo)
    "despesas.conta",               # fechar e quitar a conta (reservado; rotas na etapa seguinte)
    "notas.escrever",               # anotar/corrigir/ocultar nota da RESERVA (ler é reservas.ver)
    "notas.escrever_unidade",       # idem para a nota do APARTAMENTO (vale para reservas futuras)
    "notas.ver_ocultas",            # ver as notas ocultas e os textos anteriores das corrigidas
    "hospedes.gerir",               # lista de hóspedes da hospedagem (titular + acompanhantes) e seus dados pessoais; ver sem máscara
    "checkin.registrar",            # registrar o check-in efetivo
    "checkin.reverter",             # reverter o check-in (só sem lançamentos)
    "conta.liberar",                # liberar o apartamento deixando a conta aberta (e desfazer)
    "ficha.imprimir",               # ficha de check-in FNRH (dados pessoais completos dos hóspedes)
    "pagamentos.ver",               # ver os pagamentos recebidos (valores!) e o saldo da conta
    "pagamentos.receber",           # receber pagamento (dinheiro, Pix, cartão), parcial ou total
    "pagamentos.estornar",          # estornar um pagamento (linha negativa, com motivo)
    "despesas.transferir",          # transferir despesas (e a diária) para outra hospedagem; zerar a diária informada
    "conta.reabrir",                # reabrir uma conta fechada (com motivo)
    "veiculo.editar",               # placa do veículo (dado pessoal); ver sem máscara
})

PERMISSOES = {
    "admin": TODAS,
    "atendente": frozenset({
        "reservas.ver", "reservas.criar", "reservas.editar", "reservas.cancelar", "reservas.reativar",
        "reservas.ver_canceladas", "folha.ver", "camareiras.ver", "historico.reserva",
        "valores.ver", "valores.editar",
        "governanca.ver", "governanca.atualizar", "governanca.manutencao",     # na v1 o atendente faz o papel de governanta
        "despesas.ver", "despesas.lancar", "despesas.estornar", "despesas.conta",
        "notas.escrever", "notas.escrever_unidade",
        "hospedes.gerir", "checkin.registrar", "checkin.reverter", "conta.liberar", "ficha.imprimir", "veiculo.editar",
        "pagamentos.ver", "pagamentos.receber", "pagamentos.estornar", "despesas.transferir", "conta.reabrir",
    }),
    "recepcao": frozenset({"reservas.ver", "reservas.editar_pagamento", "folha.ver", "valores.ver",
                           "governanca.ver", "governanca.atualizar",
                           "despesas.ver", "despesas.lancar", "despesas.conta",
                           "notas.escrever",     # estornar: decisão do clube pendente
                           "hospedes.gerir", "checkin.registrar", "checkin.reverter", "conta.liberar", "ficha.imprimir", "veiculo.editar",
                           "pagamentos.ver", "pagamentos.receber"}),   # reverter check-in e liberar (ambos com motivo obrigatório): decisão do usuário; estornar pagamento, transferir e reabrir conta: decisão do clube pendente
    "camareira": frozenset({"camareiras.ver", "reservas.ver_resumo", "governanca.ver", "governanca.atualizar"}),
    "diretoria": frozenset({"reservas.ver", "folha.ver", "export.completo", "historico.resumo", "valores.ver",
                            "governanca.ver", "despesas.ver", "pagamentos.ver"}),
    "consulta": frozenset({"reservas.ver", "folha.ver", "camareiras.ver", "governanca.ver"}),     # só visualizar e imprimir
}


def capacidades(papel):
    return PERMISSOES.get(papel, frozenset())


def pode(capacidade):
    """O usuário do pedido atual tem esta capacidade?"""
    u = g.get("usuario")
    return u is not None and capacidade in capacidades(u["papel"])


def exigir(*alternativas):
    """Levanta 403 se o usuário atual não tiver NENHUMA das capacidades (para checagens dentro da rota)."""
    if not any(pode(c) for c in alternativas):
        raise ErroApi("Seu perfil não tem permissão para fazer isso", 403)


def exige(*alternativas):
    """Decorator: a rota só roda se o papel tiver PELO MENOS UMA das capacidades listadas."""
    for cap in alternativas:
        assert cap in TODAS, "capacidade desconhecida: " + cap

    def decorador(f):
        @wraps(f)
        def interna(*args, **kw):
            exigir(*alternativas)
            return f(*args, **kw)
        return interna
    return decorador
