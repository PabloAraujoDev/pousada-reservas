"use strict";
/* Resumo da conta: ações de ESTADO da hospedagem (etapa 3A). Cada uma abre um painel em linha com a explicação e a confirmação;
 * o servidor confere permissão, versão e regras de novo (409 mostra a mensagem dele no painel). Reaproveita rcAbrirPainel/rcEnviar
 * (resumo_acoes.js). Nada aqui monta HTML: só createElement/textContent.
 * Ganchos para a etapa 3B: rcConfirmar() serve a qualquer ação com confirmação (recebimento, estorno com motivo, transferência de despesas). */

/* Painel de confirmação: texto, botão de confirmar e Voltar. envio = {metodo, url, corpo, ok}. */
function rcConfirmar(titulo, origem, paragrafos, nomeOk, cls, envio, destino){
  var tit = rcAbrirPainel(titulo, function(p){
    paragrafos.forEach(function(t){ p.appendChild(ntEl("p", "suave", t)); });
    var bt = rcBotoesPainel(function(){ rcEnviar(envio.metodo, envio.url, envio.corpo(), envio.ok, p, bt.ok); }, nomeOk, cls);
    p.appendChild(bt.caixa);
  }, origem, destino);
  tit.focus();
}
function rcUrl(sufixo){ return "/api/reservas/" + rc.det.id + "/" + sufixo; }

/* Liberar, desfazer a liberação e reverter o check-in exigem MOTIVO (fica no histórico, com autor e data). */
function rcComMotivo(titulo, origem, paragrafos, nomeOk, cls, sufixo, msgOk){
  rcPedirMotivo(titulo, origem, paragrafos, nomeOk, cls, function(motivo, p, bt){
    rcEnviar("POST", rcUrl(sufixo), {versao: rc.det.versao, motivo: motivo}, msgOk, p, bt);
  }, "rcPainelAcao");
}
function rcLiberar(){
  rcComMotivo("Liberar o apartamento e deixar a conta aberta", "liberar", [
    "O apartamento " + rc.det.a + " volta a ficar livre (e suja) na Governança. A conta continua aberta e acessível em Despesas, e a hospedagem passa a aparecer em Contas abertas.",
    "Use quando o hóspede saiu sem acertar a conta. Quem tem permissão pode desfazer."], "Liberar e deixar a conta aberta", "primario",
    "liberar", "Apartamento liberado. A conta continua aberta.");
}
function rcReabrir(){
  rcComMotivo("Desfazer a liberação do apartamento", "reabrir", [
    "A hospedagem volta a ocupar o apartamento " + rc.det.a + " na Governança. A situação de limpeza não muda sozinha: confira a arrumação."],
    "Desfazer a liberação", "primario", "liberar/reverter", "Liberação desfeita.");
}
function rcCheckin(){
  rcConfirmar("Registrar check-in", "checkin", [
    "Registra que " + rc.det.nome + " chegou ao apartamento " + rc.det.a + ". Os cartões Check-ins e Ocupados continuam contados pelas datas."],
    "Registrar check-in", "primario",
    {metodo: "POST", url: rcUrl("checkin"), corpo: function(){ return {versao: rc.det.versao}; }, ok: "Check-in registrado."});
}
function rcReverter(){
  rcComMotivo("Reverter check-in", "reverter", [
    "Só é possível se a hospedagem não tiver nenhum lançamento: nem despesa ativa nem diária informada. Se houver, cancele ou estorne primeiro."],
    "Reverter check-in", "perigo", "checkin/reverter", "Check-in revertido.");
}

/* ---------- placa do veículo (dado pessoal; botão da barra de itens) ---------- */
function rcPlaca(){
  var r = rc.det, campo;
  var tit = rcAbrirPainel("Placa do veículo", function(p){
    p.appendChild(ntEl("p", "suave", "Opcional. Formato ABC-1234 ou ABC1D23. Dado pessoal: aparece na ficha de check-in e só para quem tem permissão."));
    campo = ntCampoTexto("Placa", r.placa || "", 8, 1); p.appendChild(campo.caixa);
    campo.campo.setAttribute("autocomplete", "off"); campo.campo.setAttribute("autocapitalize", "characters");
    var bt = rcBotoesPainel(function(){
      var v = rcPlacaNormalizar(campo.campo.value);
      if (v.erro){ rcAvisoPainel(p, v.erro); campo.campo.focus(); return; }
      var corpo = {versao: r.versao, placa: v.vazia ? null : v.placa};
      rcEnviar("PUT", "/api/reservas/" + r.id + "/placa", corpo, v.vazia ? "Placa removida." : "Placa salva.", p, bt.ok);
    }, "Salvar placa", "primario");
    p.appendChild(bt.caixa);
  }, "placa", "rcPainelItens");
  tit.focus();
}

/* ---------- ficha de check-in (FNRH): busca os dados completos (fica registrado no log) e imprime em A4 ---------- */
function rcFicha(){
  var b = document.querySelector('#rcCartao [data-rc="ficha"]');
  if (b) b.disabled = true;
  api("POST", "/api/reservas/" + rc.det.id + "/ficha", {}).then(function(r){
    if (b) b.disabled = false;
    if (!r.ok){ aviso(rcMensagemErro(r.status, r.dados.erro)); return; }
    fnrhMontar($("fnrhImpressao"), r.dados);
    document.body.classList.add("imp-fnrh");
    window.print();
    document.body.classList.remove("imp-fnrh"); $("fnrhImpressao").textContent = "";     // os dados pessoais não ficam no DOM depois de imprimir
  }).catch(function(){ if (b) b.disabled = false; aviso("Sem conexão com o servidor."); });
}

/* ---------- Contas abertas: apartamentos liberados cuja conta continua aberta (só contagem e quem; nunca valores) ---------- */
var rcCa = {itens: []};
function rcContasAbertas(){
  api("GET", "/api/contas-abertas").then(function(r){
    var sec = $("rcContas"), btn = $("rcContasBtn"), n = r.ok ? r.dados.contas_abertas : 0;
    rcCa.itens = r.ok ? r.dados.itens : [];
    mostrar(sec, n > 0);
    btn.textContent = "Contas abertas: " + n + (n === 1 ? " apartamento liberado" : " apartamentos liberados");
    if (!n){ mostrar($("rcContasLista"), false); btn.setAttribute("aria-expanded", "false"); return; }
    rcDesenharContas();
  }).catch(function(){});
}
function rcDesenharContas(){
  var ul = $("rcContasLista"); ul.textContent = "";
  rcCa.itens.forEach(function(c){
    var li = ntEl("li", "rc-conta-item"), b = ntBotao("Abrir", "rc-conta-abrir", "Abrir a conta do apartamento " + c.a + ", hóspede " + c.nome);
    li.appendChild(ntEl("span", "rc-conta-txt", "Apto " + c.a + " · " + c.nome + " · liberado em " + ntDataHora(c.conta_aberta_em) + " por " + c.conta_aberta_por));
    b.addEventListener("click", function(){ abrirResumo({id: c.id}); });
    li.appendChild(b); ul.appendChild(li);
  });
}
function rcAlternarContas(){
  var ul = $("rcContasLista"), abrir = ul.classList.contains("oculto");
  mostrar(ul, abrir); $("rcContasBtn").setAttribute("aria-expanded", abrir ? "true" : "false");
}
