"use strict";
/* Resumo da conta: o que cada botão da barra faz. Editar dados e Histórico reaproveitam o formulário #dlg (app.js);
 * Transferência de apartamento reaproveita POST /mover; Cancelar usa o DELETE de sempre (com motivo); Despesas abre o diálogo existente.
 * Trocar e Cancelar abrem um painel em linha dentro do cartão (Esc fecha só o painel). O servidor confere tudo de novo. */

/* ---------- painel em linha (um no cartão, outro na seção do hóspede; só um aberto por vez) ---------- */
var RC_PAINEIS = ["rcPainelAcao", "rcPainelItens"];
function rcPainel(){ return $(rc.painelId || "rcPainelAcao"); }
function rcAbrirPainel(titulo, construir, origem, destino){
  rcFecharPainel(false);
  rc.painelId = destino || "rcPainelAcao";
  var p = rcPainel(); p.dataset.origem = origem || ""; p.classList.remove("oculto");
  var h = ntEl("h3", null, titulo); h.tabIndex = -1; p.appendChild(h);
  construir(p);
  return h;
}
function rcFecharPainel(devolverFoco){
  var p = rcPainel(), id = p && p.dataset.origem;
  RC_PAINEIS.forEach(function(i){ var e = $(i); if (e){ e.classList.add("oculto"); e.textContent = ""; e.dataset.origem = ""; } });
  var b = devolverFoco && id && document.querySelector('#dlgResumo [data-rc="' + id + '"]');
  if (b) b.focus();
}
function rcAvisoPainel(p, texto){
  var a = p.querySelector(".aviso"); if (!a){ a = ntEl("p", "aviso erro"); a.setAttribute("role", "alert"); p.insertBefore(a, p.querySelector(".acoes")); }
  a.textContent = texto;
}
function rcBotoesPainel(ok, nomeOk, cls){
  var bt = ntEl("div", "acoes"), b = ntBotao(nomeOk, cls), v = ntBotao("Voltar", "");
  b.addEventListener("click", ok); v.addEventListener("click", function(){ rcFecharPainel(true); });
  bt.appendChild(b); bt.appendChild(v);
  return {caixa: bt, ok: b};
}
/* Envia uma alteração da reserva; em caso de sucesso fecha o painel, atualiza as listas e o Resumo. */
function rcEnviar(metodo, url, corpo, msgOk, painel, botao){
  botao.disabled = true;
  api(metodo, url, corpo).then(function(r){
    botao.disabled = false;
    if (r.ok){ rcFecharPainel(false); aviso(msgOk); carregar(); rcAtualizar(true); return; }
    var m = rcMensagemErro(r.status, r.dados.erro);
    if (painel) rcAvisoPainel(painel, m); else aviso(m);
    if (painel) botao.focus();                      // o botão desabilitado perdeu o foco: sem isto o Esc fecharia o Resumo inteiro
    if (r.status === 409) rcChecarMudanca();
  }).catch(function(){ botao.disabled = false; if (painel) botao.focus(); var m = "Sem conexão com o servidor."; if (painel) rcAvisoPainel(painel, m); else aviso(m); });
}

/* ---------- Trocar de apartamento ---------- */
function rcTrocar(){
  var r = rc.det, livres = rcLivres(reservas, r, UNIDADES, OCUPADAS);
  var tit = rcAbrirPainel("Transferência de apartamento", function(p){
    p.appendChild(ntEl("p", "suave", "Apartamentos livres de " + rcDataBR(r.i) + " a " + rcDataBR(r.f) + " (a reserva mantém as datas)."));
    if (!livres.length){ p.appendChild(ntEl("p", "aviso erro", "Nenhum apartamento livre neste período.")); }
    var sel = ntEl("select"); sel.id = "rcNovoApto";
    livres.forEach(function(u){ var o = ntEl("option", null, u); o.value = u; sel.appendChild(o); });
    if (livres.length){
      var c = ntEl("div", "campo"), lab = ntEl("label", null, "Novo apartamento"); lab.htmlFor = "rcNovoApto";
      c.appendChild(lab); c.appendChild(sel); p.appendChild(c);
    }
    var bt = rcBotoesPainel(function(){
      rcEnviar("POST", "/api/reservas/" + r.id + "/mover", {versao: r.versao, a: sel.value}, "Reserva movida para o apartamento " + sel.value + ".", p, bt.ok);
    }, "Transferir de apartamento", "primario");
    bt.ok.disabled = !livres.length; p.appendChild(bt.caixa);
  }, "trocar");
  tit.focus();
}

/* ---------- Cancelar reserva ---------- */
function rcCancelar(){
  var r = rc.det, campo;
  var tit = rcAbrirPainel("Cancelar esta reserva", function(p){
    p.appendChild(ntEl("p", "suave", "A reserva sai do mapa, mas continua guardada com o motivo. Se houver despesas lançadas, estorne antes."));
    campo = ntCampoTexto("Motivo do cancelamento", "", 300, 2); p.appendChild(campo.caixa);
    var bt = rcBotoesPainel(function(){
      var v = rcConferirMotivo(campo.campo.value);
      if (v.erro){ rcAvisoPainel(p, v.erro); campo.campo.focus(); return; }
      rcEnviar("DELETE", "/api/reservas/" + r.id, {versao: r.versao, motivo: v.motivo}, "Reserva cancelada.", p, bt.ok);
    }, "Confirmar cancelamento", "perigo");
    p.appendChild(bt.caixa);
  }, "cancelar");
  tit.focus();
}
function rcReativar(){
  var b = document.querySelector('#rcCartao [data-rc="reativar"]');
  rcEnviar("POST", "/api/reservas/" + rc.det.id + "/reativar", {versao: rc.det.versao}, "Reserva reativada.", null, b || document.createElement("button"));
}

/* ---------- formulário, histórico, despesas, ficha ---------- */
function rcEditar(modo){          // modo: "extras" (Acompanhantes), false (observação padrão) ou undefined (padrão do formulário)
  abrirForm(rc.det);
  if (modo === "extras" && !$("fextras").disabled) $("fextras").focus();
  else if (modo === false && !$("fo").disabled) $("fo").focus();
}
function rcHistorico(){ abrirForm(rc.det); painelForm("historico"); }
function rcAbrirDespesas(){
  var b = document.createElement("button"); b.dataset.rid = rc.det.id;      // sem tabela de origem: odGuardarOrigem aceita
  odAbrirDespesas(b);
}
function rcImprimir(){
  $("rcImpEmitido").textContent = "Emitido em " + new Date().toLocaleString("pt-BR");
  var estava = $("rcFaixa").open;
  rcAjustarFaixa(true);              // a ficha imprime o cartão mesmo que a faixa esteja recolhida na tela
  document.body.classList.add("imp-resumo");
  window.print();
  document.body.classList.remove("imp-resumo");
  rcAjustarFaixa(estava);
}
var RC_ACOES = {editar: function(){ rcEditar(); }, trocar: rcTrocar, cancelar: rcCancelar,
  reativar: rcReativar, imprimir: rcImprimir, historico: rcHistorico, despesas: rcAbrirDespesas,
  hospedes: function(){ rcHospedes(); }, liberar: function(){ rcLiberar(); }, reabrir: function(){ rcReabrir(); }, ficha: function(){ rcFicha(); },
  checkin: function(){ rcCheckin(); }, reverter: function(){ rcReverter(); }, placa: function(){ rcPlaca(); },
  extrato: function(){ rcExtrato(); }, receber: function(){ rcReceber(); }, estornar: function(){ rcEstornar(); }, transferir: function(){ rcTransferir(); },
  info: function(){ rcInfo(); }, fechar: function(){ rcFecharConta(); }, reabrir_conta: function(){ rcReabrirConta(); }};      // (resumo_estado.js, resumo_hospedes.js)
function rcCliqueBotao(ev){
  var b = ev.target.closest("[data-rc]");
  if (!b || !RC_ACOES[b.dataset.rc]) return;
  RC_ACOES[b.dataset.rc]();
}
