"use strict";
/* Aba "Despesas" do administrador: catálogo de itens de consumo (cadastrar, editar, desativar/reativar; nunca apaga).
 * Só catalogo.gerir enxerga a aba (o servidor confere de novo). Bloqueio otimista: toda alteração leva a "versao" do item.
 * Todo texto vindo do servidor entra por textContent. */

var cg = {itens: [], categorias: [], editando: null, enviando: false};

function cgMensagem(t, erro){ var m = $("cgMsg"); m.textContent = t ? (erro ? "Atenção: " : "") + t : ""; }
function cgCelula(tr, texto, classe){
  var td = document.createElement("td");
  td.textContent = texto;
  if (classe) td.className = classe;
  tr.appendChild(td);
  return td;
}
function cgBotao(texto, acao, iid, rotulo){
  var b = document.createElement("button");
  b.type = "button"; b.textContent = texto; b.setAttribute("data-acao", acao); b.setAttribute("data-iid", iid);
  b.setAttribute("aria-label", rotulo);
  return b;
}
function cgDesenhar(){
  var corpo = $("cgLista");
  corpo.textContent = "";
  cg.itens.forEach(function(i){
    var tr = document.createElement("tr");
    if (!i.ativo) tr.className = "cg-inativo";
    cgCelula(tr, i.categoria_rotulo); cgCelula(tr, i.grupo || "-"); cgCelula(tr, i.descricao);
    cgCelula(tr, dsFormatarReais(i.preco_centavos), "ds-num");
    cgCelula(tr, i.ativo ? "Ativo" : "Desativado");
    var td = cgCelula(tr, "", "acoes");
    td.appendChild(cgBotao("Editar", "editar", i.id, "Editar " + i.descricao));
    td.appendChild(cgBotao(i.ativo ? "Desativar" : "Reativar", i.ativo ? "desativar" : "reativar", i.id,
                           (i.ativo ? "Desativar " : "Reativar ") + i.descricao));
    corpo.appendChild(tr);
  });
}
function cgCarregar(){
  return api("GET", "/api/catalogo?todos=1").then(function(r){
    if (!r.ok){ cgMensagem(r.dados.erro || "Não foi possível carregar o catálogo.", true); return; }
    cg.categorias = r.dados.categorias;
    cg.itens = r.dados.itens.filter(function(i){ return i.ativo || $("cgInativos").checked; });
    cgDesenhar();
  }).catch(function(){ cgMensagem("Sem conexão com o servidor.", true); });
}
function cgPreencherCategorias(){
  var s = $("cgCategoria");
  s.textContent = "";
  cg.categorias.forEach(function(c){
    var o = document.createElement("option");
    o.value = c[0]; o.textContent = c[1];
    s.appendChild(o);
  });
}
function cgAvisoForm(t){ var a = $("cgAviso"); a.textContent = t || ""; a.classList.toggle("oculto", !t); }
function cgDesenharLog(itens){
  var ul = $("cgLog");
  ul.textContent = "";
  itens.forEach(function(l){
    var li = document.createElement("li");
    li.textContent = cgTextoLog(l);
    ul.appendChild(li);
  });
}
function cgAbrir(item){
  cg.editando = item || null;
  cgPreencherCategorias();
  $("cgTit").textContent = item ? "Editar item" : "Novo item";
  $("cgCategoria").value = item ? item.categoria : "bebidas";
  $("cgGrupo").value = item ? item.grupo : "";
  $("cgDescricao").value = item ? item.descricao : "";
  $("cgPreco").value = item ? (item.preco_centavos / 100).toFixed(2).replace(".", ",") : "";
  cgAvisoForm(""); $("cgAvisoCartao").classList.add("oculto");
  $("cgLog").textContent = "";
  if (item) api("GET", "/api/catalogo/" + encodeURIComponent(item.id) + "/log").then(function(r){ if (r.ok) cgDesenharLog(r.dados.itens); });
  $("dlgCat").showModal();
  $("cgDescricao").focus();
}
function cgSalvar(){
  if (cg.enviando) return;
  var c = cgConferirItem({categoria: $("cgCategoria").value, grupo: $("cgGrupo").value, descricao: $("cgDescricao").value, preco: $("cgPreco").value});
  if (c.erro){ cgAvisoForm(c.erro); return; }
  var ed = cg.editando, corpo = ed ? Object.assign({versao: ed.versao}, c.dados) : c.dados;
  cg.enviando = true; $("cgSalvar").disabled = true;
  api(ed ? "PUT" : "POST", ed ? "/api/catalogo/" + encodeURIComponent(ed.id) : "/api/catalogo", corpo).then(function(r){
    if (!r.ok){ cgAvisoForm(r.dados.erro || "Não foi possível salvar."); if (r.status === 409) cgCarregar(); return; }
    $("dlgCat").close(); cgMensagem(ed ? "Item atualizado." : "Item cadastrado."); return cgCarregar();
  }).catch(function(){ cgAvisoForm("Sem conexão com o servidor."); })
    .then(function(){ cg.enviando = false; $("cgSalvar").disabled = false; });
}
function cgAlternar(item, ativo){
  api("POST", "/api/catalogo/" + encodeURIComponent(item.id) + "/ativo", {ativo: ativo, versao: item.versao}).then(function(r){
    cgMensagem(r.ok ? (ativo ? "Item reativado." : "Item desativado.") : (r.dados.erro || "Não foi possível alterar."), !r.ok);
    return cgCarregar();
  }).catch(function(){ cgMensagem("Sem conexão com o servidor.", true); });
}
function cgLigar(){
  $("cgNovo").addEventListener("click", function(){ cgAbrir(null); });
  $("cgInativos").addEventListener("change", cgCarregar);
  $("cgForm").addEventListener("submit", function(ev){ ev.preventDefault(); cgSalvar(); });
  $("cgCancelar").addEventListener("click", function(){ $("dlgCat").close(); });
  $("cgFechar").addEventListener("click", function(){ $("dlgCat").close(); });
  $("cgDescricao").addEventListener("input", function(){ $("cgAvisoCartao").classList.toggle("oculto", !ctContemNumeroCartao($("cgDescricao").value)); });
  $("cgLista").addEventListener("click", function(ev){
    var b = ev.target.closest("[data-acao]");
    if (!b) return;
    var item = cg.itens.filter(function(i){ return String(i.id) === b.getAttribute("data-iid"); })[0];
    if (!item) return;
    if (b.getAttribute("data-acao") === "editar") cgAbrir(item); else cgAlternar(item, b.getAttribute("data-acao") === "reativar");
  });
  document.querySelector('nav button[data-aba="despesas"]').addEventListener("click", cgCarregar);
}
if (typeof document !== "undefined" && document.getElementById("cgLista")) cgLigar();
