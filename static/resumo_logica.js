"use strict";
/* Resumo da conta: lógica pura (sem DOM nem rede), testada em node (tests/js/resumo_logica.js).
 * Valores em centavos inteiros; o formatador é o de despesas_logica.js (dsFormatarReais). O servidor já decide quem recebe
 * a diária e as despesas: aqui só se monta o que chegou (o que não veio não existe na tela). */
if (typeof module !== "undefined" && typeof dsFormatarReais === "undefined") Object.assign(globalThis, require("./despesas_logica.js"));   // (só no teste em node)

var RC_PAGAMENTO = {pago: "Pago", parcial: "Parcial", pousada: "Paga na pousada", gratis: "Grátis", pendente: "Pendente"};
var RC_FORMA = {dinheiro: "Dinheiro", pix: "Pix", cartao: "Cartão"};
var RC_TIPO = {socio: "Sócio do clube", convidado: "Convidado"};

function rcNoites(i, f){
  var a = i.split("-"), b = f.split("-");
  return Math.round((Date.UTC(+b[0], +b[1] - 1, +b[2]) - Date.UTC(+a[0], +a[1] - 1, +a[2])) / 86400000);
}
function rcDataBR(s){ var p = String(s || "").split("-"); return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(s || ""); }
function rcPlural(n, um, varios){ return n + " " + (n === 1 ? um : varios); }
/* Situação no dia: texto SEMPRE junto da bolinha (nunca só cor). Chave de classe + rótulo. */
function rcSituacao(r, hoje){
  if (r.status && r.status !== "ativa") return {chave: "cancelada", rotulo: "Cancelada"};
  if (r.f < hoje) return {chave: "encerrada", rotulo: "Encerrada"};
  if (r.i > hoje) return {chave: "futura", rotulo: "Reserva futura"};
  if (r.i === hoje) return {chave: "chegando", rotulo: "Chegando hoje (14h)"};
  if (r.f === hoje) return {chave: "saindo", rotulo: "Saindo hoje (12h)"};
  return {chave: "hospedado", rotulo: "Hospedado"};
}
function rcPeriodo(r){
  return "In " + rcDataBR(r.i) + " (14h) | Out " + rcDataBR(r.f) + " (12h) | " + rcPlural(rcNoites(r.i, r.f), "noite", "noites");
}
function rcTitulo(r){ return "Apartamento " + r.a + " · Reserva #" + r.id; }
/* Linha do tipo de hóspede: "Sócio do clube · Grupo Turma Azul". */
function rcTipoGrupo(r){
  var t = [];
  t.push(RC_TIPO[r.tipo] || "Tipo não informado");
  if (r.grupo) t.push("Grupo " + r.grupo);
  return t.join(" · ");
}
/* Categoria do apartamento: o sistema não guarda categoria, então vale o andar (Térreo, 2º andar, 3º andar, Chalés). */
function rcAndar(a){
  var c = String(a || "").charAt(0);
  return c === "1" ? "Térreo" : c === "2" ? "2º andar" : c === "3" ? "3º andar" : "Chalés";
}
function rcTituloCartao(r){ return "Apartamento " + r.a + " - " + rcAndar(r.a); }
var RC_ESTADO = {pendente: "Check-in pendente", efetuado: "Check-in efetuado", conta_aberta: "Apartamento liberado, conta aberta"};
function rcEstado(r){ return RC_ESTADO[r.estado_hospedagem] || RC_ESTADO.pendente; }
/* Botões da barra do cartão, na ordem da referência: Alterar estadia, Hóspedes, Transferir, Liberar (ou Desfazer a liberação),
 * Ficha FNRH, Registrar/Reverter check-in; depois Cancelar, Imprimir resumo, Histórico, Despesas.
 * p = {editar, editarPag, cancelar, reativar, historico, despesas, liberar, ficha, checkin, reverter}; estado = pendente|efetuado|conta_aberta.
 * Só entra o que o perfil pode: o servidor confere de novo. */
function rcBotoes(p, cancelada, estado){
  var b = [];
  if (cancelada){
    if (p.reativar) b.push("reativar");
  } else {
    if (p.editar || p.editarPag) b.push("editar");
    b.push("hospedes");
    if (p.editar) b.push("trocar");
    if (p.liberar) b.push(estado === "conta_aberta" ? "reabrir" : "liberar");
    if (p.ficha) b.push("ficha");
    if (estado === "pendente" && p.checkin) b.push("checkin");
    if (estado === "efetuado" && p.reverter) b.push("reverter");
    if (p.cancelar) b.push("cancelar");
  }
  b.push("imprimir");
  if (p.historico) b.push("historico");
  if (p.despesas && !cancelada) b.push("despesas");
  return b;
}
var RC_ROTULO = {editar: "Alterar estadia", hospedes: "Manutenção de hóspedes", trocar: "Transferência de apartamento",
  liberar: "Liberar o apartamento e deixar a conta aberta", reabrir: "Desfazer a liberação do apartamento",
  ficha: "Ficha de check-in (FNRH)", checkin: "Registrar check-in", reverter: "Reverter check-in", cancelar: "Cancelar reserva",
  reativar: "Reativar reserva", imprimir: "Imprimir resumo da conta", historico: "Histórico", despesas: "Despesas", placa: "Placa do veículo",
  extrato: "Imprimir o extrato da conta (só o que estiver selecionado)", receber: "Receber pagamento", estornar: "Estornar o que estiver selecionado",
  transferir: "Transferir o selecionado para outro apartamento", info: "Lançamentos da hospedagem", fechar: "Fechar a conta", reabrir_conta: "Reabrir a conta"};
var RC_CURTO = {editar: "Alterar", hospedes: "Hóspedes", trocar: "Transferir", liberar: "Liberar", reabrir: "Reocupar", ficha: "Ficha FNRH",
  checkin: "Check-in", reverter: "Reverter", cancelar: "Cancelar", reativar: "Reativar", imprimir: "Resumo", historico: "Histórico",
  despesas: "Despesas", placa: "Placa",
  extrato: "Extrato", receber: "Receber", estornar: "Estornar", transferir: "Transferir", info: "Lançamentos", fechar: "Fechar conta", reabrir_conta: "Reabrir conta"};
function rcAriaBotao(id, r){   // rótulo completo para leitor de tela
  if (id === "estornar" || id === "transferir" || id === "receber" || id === "extrato" || id === "info") return RC_ROTULO[id] + " (apartamento " + r.a + ")";
  if (id === "trocar") return "Transferir o apartamento " + r.a + " da reserva de " + r.nome;
  return RC_ROTULO[id] + " (apartamento " + r.a + ", hóspede " + r.nome + ")";
}
/* Subtotais e total. p = {valores, despesas}; totais = "totais" de GET /despesas (ou null). Nada aparece sem permissão;
 * o total da estadia só existe com os DOIS acessos e com a diária informada (nunca um total parcial). */
function rcSubtotais(det, totais, p){
  var n = rcNoites(det.i, det.f), linhas = [], total = null, ok = !!totais;
  if (p.valores){
    var d = det.diaria_centavos;
    linhas.push({id: "diarias", rotulo: "Diárias", texto: d == null ? "Diária não informada" : dsFormatarReais(d * n) + " (" + n + " x " + dsFormatarReais(d) + ")"});
  }
  if (p.despesas && ok) linhas.push({id: "despesas", rotulo: "Lançamentos", texto: dsFormatarReais(totais.despesas_centavos)});
  if (p.valores && p.despesas && ok && det.diaria_centavos != null){
    total = typeof totais.estadia_centavos === "number" ? totais.estadia_centavos : det.diaria_centavos * n + totais.despesas_centavos;
  }
  return {linhas: linhas, total: total === null ? null : dsFormatarReais(total)};
}
/* Azulejos da seção do hóspede, na ordem da referência: Diária, Evento, Consumo, Crédito. Cada um tem caixa de seleção (só seleção visual
 * e total selecionado nesta etapa; lançar/transferir/estornar ficam para a etapa seguinte). Evento e Crédito ainda não existem:
 * aparecem desabilitados com "Em breve". Valores só para quem recebeu (valores.ver / despesas.ver). */
function rcAzulejos(det, totais, p){
  var a = [], n = rcNoites(det.i, det.f);
  if (p.valores) a.push({id: "diaria", rotulo: "Diária", valor: det.diaria_centavos == null ? "Não informada" : dsFormatarReais(det.diaria_centavos * n),
    nota: det.diaria_centavos == null ? "" : rcPlural(n, "noite", "noites") + " x " + dsFormatarReais(det.diaria_centavos), selecionavel: det.diaria_centavos > 0});
  if (p.valores || p.despesas) a.push({id: "evento", rotulo: "Evento", valor: "Em breve", nota: "Ainda não existe na conta", desabilitado: true});
  if (p.despesas && totais) a.push({id: "consumo", rotulo: "Consumo", valor: dsFormatarReais(totais.despesas_centavos), nota: "Lançamentos da conta", selecionavel: true});
  if (!a.length) return a;
  if (totais && typeof totais.pagamentos_centavos === "number"){      // pagamentos.ver: o Crédito é a soma dos pagamentos recebidos (líquidos de estorno)
    a.push({id: "credito", rotulo: "Crédito", valor: dsFormatarReais(totais.pagamentos_centavos), nota: "Pagamentos recebidos", selecionavel: !!p.temPagamentos});
    a.push({id: "saldo", rotulo: "Saldo a pagar", valor: dsFormatarReais(totais.saldo_centavos), nota: p.contaFechada ? "Conta fechada" : "Total menos pagamentos", semCaixa: true});
  } else a.push({id: "credito", rotulo: "Crédito", valor: "Em breve", nota: "Pagamentos com valor virão depois", desabilitado: true});
  return a;
}
/* Itens selecionáveis da conta, por tipo (diaria, consumo). itensDesp = "itens" de GET /despesas (ou null). */
function rcDescPagamento(g){
  var t = (RC_FORMA[g.forma] || g.forma) + (g.forma === "cartao" ? " " + g.bandeira + " " + (g.modalidade === "credito" ? "crédito" : "débito") : "");
  return "Pagamento " + t + (g.parcelas > 1 ? " em " + g.parcelas + "x" : "");
}
function rcItensConta(det, itensDesp, p, pagamentos){
  var n = rcNoites(det.i, det.f), lista = [];
  if (p.valores && det.diaria_centavos > 0) lista.push({id: "diaria", tipo: "diaria", descricao: "Diárias: " + rcPlural(n, "noite", "noites") + " x " + dsFormatarReais(det.diaria_centavos), centavos: det.diaria_centavos * n});
  if (p.despesas && itensDesp){
    itensDesp.filter(function(i){ return i.tipo === "lancamento" && !i.estornado; }).sort(function(x, y){ return x.id - y.id; }).forEach(function(i){
      lista.push({id: "d" + i.id, tipo: "consumo", descricao: i.descricao + (i.quantidade > 1 ? " (x" + i.quantidade + ")" : ""), centavos: i.total_centavos});
    });
  }
  if (p.pagamentos && pagamentos){        // Crédito: pagamentos recebidos e ainda não estornados (selecionar serve para estornar)
    pagamentos.filter(function(g){ return g.tipo === "recebimento" && !g.estornado; }).sort(function(x, y){ return x.id - y.id; }).forEach(function(g){
      lista.push({id: "p" + g.id, tipo: "credito", descricao: rcDescPagamento(g), centavos: g.valor_centavos});
    });
  }
  return lista;
}
function rcTotalSelecionado(itens, marcados){
  return itens.reduce(function(soma, i){ return soma + (marcados[i.id] && i.tipo !== "credito" ? i.centavos : 0); }, 0);
}
/* Estado do azulejo a partir dos itens marcados: {marcado, parcial}. */
function rcEstadoAzulejo(itens, marcados, tipo){
  var do_tipo = itens.filter(function(i){ return i.tipo === tipo; }), n = do_tipo.filter(function(i){ return marcados[i.id]; }).length;
  return {marcado: n > 0 && n === do_tipo.length, parcial: n > 0 && n < do_tipo.length, vazio: do_tipo.length === 0};
}
/* Placa digitada: mesma regra do servidor (antiga ABC-1234 ou Mercosul ABC1D23). Devolve {placa} normalizada, {vazia: true} ou {erro}. */
function rcPlacaNormalizar(v){
  var t = String(v == null ? "" : v).replace(/[\s-]/g, "").toUpperCase();
  if (!t) return {vazia: true};
  if (/^[A-Z]{3}[0-9]{4}$/.test(t) || /^[A-Z]{3}[0-9][A-Z][0-9]{2}$/.test(t)) return {placa: t};
  return {erro: "Placa inválida. Use o formato ABC-1234 ou ABC1D23."};
}
/* Apartamentos livres no período da reserva (para "Trocar de apartamento"); o servidor confere de novo (409). */
function rcLivres(reservas, r, unidades, ocupadas){
  return unidades.filter(function(u){
    if (u === r.a || ocupadas[u]) return false;
    return !reservas.some(function(x){ return x.a === u && x.id !== r.id && x.i < r.f && r.i < x.f; });
  });
}
function rcConferirMotivo(v){
  var t = String(v == null ? "" : v).trim();
  if (!t) return {erro: "Informe o motivo do cancelamento."};
  if (t.length > 300) return {erro: "Motivo grande demais (máximo 300 caracteres)."};
  return {motivo: t};
}
/* A reserva aberta no Resumo mudou no servidor? (versão diferente, ou sumiu/foi cancelada). */
function rcMudou(aberta, atual){
  if (!atual) return true;
  return atual.versao !== aberta.versao || atual.status !== aberta.status;
}
function rcMensagemErro(status, texto){
  if (status === 403) return "Seu perfil não pode fazer isso.";
  if (status === 404) return "Esta reserva não foi encontrada. Feche e abra de novo.";
  return texto || "Não foi possível concluir. Tente de novo.";
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {rcNoites: rcNoites, rcSituacao: rcSituacao, rcPeriodo: rcPeriodo, rcTitulo: rcTitulo, rcTipoGrupo: rcTipoGrupo,
    rcBotoes: rcBotoes, rcAriaBotao: rcAriaBotao, rcSubtotais: rcSubtotais, rcAzulejos: rcAzulejos, rcLivres: rcLivres,
    rcAndar: rcAndar, rcTituloCartao: rcTituloCartao, rcEstado: rcEstado, rcItensConta: rcItensConta, rcTotalSelecionado: rcTotalSelecionado,
    rcEstadoAzulejo: rcEstadoAzulejo, rcPlacaNormalizar: rcPlacaNormalizar,
    rcConferirMotivo: rcConferirMotivo, rcMudou: rcMudou, rcMensagemErro: rcMensagemErro, RC_ROTULO: RC_ROTULO, RC_CURTO: RC_CURTO};
}
