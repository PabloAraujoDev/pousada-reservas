"use strict";
/* Resumo da conta: seção "1 - NOME DO HÓSPEDE" com os azulejos Diária / Evento / Consumo / Crédito, a lista de itens por tipo e a barra de
 * itens (hoje só o carro: placa do veículo). Nesta etapa a seleção é só VISUAL (caixa de seleção + total selecionado); lançar, transferir,
 * estornar e receber ficam para a etapa 3B, que encontra aqui os ganchos: rc.marcados (ids marcados), rcItensDaConta() e #rcBarraItens.
 * Tudo entra por createElement/textContent. Usa: ntEl (notas_painel.js), rcAzulejos/rcItensConta/... (resumo_logica.js). */

function rcItensDaConta(){ var p = rcPerm(); return rcItensConta(rc.det, rc.itens, {valores: p.valores, despesas: p.despesas, pagamentos: p.pagVer}, rc.pagamentos); }
function rcContaAberta(){ return !rc.conta || rc.conta.situacao === "aberta"; }
function rcTipoDoAzulejo(id){ return id === "diaria" ? "diaria" : id === "consumo" ? "consumo" : null; }

function rcDesenharTotalSelecionado(itens){
  var t = $("rcTotalSel"); if (!t) return;
  var qtd = itens.filter(function(i){ return rc.marcados[i.id]; }).length;
  t.textContent = qtd ? "Total selecionado: " + dsFormatarReais(rcTotalSelecionado(itens, rc.marcados)) + " (" + rcPlural(qtd, "item", "itens") + ")" : "Nenhum item selecionado";
  document.querySelectorAll("#rcBarraItens .rc-so-selecao").forEach(function(b){ b.classList.toggle("oculto", !qtd); });      // Estornar e Transferir só com seleção
}
/* Atualiza as caixas dos azulejos (marcada/parcial) e o total sem redesenhar a seção (não perde o foco). */
function rcSincronizarSelecao(){
  var itens = rcItensDaConta();
  document.querySelectorAll("#rcHospede .rc-az-caixa").forEach(function(cx){
    var e = rcEstadoAzulejo(itens, rc.marcados, cx.dataset.tipo);
    cx.checked = e.marcado; cx.indeterminate = e.parcial;
  });
  document.querySelectorAll("#rcHospede .rc-item-caixa").forEach(function(cx){ cx.checked = !!rc.marcados[cx.dataset.item]; });
  rcDesenharTotalSelecionado(itens);
}
function rcAlternarTipo(tipo, marcar){
  rcItensDaConta().forEach(function(i){ if (i.tipo === tipo) rc.marcados[i.id] = marcar; });
  rcSincronizarSelecao();
}
function rcDesenharAzulejo(a){
  var d = ntEl("div", "rc-az rc-az-" + a.id + (a.desabilitado ? " rc-az-off" : ""));
  if (a.semCaixa){ d.appendChild(ntEl("span", "rc-az-rot", a.rotulo)); d.appendChild(ntEl("span", "rc-az-valor", a.valor)); d.appendChild(ntEl("span", "rc-az-nota suave", a.nota)); return d; }
  var lab = ntEl("label", "rc-az-rot"), cx = ntEl("input", "rc-az-caixa");
  cx.type = "checkbox"; cx.dataset.tipo = rcTipoDoAzulejo(a.id) || a.id; cx.setAttribute("aria-label", "Selecionar todos os itens de " + a.rotulo);
  cx.disabled = !!a.desabilitado || !a.selecionavel;
  cx.addEventListener("change", function(){ rcAlternarTipo(cx.dataset.tipo, cx.checked); });
  lab.appendChild(cx); lab.appendChild(document.createTextNode(" " + a.rotulo));
  d.appendChild(lab); d.appendChild(ntEl("span", "rc-az-valor", a.valor));
  if (a.nota) d.appendChild(ntEl("span", "rc-az-nota suave", a.nota));
  return d;
}
function rcDesenharListaItens(h, itens){
  if (!itens.length) return;
  var ul = ntEl("ul", "rc-itens"); ul.setAttribute("aria-label", "Itens da conta");
  itens.forEach(function(i){
    var li = ntEl("li", "rc-item"), lab = ntEl("label", "rc-item-rot"), cx = ntEl("input", "rc-item-caixa");
    cx.type = "checkbox"; cx.dataset.item = i.id; cx.checked = !!rc.marcados[i.id];
    cx.addEventListener("change", function(){ rc.marcados[i.id] = cx.checked; rcSincronizarSelecao(); });
    lab.appendChild(cx); lab.appendChild(ntEl("span", "rc-item-tipo suave", RC_TIPO_ITEM[i.tipo] || i.tipo));
    lab.appendChild(ntEl("span", "rc-item-desc", i.descricao)); li.appendChild(lab);
    li.appendChild(ntEl("span", "rc-item-valor", dsFormatarReais(i.centavos)));
    ul.appendChild(li);
  });
  h.appendChild(ul);
  var t = ntEl("p", "rc-total-sel", ""); t.id = "rcTotalSel"; t.setAttribute("role", "status"); t.setAttribute("aria-live", "polite");
  h.appendChild(t);
}
/* Barra de itens: placa, Extrato, Receber, Estornar, Transferir, Info e Fechar/Reabrir a conta (só o que o perfil pode; o servidor confere). */
function rcBotoesDaBarra(){
  var p = rcPerm(), r = rc.det, tot = rc.totais || {};
  return rcBarraBotoes({ativa: !rcCancelada(), veiculo: p.veiculo, despesas: p.despesas, aberta: rcContaAberta(),
    receber: p.pagReceber && p.pagVer && p.valores, estornar: p.desEstornar || p.pagEstornar, transferir: p.transferir && p.valores,
    fechar: p.contaFechar && p.pagVer && p.valores, reabrir: p.contaReabrir, saldo: tot.saldo_centavos});
}
function rcDesenharBarraItens(h, ids){
  var bar = ntEl("div", "rc-barra-itens"); bar.id = "rcBarraItens"; bar.setAttribute("role", "toolbar"); bar.setAttribute("aria-label", "Itens da hospedagem");
  ids.forEach(function(id){
    var b = rcBotao(id, rc.det);
    if (id === "estornar" || id === "transferir") b.classList.add("rc-so-selecao", "oculto");
    bar.appendChild(b);
  });
  h.appendChild(bar);
  var p = ntEl("div", "rc-acao oculto", ""); p.id = "rcPainelItens"; h.appendChild(p);
}
function rcDesenharHospede(){
  var r = rc.det, h = $("rcHospede"), p = rcPerm();
  h.textContent = "";
  h.appendChild(ntEl("h3", "rc-hosp-tit", "1 - " + String(r.nome).toLocaleUpperCase("pt-BR")));
  h.appendChild(ntEl("p", "suave rc-hosp-sub", rcPlural(r.n, "pessoa", "pessoas") + " · " + rcTipoGrupo(r)));
  var ids = rcBotoesDaBarra();
  if (ids.length) rcDesenharBarraItens(h, ids);
  var az = rcAzulejos(r, rc.totais, {valores: p.valores, despesas: p.despesas, temPagamentos: !!(rc.pagamentos && rcItensDaConta().some(function(i){ return i.tipo === "credito"; })), contaFechada: !rcContaAberta()});
  if (!az.length) return;
  var g = ntEl("div", "rc-azulejos"); g.setAttribute("role", "group"); g.setAttribute("aria-label", "Valores da conta");
  az.forEach(function(a){ g.appendChild(rcDesenharAzulejo(a)); });
  h.appendChild(g);
  var itens = rcItensDaConta();
  Object.keys(rc.marcados).forEach(function(id){ if (!itens.some(function(i){ return i.id === id; })) delete rc.marcados[id]; });
  rcDesenharListaItens(h, itens); rcSincronizarSelecao();
}
