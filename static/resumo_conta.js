"use strict";
/* Resumo da conta (diálogo #dlgResumo): a tela que abre ao clicar numa reserva.
 * Cartão da reserva (apto, nº, titular, período, pagamento, subtotais), barra de botões, observações em abas (notas_abas.js)
 * e a seção do hóspede titular com azulejos. O formulário #dlg continua existindo: abre pelo botão "Editar dados".
 * Valores só aparecem para quem recebeu (valores.ver / despesas.ver): o servidor filtra; sem permissão o item nem entra no DOM.
 * Todo texto entra por textContent (createElement); nada de HTML montado como texto. Usa: ntEl/ntBotao (notas_painel.js), rc* (resumo_logica.js). */

var rc = {det: null, totais: null, itens: null, pagamentos: null, pagcfg: null, conta: null, gov: null, origem: null, timer: null, aberto: false, abrindo: false, marcados: {}};
var RC_SVG = "http://www.w3.org/2000/svg";
var RC_ICONES = {     // desenhos simples próprios (24x24)
  editar: "M4 20v-4L15 5l4 4L8 20H4zM16.4 3.6l1.2-1.2a1.4 1.4 0 0 1 2 0l2 2a1.4 1.4 0 0 1 0 2l-1.2 1.2-4-4z",
  hospedes: "M9 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm8 1a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM3 19c0-3 2.7-5 6-5s6 2 6 5H3zm13-4.8c2.8.2 5 1.8 5 4.8h-4c0-1.8-.4-3.4-1-4.8z",
  trocar: "M4 8h12V5l5 5-5 5v-3H4V8zm16 8H8v3l-5-5 5-5v3h12v4z",
  cancelar: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM8 9.4 9.4 8l2.6 2.6L14.6 8 16 9.4 13.4 12l2.6 2.6-1.4 1.4-2.6-2.6L9.4 16 8 14.6l2.6-2.6L8 9.4z",
  reativar: "M12 5V2L7 6l5 4V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z",
  ficha: "M7 3h10v4H7V3zM5 8h14a2 2 0 0 1 2 2v6h-4v4H7v-4H3v-6a2 2 0 0 1 2-2zm4 7v4h6v-4H9z",
  imprimir: "M6 2h9l5 5v15H6V2zm8 1.5V8h4.5L14 3.5zM8 12h8v1.5H8V12zm0 3h8v1.5H8V15zm0 3h5v1.5H8V18z",
  liberar: "M7 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm12-6h-8v7H3V5H1v15h2v-3h18v3h2v-9a4 4 0 0 0-4-4z",
  reabrir: "M12 5V2L7 6l5 4V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z",
  checkin: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm-1.2 13L7 12.2l1.4-1.4 2.4 2.4 4.8-4.8L17 9.8 10.8 16z",
  reverter: "M12.5 8c-2.65 0-5.05 1-6.9 2.6L2 7v9h9l-3.6-3.6A8 8 0 0 1 12.5 11c3.5 0 6.55 2.3 7.6 5.5l2.4-.8C21.1 11 17.15 8 12.5 8z",
  placa: "M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11v7h-2v-2H7v2H5v-7zm3.1-4-.9 3h9.6l-.9-3H8.1zM7.5 13a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4zm9 0a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4z",
  historico: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm1 4v5l4 2-.8 1.6L11 13V7h2z",
  despesas: "M3 6h18v12H3V6zm9 2.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  extrato: "M6 2h9l5 5v15H6V2zm8 1.5V8h4.5L14 3.5zM8 12h8v1.5H8V12zm0 3h8v1.5H8V15zm0 3h5v1.5H8V18z",
  receber: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15.5V19h-2v-1.5c-1.4-.2-2.5-.9-3-2l1.7-.9c.3.7 1 1.2 2 1.2 1 0 1.6-.4 1.6-1 0-.7-.6-1-2-1.4-1.6-.5-3-1.1-3-2.8 0-1.2.9-2.1 2.7-2.4V6.5h2V8c1.1.2 2 .8 2.4 1.7l-1.6.9c-.3-.6-.9-.9-1.7-.9-.9 0-1.4.4-1.4.9 0 .6.5.9 1.9 1.3 1.7.5 3.1 1.2 3.1 2.9 0 1.3-1 2.3-2.7 2.7z",
  estornar: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM7 11h10v2H7v-2z",
  transferir: "M7 4l-4 4 4 4V9h7V7H7V4zm10 8v3h-7v2h7v3l4-4-4-4z",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm-1 4h2v2h-2V7zm0 4h2v6h-2v-6z",
  fechar: "M17 9V7a5 5 0 0 0-10 0v2H5v12h14V9h-2zM9 7a3 3 0 0 1 6 0v2H9V7z",
  reabrir_conta: "M17 9V7a5 5 0 0 0-9.6-2l1.9.8A3 3 0 0 1 15 7v2H5v12h14V9h-2z"
};

function rcIcone(id){
  var s = document.createElementNS(RC_SVG, "svg"), p = document.createElementNS(RC_SVG, "path");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("width", "22"); s.setAttribute("height", "22");
  s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false"); s.setAttribute("class", "od-ico");
  p.setAttribute("d", RC_ICONES[id]); s.appendChild(p);
  return s;
}
function rcBotao(id, r){          // botão de ícone com rótulo curto visível e rótulo completo para leitor de tela
  var b = ntBotao("", "rc-bt rc-bt-" + id, rcAriaBotao(id, r));
  b.dataset.rc = id; b.title = RC_ROTULO[id];
  b.appendChild(rcIcone(id)); b.appendChild(ntEl("span", "rc-bt-rot", RC_CURTO[id]));
  return b;
}
function rcPerm(){
  return {editar: pode("reservas.editar"), editarPag: pode("reservas.editar_pagamento"), cancelar: pode("reservas.cancelar"),
    reativar: pode("reservas.reativar"), historico: pode("historico.reserva") || pode("historico.completo"),
    despesas: pode("despesas.ver"), valores: pode("valores.ver"), liberar: pode("conta.liberar"), ficha: pode("ficha.imprimir"),
    checkin: pode("checkin.registrar"), pagVer: pode("pagamentos.ver"), pagReceber: pode("pagamentos.receber"), pagEstornar: pode("pagamentos.estornar"),
    desEstornar: pode("despesas.estornar"), transferir: pode("despesas.transferir"), contaFechar: pode("despesas.conta"), contaReabrir: pode("conta.reabrir"), valoresEditar: pode("valores.editar"), reverter: pode("checkin.reverter"), veiculo: pode("veiculo.editar"), hospedes: pode("hospedes.gerir")};
}
function rcCancelada(){ return !!rc.det && rc.det.status !== "ativa"; }
function rcSubs(){ var p = rcPerm(); return rcSubtotais(rc.det, rc.totais, {valores: p.valores, despesas: p.despesas}); }

/* ---------- desenho ---------- */
function rcDesenharCabecalho(){
  var r = rc.det, sit = rcSituacao(r, hojeISO()), sub = rcSubs();
  $("rcTit").textContent = rcTitulo(r);
  var s = $("rcSit"); s.textContent = "";
  s.appendChild(ntEl("span", "rc-bolinha rc-s-" + sit.chave)); s.appendChild(document.createTextNode(sit.rotulo));
  var t = $("rcTotal"); t.textContent = "";
  if (sub.total){ t.appendChild(ntEl("span", "rc-total-rot", "Total da estadia")); t.appendChild(ntEl("strong", "rc-total-valor", sub.total)); }
  else t.appendChild(ntEl("span", "pilula " + r.p, "Pagamento: " + (RC_PAGAMENTO[r.p] || r.p)));
}
function rcLinha(rotulo, valor, cls){
  var p = ntEl("p", "rc-linha" + (cls ? " " + cls : "")); p.appendChild(ntEl("span", "rc-rot", rotulo)); p.appendChild(ntEl("span", "rc-val", valor));
  return p;
}
function rcDesenharTotais(c){          // lado direito do cartão: Diárias, Lançamentos e Total da estadia (só o que o perfil recebeu)
  var sub = rcSubs();
  if (!sub.linhas.length && !sub.total) return;
  var dl = ntEl("dl", "rc-subtotais");
  sub.linhas.concat(sub.total ? [{rotulo: "Total da estadia", texto: sub.total, forte: true}] : []).forEach(function(l){
    dl.appendChild(ntEl("dt", l.forte ? "rc-forte" : "", l.rotulo)); dl.appendChild(ntEl("dd", l.forte ? "rc-forte" : "", l.texto));
  });
  var box = ntEl("div", "rc-totais"); box.appendChild(ntEl("h3", "rc-totais-tit", "Totais")); box.appendChild(dl);
  c.appendChild(box);
}
function rcTarifa(r){
  var d = r.diaria_centavos;
  return d == null ? "Diária não informada" : dsFormatarReais(d) + " por noite";
}
function rcQuandoCheckin(r){
  return r.checkin_em ? "Check-in efetuado em " + ntDataHora(r.checkin_em) + " por " + r.checkin_por : "Check-in pendente";
}
function rcDesenharDados2(esq, r, canc){          // coluna esquerda do cartão
  var extras = (r.extras || "").trim();
  esq.appendChild(rcLinha("Hóspede titular", r.nome, "rc-titular"));
  esq.appendChild(rcLinha("Tipo", rcTipoGrupo(r)));
  esq.appendChild(rcLinha("Período", rcPeriodo(r)));
  if (pode("valores.ver")) esq.appendChild(rcLinha("Tarifa", rcTarifa(r)));
  esq.appendChild(rcLinha("Pessoas", rcPlural(r.n, "pessoa", "pessoas")));
  var pg = ntEl("p", "rc-linha"); pg.appendChild(ntEl("span", "rc-rot", "Pagamento"));
  pg.appendChild(ntEl("span", "pilula " + r.p, RC_PAGAMENTO[r.p] || r.p)); esq.appendChild(pg);
  esq.appendChild(rcLinha("Acompanhantes e extras", extras || "Nenhum informado", extras ? "" : "suave"));
  if (r.placa) esq.appendChild(rcLinha("Placa do veículo", r.placa, "rc-placa"));
  if (rc.conta && rc.conta.situacao === "fechada") esq.appendChild(rcLinha("Conta", "Fechada em " + ntDataHora(rc.conta.fechada_em), "rc-estado"));
  if (!canc){
    esq.appendChild(rcLinha("Hospedagem", rcEstado(r) + (r.estado_hospedagem === "conta_aberta" ? " em " + ntDataHora(r.conta_aberta_em) + " por " + r.conta_aberta_por : ""),
      "rc-estado rc-e-" + (r.estado_hospedagem || "pendente")));
    if (r.estado_hospedagem !== "pendente") esq.appendChild(rcLinha("Check-in", rcQuandoCheckin(r)));
  }
}
function rcDesenharCartao(){
  var r = rc.det, c = $("rcCartao"), canc = rcCancelada();
  c.textContent = "";
  var topo = ntEl("div", "rc-apto"); topo.appendChild(ntEl("h3", "rc-apto-nome", rcTituloCartao(r)));
  topo.appendChild(ntEl("span", "rc-reserva suave", "Reserva #" + r.id)); c.appendChild(topo);
  var grade = ntEl("div", "rc-cartao-grade"), esq = ntEl("div", "rc-dados");
  rcDesenharDados2(esq, r, canc);
  grade.appendChild(esq); rcDesenharTotais(grade); c.appendChild(grade);
  if (canc) c.appendChild(ntEl("p", "rc-cancelada", "Cancelada em " + ntDataHora(r.cancelado_em) + " por " + r.cancelado_por + ". Motivo: " + r.motivo_cancelamento));
  var barra = ntEl("div", "rc-barra"); barra.setAttribute("role", "toolbar"); barra.setAttribute("aria-label", "Ações da reserva");
  rcBotoes(rcPerm(), canc, r.estado_hospedagem).forEach(function(id){ barra.appendChild(rcBotao(id, r)); });
  c.appendChild(barra);
  c.appendChild(ntEl("div", "rc-acao oculto", "")).id = "rcPainelAcao";
}
function rcDesenharNotas(inicial){
  var r = rc.det, edita = !rcCancelada() && (pode("reservas.editar") || pode("reservas.editar_pagamento"));
  ntMontarAbas($("rcAbas"), $("rcPainel"), {rid: r.id, unidade: r.a, det: r, gov: rc.gov, inicial: inicial || "reserva", leitura: rcCancelada(),
    aoEditarPadrao: edita ? function(){ rcEditar(false); } : null});
  var ver = !rcCancelada() && pode("despesas.ver");
  mostrar($("rcBaseDespesas"), ver);
}
function rcDesenharDados(){ rcDesenharCabecalho(); rcDesenharCartao(); rcDesenharHospede(); }
