"use strict";
/* Despesas: estado do diálogo e FORMULÁRIO de lançamento. Só quem tem despesas.lancar vê o formulário (o servidor confere de novo).
 * Duplo clique: o botão é desabilitado ao enviar e cada formulário carrega uma "chave"; a mesma chave nunca cria dois lançamentos.
 * Todo texto vindo do servidor entra por textContent. */

var ds = {rid: null, r: null, dados: null, json: "", chave: "", enviando: false, estornando: null, mudou: false, timer: null};

function dsMensagem(texto, erro){
  var m = $("dsMsg");
  m.textContent = texto ? (erro ? "Atenção: " : "") + texto : "";
  m.classList.toggle("ds-erro", !!erro);
}
function dsTotalAoVivo(){
  var q = dsParseQuantidade($("dsQtd").value), v = dsParseReais($("dsValor").value);
  $("dsTotalVivo").textContent = q !== null && v !== null ? dsFormatarReais(q * v) : "R$ 0,00";
}
function dsAvisarCartao(){ $("dsAvisoCartao").classList.toggle("oculto", !ctContemNumeroCartao($("dsDesc").value)); }
function dsLimparFormulario(){
  $("dsDesc").value = ""; $("dsQtd").value = "1"; $("dsValor").value = "";
  dsTotalAoVivo(); dsAvisarCartao();
}
function dsPrepararFormulario(){
  var f = $("dsForm");
  f.classList.toggle("oculto", !pode("despesas.lancar"));
  dsLimparFormulario();
  $("dsCat").value = "restaurante";
  ds.chave = dsNovaChave(); ds.enviando = false; $("dsLancar").disabled = false;
  dsMensagem("");
}
function dsAposLancar(dados){
  dsMensagem(dsDescricaoLancado(dados));
  dsLimparFormulario();
  ds.chave = dsNovaChave();           // próximo lançamento = nova chave
  ds.mudou = true;
  $("dsDesc").focus();
  return dsAtualizar();
}
function dsLancar(){
  if (ds.enviando) return;
  var c = dsConferirFormulario({categoria: $("dsCat").value, descricao: $("dsDesc").value, quantidade: $("dsQtd").value, valor: $("dsValor").value});
  if (c.erro){ dsMensagem(c.erro, true); return; }
  ds.enviando = true; $("dsLancar").disabled = true;
  api("POST", "/api/reservas/" + encodeURIComponent(ds.rid) + "/despesas", Object.assign({chave: ds.chave}, c.dados)).then(function(r){
    if (r.ok) return dsAposLancar(c.dados);
    dsMensagem(dsMensagemErro(r.status, r.dados.erro, "lancar"), true);
  }).catch(function(){ dsMensagem("Sem conexão com o servidor. Confira a conta antes de lançar de novo.", true); })
    .then(function(){ ds.enviando = false; $("dsLancar").disabled = false; });
}
function dsLigarFormulario(){
  $("dsForm").addEventListener("submit", function(ev){ ev.preventDefault(); dsLancar(); });
  ["dsQtd", "dsValor"].forEach(function(id){ $(id).addEventListener("input", dsTotalAoVivo); });
  $("dsDesc").addEventListener("input", dsAvisarCartao);
}
if (typeof document !== "undefined" && document.getElementById("dsForm")) dsLigarFormulario();
