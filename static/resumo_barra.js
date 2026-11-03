"use strict";
/* Resumo da conta, etapa 3B: ações da barra de itens que NÃO mexem em dinheiro: Extrato (imprime só o selecionado), Info (lista de
 * lançamentos, só leitura) e Fechar/Reabrir a conta. Tudo por createElement/textContent. Usa rcAbrirPainel/rcEnviar (resumo_acoes.js),
 * rcConfirmar (resumo_estado.js), rcExtratoDados (resumo_pag_logica.js). */

/* ---------- Extrato A4: só o que está selecionado (nada selecionado = a conta inteira) ---------- */
function rcExtratoLinha(tabela, a, b, c, cab){
  var tr = ntEl("tr"); [a, b, c].forEach(function(t, k){ tr.appendChild(ntEl(cab ? "th" : "td", k === 2 ? "ex-num" : "", t)); }); tabela.appendChild(tr);
}
function rcExtratoMontar(box, d){
  var r = rc.det;
  box.textContent = "";
  box.appendChild(ntEl("p", "ex-pousada", "Pousada Boa Esperança - Clube dos Oficiais da PM MG"));
  box.appendChild(ntEl("h2", "ex-titulo", "Extrato da conta"));
  box.appendChild(ntEl("p", "ex-estado", d.parcial ? "Extrato parcial: somente os itens selecionados" : (rcContaAberta() ? "Conta inteira, conta aberta" : "Conta inteira, conta fechada")));
  box.appendChild(ntEl("p", "", "Hóspede: " + r.nome + " | Apartamento " + r.a + " | Reserva #" + r.id));
  box.appendChild(ntEl("p", "", rcPeriodo(r)));
  var tb = ntEl("table", "ex-tabela"); rcExtratoLinha(tb, "Tipo", "Descrição", "Valor", true);
  d.linhas.forEach(function(l){ rcExtratoLinha(tb, l.tipo, l.descricao, l.valor); });
  if (!d.linhas.length) rcExtratoLinha(tb, "", "Nenhum item na conta", "");
  box.appendChild(tb);
  var dl = ntEl("dl", "ex-totais");
  function par(t, v, forte){ dl.appendChild(ntEl("dt", forte ? "ex-forte" : "", t)); dl.appendChild(ntEl("dd", forte ? "ex-forte" : "", v)); }
  par(d.parcial ? "Total selecionado" : "Total da conta", dsFormatarReais(d.total), true);
  if (d.pagamentos) par("Pagamentos selecionados", dsFormatarReais(d.pagamentos));
  if (d.saldo !== null) par("Saldo a pagar", dsFormatarReais(d.saldo), true);
  box.appendChild(dl);
  box.appendChild(ntEl("p", "ex-emitido", "Emitido em " + new Date().toLocaleString("pt-BR") + " por " + (sessao.usuario ? sessao.usuario.nome : "")));
  var ass = ntEl("div", "ex-ass"); ass.appendChild(ntEl("span", "", "Hóspede")); ass.appendChild(ntEl("span", "", "Recepção")); box.appendChild(ass);
}
function rcExtrato(){
  var d = rcExtratoDados(rcItensDaConta(), rc.marcados, rc.totais), box = $("rcExtratoImp");
  rcExtratoMontar(box, d);
  document.body.classList.add("imp-rcextrato");
  window.print();
  document.body.classList.remove("imp-rcextrato"); box.textContent = "";
}

/* ---------- Info: todos os lançamentos da hospedagem (somente leitura) ---------- */
var RC_FILTROS = [["", "Tudo"], ["lancamento", "Lançamentos"], ["estorno", "Estornos"], ["transferencia", "Transferências"], ["pagamento", "Pagamentos"], ["conta", "Conta e diária"]];
function rcInfoLinha(l){
  var li = ntEl("li", "rc-info-item rc-info-" + l.grupo);
  li.appendChild(ntEl("span", "rc-info-quando", dsDataHora(l.em) + " · " + l.por));
  li.appendChild(ntEl("span", "rc-info-desc", l.descricao));
  if (l.total_centavos !== null) li.appendChild(ntEl("span", "rc-info-valor", dsFormatarReais(l.total_centavos)));
  if (l.motivo) li.appendChild(ntEl("span", "rc-info-motivo suave", "Motivo: " + l.motivo));
  return li;
}
function rcInfoDesenhar(ul, itens, filtro){
  ul.textContent = "";
  var vis = itens.filter(function(l){ return !filtro || l.grupo === filtro; });
  vis.forEach(function(l){ ul.appendChild(rcInfoLinha(l)); });
  if (!vis.length) ul.appendChild(ntEl("li", "suave", "Nenhum lançamento neste filtro."));
}
function rcInfo(){
  api("GET", rcUrl("lancamentos")).then(function(r){
    if (!r.ok){ aviso(rcMensagemErro(r.status, r.dados.erro)); return; }
    var tit = rcAbrirPainel("Lançamentos da hospedagem", function(p){
      p.appendChild(ntEl("p", "suave", "Somente leitura, em ordem cronológica: lançamentos, estornos, transferências, pagamentos e eventos da conta."));
      var c = ntEl("div", "campo"), lab = ntEl("label", null, "Filtrar por tipo"), sel = ntEl("select"), ul = ntEl("ul", "rc-info");
      lab.htmlFor = sel.id = "rcInfoFiltro"; ul.setAttribute("aria-label", "Lançamentos da hospedagem");
      RC_FILTROS.forEach(function(f){ var o = ntEl("option", null, f[1]); o.value = f[0]; sel.appendChild(o); });
      sel.addEventListener("change", function(){ rcInfoDesenhar(ul, r.dados.itens, sel.value); });
      c.appendChild(lab); c.appendChild(sel); p.appendChild(c); p.appendChild(ul); rcInfoDesenhar(ul, r.dados.itens, "");
      var bt = ntEl("div", "acoes"), v = ntBotao("Fechar", ""); v.addEventListener("click", function(){ rcFecharPainel(true); });
      bt.appendChild(v); p.appendChild(bt);
    }, "info", "rcPainelItens");
    tit.focus();
  }).catch(function(){ aviso("Sem conexão com o servidor."); });
}

/* ---------- Fechar e reabrir a conta ---------- */
function rcFecharConta(){
  rcConfirmar("Fechar a conta", "fechar", [
    "O saldo está zerado. Depois de fechada, a conta não aceita novos lançamentos, pagamentos, estornos nem transferências.",
    "Só admin e atendente podem reabrir, informando o motivo."], "Fechar conta", "primario",
    {metodo: "POST", url: rcUrl("conta/fechar"), corpo: function(){ return {conta_versao: rc.conta.versao}; }, ok: "Conta fechada."}, "rcPainelItens");
}
function rcReabrirConta(){
  rcPedirMotivo("Reabrir a conta", "reabrir_conta", ["A conta volta a aceitar lançamentos e pagamentos. O motivo fica registrado."], "Reabrir conta", "primario",
    function(motivo, p, bt){ rcEnviar("POST", rcUrl("conta/reabrir"), {conta_versao: rc.conta.versao, motivo: motivo}, "Conta reaberta.", p, bt); });
}
