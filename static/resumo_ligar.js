"use strict";
/* Resumo da conta: abrir, atualizar, vigiar mudanças e ligar os eventos. Usa app.js ($, api, aviso, pode, reservas, carregar, mostrar),
 * resumo_conta.js (desenho) e resumo_acoes.js (botões).
 *
 * Polling: enquanto o Resumo está aberto o redesenho automático das telas pausa (algumDialogoAberto). O próprio Resumo só PERGUNTA ao
 * servidor, a cada 8 s, se a versão da reserva mudou e, se mudou, mostra a faixa "Esta reserva mudou. Recarregar": nunca redesenha
 * por baixo do que a pessoa está digitando (notas, motivo). */

/* Ponto único para abrir uma reserva: quem pode ver reservas recebe o Resumo; o resto cai no formulário. */
function abrirReserva(r, op){
  if (pode("reservas.ver")) abrirResumo(r, op);
  else abrirForm(r);
}

/* ---------- dados ---------- */
function rcBuscarDetalhe(id){ return api("GET", "/api/reservas/" + encodeURIComponent(id)); }
function rcBuscarExtras(det){
  var ativa = det.status === "ativa", id = encodeURIComponent(det.id);
  function pegar(ok, url){ return ok ? api("GET", url).then(function(r){ return r.ok ? r.dados : null; }).catch(function(){ return null; }) : Promise.resolve(null); }
  return Promise.all([pegar(pode("despesas.ver") && ativa, "/api/reservas/" + id + "/despesas"),
    pegar(pode("pagamentos.ver") && ativa, "/api/reservas/" + id + "/pagamentos"), odBuscarGovernanca(det.a)]).then(function(res){
    var d = res[0], g = res[1];
    return {totais: d && d.totais, itens: d && d.itens, conta: d && d.conta, pagamentos: g && g.itens, pagcfg: g && g.config, gov: res[2]};
  });
}
function rcOrigem(el, id){ return {el: el && el !== document.body ? el : null, id: id}; }

/* ---------- abrir e fechar ---------- */
function abrirResumo(r, op){
  if (rc.abrindo) return;
  rc.abrindo = true;
  var origem = rcOrigem(document.activeElement, r.id);
  rcBuscarDetalhe(r.id).then(function(d){
    if (!d.ok){ aviso(rcMensagemErro(d.status, d.dados.erro)); return null; }
    return rcBuscarExtras(d.dados).then(function(x){
      var jaAberto = $("dlgResumo").open;
      rc.det = d.dados; rc.totais = x.totais; rc.itens = x.itens; rc.conta = x.conta; rc.pagamentos = x.pagamentos; rc.pagcfg = x.pagcfg; rc.gov = x.gov; rc.marcados = {}; if (!jaAberto) rc.origem = origem;
      rcDesenharDados(); rcDesenharNotas(op && op.aba); rcFecharPainel(false); mostrar($("rcMudou"), false);
      rcAjustarFaixa(prefs.resumo_recolhido !== true);
      if (!jaAberto) $("dlgResumo").showModal();
      rc.aberto = true; $("rcTit").focus(); rcContasAbertas();
      rcIniciarVigia();
    });
  }).catch(function(){ aviso("Sem conexão com o servidor."); }).then(function(){ rc.abrindo = false; });
}
function rcDevolverFoco(){
  var o = rc.origem; rc.origem = null;
  if (!o) return;
  var el = o.el && o.el.isConnected ? o.el : document.querySelector('[data-id="' + o.id + '"]');
  if (el && el.focus) el.focus();
}
function rcAoFechar(){
  rc.aberto = false; rcPararVigia();
  if (document.querySelector("#aba-canceladas.ativa")) carregarCanceladas();
  carregar().then(rcDevolverFoco, rcDevolverFoco);        // a tela por baixo volta a se atualizar
}

/* ---------- atualizar ---------- */
function rcAtualizar(comNotas){
  var antes = rc.det;
  return rcBuscarDetalhe(antes.id).then(function(d){
    if (!d.ok){ mostrar($("rcMudou"), true); return; }
    return rcBuscarExtras(d.dados).then(function(x){
      var mudouTexto = d.dados.o !== antes.o || d.dados.extras !== antes.extras || d.dados.a !== antes.a || d.dados.status !== antes.status;
      rc.det = d.dados; rc.totais = x.totais; rc.itens = x.itens; rc.conta = x.conta; rc.pagamentos = x.pagamentos; rc.pagcfg = x.pagcfg; rc.gov = x.gov;
      rcDesenharDados(); mostrar($("rcMudou"), false); rcContasAbertas();
      if (comNotas || mudouTexto) rcDesenharNotas($("rcAbas").dataset.ativa);
    });
  }).catch(function(){ aviso("Sem conexão com o servidor."); });
}
function rcChecarMudanca(){
  if (!rc.aberto) return Promise.resolve();
  return rcBuscarDetalhe(rc.det.id).then(function(d){ if (rcMudou(rc.det, d.ok ? d.dados : null)) mostrar($("rcMudou"), true); }).catch(function(){});
}
function rcIniciarVigia(){ rcPararVigia(); rc.timer = setInterval(rcChecarMudanca, 8000); }
function rcPararVigia(){ if (rc.timer){ clearInterval(rc.timer); rc.timer = null; } }

/* ---------- faixa "Resumo da conta" recolhível (estado guardado por usuário, em /api/preferencias) ---------- */
function rcAjustarFaixa(aberta){ $("rcFaixa").open = aberta; }        // mudança de programa (abrir, imprimir): não é escolha da pessoa
function rcAoAlternarFaixa(){
  if (!rc.escolheuFaixa) return;                  // só vale o que veio de um clique/tecla no título da faixa (veja rcLigar)
  rc.escolheuFaixa = false;
  var recolhido = !$("rcFaixa").open;
  if (recolhido === (prefs.resumo_recolhido === true)) return;
  prefs.resumo_recolhido = recolhido;
  api("POST", "/api/preferencias", {resumo_recolhido: recolhido}).catch(function(){});      // só estética: se falhar, vale nesta tela
}

/* ---------- teclado e eventos ---------- */
var RC_ATALHOS = {e: "editar", d: "despesas", p: "imprimir"};
function rcTeclado(ev){
  if (ev.key === "Escape" && !rcPainel().classList.contains("oculto")){ ev.preventDefault(); rcFecharPainel(true); return; }
  var t = ev.target, campo = t.closest && t.closest("input, textarea, select, [contenteditable]");
  if (campo || ev.ctrlKey || ev.metaKey || ev.altKey) return;
  var id = RC_ATALHOS[String(ev.key).toLowerCase()], b = id && document.querySelector('#dlgResumo [data-rc="' + id + '"]');
  if (b){ ev.preventDefault(); b.click(); }      // só existe o botão se o perfil pode: o atalho nunca dá mais do que a tela
}
function rcFocarBotao(id){ var b = document.querySelector('#rcCartao [data-rc="' + id + '"]'); if (b) b.focus(); }
function rcLigar(){
  ["rcFechar", "rcFechar2"].forEach(function(id){ $(id).addEventListener("click", function(){ $("dlgResumo").close(); }); });
  $("dlgResumo").addEventListener("close", rcAoFechar);
  $("dlgResumo").addEventListener("keydown", rcTeclado);
  $("rcCorpo").addEventListener("click", rcCliqueBotao);
  $("rcFaixa").querySelector("summary").addEventListener("click", function(){ rc.escolheuFaixa = true; });
  $("rcFaixa").addEventListener("toggle", rcAoAlternarFaixa);
  $("rcBaseDespesas").addEventListener("click", rcAbrirDespesas);
  $("rcBaseImprimir").addEventListener("click", rcImprimir);
  $("rcRecarregar").addEventListener("click", function(){ rcAtualizar(true).then(function(){ $("rcTit").focus(); }); });
  $("dlg").addEventListener("close", function(){ if (rc.aberto) rcAtualizar(false).then(function(){ rcFocarBotao("editar"); }); });
  $("dlgDesp").addEventListener("close", function(){ if (rc.aberto) rcAtualizar(false).then(function(){ rcFocarBotao("despesas"); }); });
  $("rcContasBtn").addEventListener("click", rcAlternarContas);
  window.addEventListener("afterprint", function(){ document.body.classList.remove("imp-resumo", "imp-fnrh", "imp-rcextrato"); });
}
if (typeof document !== "undefined" && document.getElementById("dlgResumo")) rcLigar();
