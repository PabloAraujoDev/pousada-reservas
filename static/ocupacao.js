"use strict";
/* Relatório de ocupação: o DIÁLOGO (escolher período e papel) e o envio para a impressora ou o PDF.
 * Usa de ocupacao_logica.js: oc*, de app.js: $, api, pode, orientacao, inicioMapa, inicioFolha, hojeISO.
 * O cálculo é do servidor (GET /api/ocupacao e /api/ocupacao.pdf); aqui só se desenha, sempre com escape. */

var ocOrigem = null;          // botão que abriu o diálogo (o foco volta para ele)
var ocOcupado = false;        // há um pedido em andamento (evita clique duplo)

function ocPeriodoPadrao(origem){
  if (origem === "folha") return {inicio: inicioFolha, fim: ocSoma(inicioFolha, 6)};
  return ocPeriodo("mapa", hojeISO(), {inicio: inicioMapa, dias: +$("mSemanas").value});
}
function ocMostrarMsg(txt){ var m = $("ocMsg"); m.textContent = txt || ""; m.classList.toggle("erro", !!txt); }
/* Confere o formulário, mostra o erro (ou quantos dias) e liga/desliga os botões. Devolve o resultado de ocValidar. */
function ocConferir(){
  var v = ocValidar($("ocInicio").value, $("ocFim").value);
  ocMostrarMsg(v.erro);
  $("ocInfo").textContent = v.erro ? "" : v.dias + (v.dias === 1 ? " dia" : " dias") + " no período.";
  $("ocImprimir").disabled = $("ocPdf").disabled = !!v.erro || ocOcupado;
  $("ocInicio").setAttribute("aria-invalid", v.erro ? "true" : "false");
  $("ocFim").setAttribute("aria-invalid", v.erro ? "true" : "false");
  return v;
}
function ocAbrir(botao){
  ocOrigem = botao;
  var p = ocPeriodoPadrao(botao.dataset.origem);
  $("ocInicio").value = p.inicio; $("ocFim").value = p.fim;
  $("ocOrientacao").value = orientacao;
  ocOcupado = false; ocConferir();
  $("dlgOcupacao").showModal();
  $("ocTit").focus();
}
function ocFechar(){
  $("dlgOcupacao").close();
  if (ocOrigem) ocOrigem.focus();
}
function ocPedir(url){
  var pedido = fetch(url, {credentials: "same-origin"});
  ocOcupado = true; ocConferir();
  return pedido.then(function(r){
    if (r.status === 401){ irParaLogin(); }
    return r;
  }).finally(function(){ ocOcupado = false; ocConferir(); });
}
function ocMensagemDeErro(r){
  return r.json().catch(function(){ return {}; }).then(function(j){
    ocMostrarMsg(r.status === 403 ? "Seu perfil não tem permissão para este relatório." : (j.erro || "Não foi possível gerar o relatório. Tente de novo."));
  });
}
function ocImprimir(){
  var v = ocConferir(); if (v.erro || ocOcupado) return;
  var papel = $("ocOrientacao").value === "retrato" ? "retrato" : "paisagem";
  ocPedir(ocUrl("/api/ocupacao", $("ocInicio").value, $("ocFim").value, papel)).then(function(r){
    if (!r.ok) return ocMensagemDeErro(r);
    return r.json().then(function(rel){
      var d = new Date(), z = function(n){ return String(n).padStart(2, "0"); };
      var emitido = z(d.getDate()) + "/" + z(d.getMonth() + 1) + "/" + d.getFullYear() + " " + z(d.getHours()) + ":" + z(d.getMinutes());
      $("ocImpressao").innerHTML = ocHtml(rel, emitido);
      ocFechar();
      document.body.classList.add("imp-ocupacao", "ocup-" + papel);
      window.print();
      ocLimparImpressao();
    });
  }).catch(function(){ ocMostrarMsg("Não foi possível falar com o servidor. Verifique a conexão."); });
}
function ocLimparImpressao(){
  document.body.classList.remove("imp-ocupacao", "ocup-paisagem", "ocup-retrato");
  $("ocImpressao").textContent = "";                   // nomes de hóspedes não ficam na página
}
function ocBaixarPdf(){
  var v = ocConferir(); if (v.erro || ocOcupado) return;
  var ini = $("ocInicio").value, fim = $("ocFim").value;
  ocPedir(ocUrl("/api/ocupacao.pdf", ini, fim, $("ocOrientacao").value)).then(function(r){
    if (!r.ok) return ocMensagemDeErro(r);
    return r.blob().then(function(blob){
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = "ocupacao_" + ini + "_a_" + fim + ".pdf";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){ URL.revokeObjectURL(a.href); }, 10000);
      ocFechar();
    });
  }).catch(function(){ ocMostrarMsg("Não foi possível falar com o servidor. Verifique a conexão."); });
}
function ocLigar(){
  document.querySelectorAll(".oc-abrir").forEach(function(b){ b.addEventListener("click", function(){ ocAbrir(b); }); });
  document.querySelectorAll("#dlgOcupacao [data-atalho]").forEach(function(b){
    b.addEventListener("click", function(){
      var p = ocPeriodo(b.dataset.atalho, hojeISO(), {inicio: inicioMapa, dias: +$("mSemanas").value});
      $("ocInicio").value = p.inicio; $("ocFim").value = p.fim; ocConferir();
    });
  });
  $("ocInicio").addEventListener("input", ocConferir);
  $("ocFim").addEventListener("input", ocConferir);
  $("ocImprimir").addEventListener("click", ocImprimir);
  $("ocPdf").addEventListener("click", ocBaixarPdf);
  $("ocCancelar").addEventListener("click", ocFechar);
  $("ocForm").addEventListener("submit", function(ev){ ev.preventDefault(); ocImprimir(); });
  window.addEventListener("afterprint", ocLimparImpressao);
}
if (typeof document !== "undefined") ocLigar();
