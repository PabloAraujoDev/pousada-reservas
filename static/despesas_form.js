"use strict";
/* Despesas: estado do diálogo e FORMULÁRIO de lançamento. Só quem tem despesas.lancar vê o formulário (o servidor confere de novo).
 * Duplo clique: o botão é desabilitado ao enviar e cada formulário carrega uma "chave"; a mesma chave nunca cria dois lançamentos.
 * Todo texto vindo do servidor entra por textContent. */

var ds = {itens: [], rid: null, r: null, dados: null, json: "", chave: "", enviando: false, estornando: null, mudou: false, timer: null};

function dsMensagem(texto, erro){
  var m = $("dsMsg");
  m.textContent = texto ? (erro ? "Atenção: " : "") + texto : "";
  m.classList.toggle("ds-erro", !!erro);
}
function dsAvulso(){ return pode("catalogo.gerir") && $("dsAvulso").checked; }
function dsItemEscolhido(){
  var id = $("dsItem").value;
  return ds.itens.filter(function(i){ return String(i.id) === id; })[0] || null;
}
function dsTotalAoVivo(){
  var q = dsParseQuantidade($("dsQtd").value), it = dsItemEscolhido(), v = dsAvulso() ? dsParseReais($("dsValor").value) : (it ? it.preco_centavos : null);
  $("dsUnitVivo").textContent = v !== null ? dsFormatarReais(v) : "-";
  $("dsTotalVivo").textContent = q !== null && v !== null ? dsFormatarReais(q * v) : "R$ 0,00";
}
/* Seletor do catálogo: itens ativos, já em ordem alfabética, agrupados por categoria e grupo (o preço aparece no texto). */
function dsPreencherItens(itens){
  var s = $("dsItem"), antes = s.value;
  ds.itens = itens; s.textContent = "";
  dsAgruparItens(itens).forEach(function(g){
    var og = document.createElement("optgroup");
    og.label = g.rotulo;
    g.itens.forEach(function(i){
      var o = document.createElement("option");
      o.value = i.id; o.textContent = i.descricao + " - " + dsFormatarReais(i.preco_centavos);
      og.appendChild(o);
    });
    s.appendChild(og);
  });
  if (antes && ds.itens.some(function(i){ return String(i.id) === antes; })) s.value = antes;   // recarregar (409) não troca o item escolhido
  dsTotalAoVivo();
}
function dsCarregarCatalogo(){
  return api("GET", "/api/catalogo").then(function(r){
    if (r.ok) dsPreencherItens(r.dados.itens); else dsMensagem(dsMensagemErro(r.status, r.dados.erro, "lancar"), true);
  }).catch(function(){ dsMensagem("Sem conexão para carregar a lista de itens.", true); });
}
function dsAlternarAvulso(){
  var av = dsAvulso();
  document.querySelectorAll("#dsForm .ds-avulso").forEach(function(el){ el.classList.toggle("oculto", !av); });
  $("dsItem").parentNode.classList.toggle("oculto", av);
  dsTotalAoVivo(); dsAvisarCartao();
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
  $("dsCat").value = "restaurante"; $("dsAvulso").checked = false;
  $("dsModoRot").classList.toggle("oculto", !pode("catalogo.gerir"));
  $("dsItem").textContent = "";           // a escolha de outra abertura do diálogo nunca vale: começa sempre do primeiro item
  dsAlternarAvulso(); dsCarregarCatalogo();
  ds.chave = dsNovaChave(); ds.enviando = false; $("dsLancar").disabled = false;
  dsMensagem("");
}
function dsAposLancar(dados){
  dsMensagem(dsDescricaoLancado(dados));
  dsLimparFormulario();
  ds.chave = dsNovaChave();           // próximo lançamento = nova chave
  ds.mudou = true;
  $("dsItem").focus();
  return dsAtualizar();
}
function dsLancar(){
  if (ds.enviando) return;
  var c = dsAvulso() ? dsConferirFormulario({categoria: $("dsCat").value, descricao: $("dsDesc").value, quantidade: $("dsQtd").value, valor: $("dsValor").value})
                     : dsConferirPorItem(dsItemEscolhido(), $("dsQtd").value);
  if (c.erro){ dsMensagem(c.erro, true); return; }
  var it = dsItemEscolhido(), visto = dsAvulso() ? c.dados : {quantidade: c.dados.quantidade, descricao: it.descricao, valor_unit_centavos: it.preco_centavos};
  ds.enviando = true; $("dsLancar").disabled = true;
  api("POST", "/api/reservas/" + encodeURIComponent(ds.rid) + "/despesas", Object.assign({chave: ds.chave}, c.dados)).then(function(r){
    if (r.ok) return dsAposLancar(visto);
    dsMensagem(dsMensagemErro(r.status, r.dados.erro, "lancar"), true);
    if (r.status === 409 || r.status === 404) return dsCarregarCatalogo();     // preço/nome mudou ou item desativado: recarrega a lista
  }).catch(function(){ dsMensagem("Sem conexão com o servidor. Confira a conta antes de lançar de novo.", true); })
    .then(function(){ ds.enviando = false; $("dsLancar").disabled = false; });
}
function dsLigarFormulario(){
  $("dsForm").addEventListener("submit", function(ev){ ev.preventDefault(); dsLancar(); });
  ["dsQtd", "dsValor"].forEach(function(id){ $(id).addEventListener("input", dsTotalAoVivo); });
  $("dsItem").addEventListener("change", dsTotalAoVivo);
  $("dsAvulso").addEventListener("change", dsAlternarAvulso);
  $("dsDesc").addEventListener("input", dsAvisarCartao);
}
if (typeof document !== "undefined" && document.getElementById("dsForm")) dsLigarFormulario();
