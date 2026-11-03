"use strict";
/* Despesas: diálogo da conta da reserva (lista, totais, estorno, extrato A4, atualização a cada 8 s).
 * O botão da coluna Ações (operacao_acoes.js) chama odAbrirDespesas. Valores só existem aqui, por despesas.ver.
 * Nada se edita nem se apaga: o erro é corrigido por ESTORNO (nova linha negativa, com motivo). Texto do servidor: sempre textContent. */

function dsCelula(tr, rotulo, texto, classe){
  var td = document.createElement("td");
  td.setAttribute("data-r", rotulo); td.textContent = texto;
  if (classe) td.className = classe;
  tr.appendChild(td);
  return td;
}
function dsTextoSituacao(it, porId){
  if (it.tipo === "estorno") return "Estorno do lançamento nº " + it.estorno_de + ". Motivo: " + it.motivo;
  if (!it.estornado) return "";
  var e = porId[it.estorno_id];
  return e ? "Estornado por " + e.por + " em " + dsDataHora(e.em) + ". Motivo: " + e.motivo : "Estornado";
}
function dsBotaoEstornar(it){
  var b = document.createElement("button");
  b.type = "button"; b.className = "ds-estornar"; b.textContent = "Estornar";
  b.setAttribute("data-lid", it.id);
  b.setAttribute("aria-label", "Cancelar este lançamento: " + it.quantidade + " x " + it.descricao + ", " + dsFormatarReais(it.total_centavos));
  return b;
}
function dsLinha(it, porId){
  var tr = document.createElement("tr"), sit = dsSituacaoLinha(it);
  tr.className = "ds-linha ds-s-" + sit;
  dsCelula(tr, "Data", dsDataHora(it.em));
  dsCelula(tr, "Categoria", dsRotuloCategoria(it.categoria));
  dsCelula(tr, "Descrição", (it.tipo === "estorno" ? "Estorno: " : "") + it.descricao, "ds-desc");
  dsCelula(tr, "Qtd", String(it.quantidade), "ds-num");
  dsCelula(tr, "Unitário", dsFormatarReais(it.valor_unit_centavos), "ds-num");
  dsCelula(tr, "Total", dsFormatarReais(it.total_centavos), "ds-num");
  dsCelula(tr, "Quem", it.por);
  var acao = dsCelula(tr, "Situação", dsTextoSituacao(it, porId), "ds-sit");
  if (sit === "normal" && pode("despesas.estornar")) acao.appendChild(dsBotaoEstornar(it));
  return tr;
}
function dsDesenharLista(itens){
  var corpo = $("dsLista"), porId = {};
  itens.forEach(function(i){ porId[i.id] = i; });
  corpo.textContent = "";
  itens.forEach(function(i){ corpo.appendChild(dsLinha(i, porId)); });
  $("dsVazio").classList.toggle("oculto", itens.length > 0);
  $("dsTabela").classList.toggle("oculto", itens.length === 0);
}
function dsDesenharTotais(t){
  var dl = $("dsTotais"); dl.textContent = "";
  dsLinhasTotais(t).forEach(function(par){
    var dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = par[0]; dd.textContent = par[1];
    if (par[0] === "Total da estadia") { dt.className = dd.className = "ds-forte"; }
    dl.appendChild(dt); dl.appendChild(dd);
  });
}
function dsDesenhar(d){
  $("dsSituacao").textContent = d.conta.situacao === "aberta" ? "Conta aberta" : "Conta fechada";
  dsDesenharTotais(d.totais);
  dsDesenharLista(d.itens);
  if (ds.estornando && d.itens.some(function(i){ return i.id === ds.estornando && i.estornado; })) dsFecharEstorno(false);
}
function dsAplicar(resp){
  var json = JSON.stringify(resp);
  if (json === ds.json) return;      // nada mudou: não redesenha
  ds.json = json; ds.dados = resp;
  dsDesenhar(resp);
}
function dsBuscar(){ return api("GET", "/api/reservas/" + encodeURIComponent(ds.rid) + "/despesas"); }
function dsAtualizar(){
  return dsBuscar().then(function(r){ if (r.ok) dsAplicar(r.dados); }).catch(function(){});
}

/* ---------- estorno (confirmação com motivo, no próprio diálogo) ---------- */
function dsAbrirEstorno(lid){
  var it = ds.dados.itens.filter(function(i){ return i.id === lid; })[0];
  if (!it) return;
  ds.estornando = lid;
  $("dsEstornoTxt").textContent = "Cancelar este lançamento: " + it.quantidade + " x " + it.descricao + " (" + dsFormatarReais(it.total_centavos) + ").";
  $("dsMotivo").value = ""; $("dsMotivoAviso").classList.add("oculto");
  $("dsEstorno").classList.remove("oculto");
  $("dsMotivo").focus();
}
function dsFecharEstorno(devolverFoco){
  var lid = ds.estornando;
  ds.estornando = null;
  $("dsEstorno").classList.add("oculto");
  var b = lid && document.querySelector('#dsLista [data-lid="' + lid + '"]');
  if (devolverFoco !== false) (b || $("dsDesc")).focus();
}
function dsConfirmarEstorno(){
  var m = dsConferirMotivo($("dsMotivo").value);
  if (m.erro){ dsMensagem(m.erro, true); $("dsMotivo").focus(); return; }
  if (ds.enviando) return;
  ds.enviando = true; $("dsConfirmarEstorno").disabled = true;
  api("POST", "/api/despesas/" + encodeURIComponent(ds.estornando) + "/estorno", {motivo: m.motivo}).then(function(r){
    if (!r.ok){ dsMensagem(dsMensagemErro(r.status, r.dados.erro, "estornar"), true); return dsAtualizar(); }
    dsMensagem("Lançamento cancelado por estorno."); ds.mudou = true;
    dsFecharEstorno(false);
    return dsAtualizar().then(function(){ $("dsDesc").focus(); });
  }).catch(function(){ dsMensagem("Sem conexão com o servidor. Confira a conta antes de tentar de novo.", true); })
    .then(function(){ ds.enviando = false; $("dsConfirmarEstorno").disabled = false; });
}

/* ---------- extrato A4 (só o diálogo; veja .imp-extrato em app.css) ---------- */
function dsPeriodoTexto(r){
  var n = odNoites(r.i, r.f);
  return "Período: " + cdDataBR(r.i) + " a " + cdDataBR(r.f) + " | " + n + (n === 1 ? " noite" : " noites");
}
function dsImprimirExtrato(){
  var r = ds.r, d = ds.dados;
  $("dsImpInfo").textContent = "Apartamento " + r.a + " | Hóspede: " + r.nome + " | " + dsPeriodoTexto(r);
  $("dsImpEstado").textContent = d.conta.situacao === "aberta" ? "Extrato parcial, conta aberta" : "Conta fechada";
  $("dsImpEmitido").textContent = "Emitido em " + new Date().toLocaleString("pt-BR");
  document.body.classList.add("imp-extrato");
  window.print();
  document.body.classList.remove("imp-extrato");
}

/* ---------- abrir, fechar, atualizar a cada 8 s ---------- */
function dsParar(){ if (ds.timer){ clearInterval(ds.timer); ds.timer = null; } }
function dsIniciarAtualizacao(){
  dsParar();
  ds.timer = setInterval(function(){ if (!ds.enviando) dsAtualizar(); }, 8000);     // só a lista e os totais: o formulário não é tocado
}
function odAbrirDespesas(b){
  var r = b.dataset.rid ? reservaPorId(b.dataset.rid) : null;
  if (!r) return;
  odGuardarOrigem(b);
  ds.rid = r.id; ds.r = r; ds.json = ""; ds.mudou = false; ds.estornando = null;
  dsBuscar().then(function(resp){
    if (!resp.ok){ aviso(dsMensagemErro(resp.status, resp.dados.erro)); odOrigem = null; return; }
    $("dsTit").textContent = "Despesas: Apartamento " + r.a + " - " + r.nome;
    dsPrepararFormulario();
    $("dsEstorno").classList.add("oculto");
    dsAplicar(resp.dados);
    $("dlgDesp").showModal();
    (pode("despesas.lancar") ? $("dsDesc") : $("dsTit")).focus();
    dsIniciarAtualizacao();
  }).catch(function(){ aviso("Sem conexão com o servidor."); odOrigem = null; });
}
function dsAoFechar(){
  dsParar();
  var depois = ds.mudou && typeof carregar === "function" ? carregar() : Promise.resolve();     // atualiza o ponto do botão Despesas
  depois.then(odDevolverFoco);
}
function dsLigar(){
  ["dsFechar", "dsFechar2"].forEach(function(id){ $(id).addEventListener("click", function(){ $("dlgDesp").close(); }); });
  $("dlgDesp").addEventListener("close", dsAoFechar);
  $("dlgDesp").addEventListener("cancel", function(ev){      // Esc: primeiro fecha a confirmação de estorno, depois o diálogo
    if (ds.estornando){ ev.preventDefault(); dsFecharEstorno(true); }
  });
  $("dsLista").addEventListener("click", function(ev){
    var b = ev.target.closest("[data-lid]");
    if (b) dsAbrirEstorno(+b.getAttribute("data-lid"));
  });
  $("dsEstorno").addEventListener("submit", function(ev){ ev.preventDefault(); dsConfirmarEstorno(); });
  $("dsCancelarEstorno").addEventListener("click", function(){ dsFecharEstorno(true); });
  $("dsMotivo").addEventListener("input", function(){ $("dsMotivoAviso").classList.toggle("oculto", !ctContemNumeroCartao($("dsMotivo").value)); });
  $("dsImprimir").addEventListener("click", dsImprimirExtrato);
  window.addEventListener("afterprint", function(){ document.body.classList.remove("imp-extrato"); });
}
if (typeof document !== "undefined" && document.getElementById("dlgDesp")) dsLigar();
