"use strict";
/* Operação do dia: diálogo OBSERVAÇÕES (botão "Notas" da coluna Ações). O conteúdo é o painel de abas de notas_abas.js:
 *   Reserva (observação padrão + notas com autor e data), Arrumação (governança, só leitura) e Apartamento (notas da unidade).
 * Quem pode editar a reserva (reservas.editar ou reservas.editar_pagamento) recebe o botão "Editar observação padrão", que abre o
 * formulário que já existe (as regras de permissão são as de sempre). Os textos entram por textContent. */

/* ---------- tela ---------- */
function odBuscarDetalhe(rid){
  if (!rid) return Promise.resolve(null);
  return api("GET", "/api/reservas/" + encodeURIComponent(rid)).then(function(r){ return r.ok ? r.dados : null; }).catch(function(){ return null; });
}
function odAbrirNotas(b){
  var l = odLinhaDoBotao(b);
  if (l.tipo === "reserva" && !l.r) return;
  odGuardarOrigem(b);
  Promise.all([odBuscarDetalhe(b.dataset.rid), odBuscarGovernanca(l.a)]).then(function(res){
    var edita = l.tipo === "reserva" && (pode("reservas.editar") || pode("reservas.editar_pagamento"));
    $("notasTit").textContent = "Observações: " + odTituloDialogo(l);
    ntMontarAbas($("notasAbas"), $("notasPainel"), {
      rid: l.tipo === "reserva" ? l.r.id : null, unidade: l.a, det: res[0], gov: res[1], inicial: l.tipo === "reserva" ? "reserva" : "arrumacao",
      aoEditarPadrao: edita ? function(){ $("dlgNotas").close(); abrirForm(l.r); $("fo").focus(); } : null     // o formulário existente cuida das regras
    });
    $("dlgNotas").showModal();
    $("notasTit").focus();
  });
}
function odLigarNotas(){
  ["notasFechar", "notasFechar2"].forEach(function(id){ $(id).addEventListener("click", function(){ $("dlgNotas").close(); }); });
  $("dlgNotas").addEventListener("close", function(){ carregar().then(odDevolverFoco, odDevolverFoco); });      // atualiza o ponto "há observações" e devolve o foco
}
if (typeof document !== "undefined") odLigarNotas();
