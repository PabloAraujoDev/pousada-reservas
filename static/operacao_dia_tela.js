"use strict";
/* Operação do dia: a TELA das listas dos cartões.
 *  - Cabeçalho da lista do Calendário (título, contador).
 *  - Painel embutido do Mapa da reserva (#mrLista): clique num cartão abre a lista logo abaixo, no lugar (sem diálogo).
 * Usa de calendario_dia.js: cd*, de operacao_dia.js: od*, de app.js: $, esc, pode, reservas, mostrar, abrirForm.
 * A lista é só leitura; o clique numa linha abre a reserva e, num vago, "Nova reserva" (se o perfil pode criar). */

var mrCategoria = null;       // cartão ativo no Mapa (independente do Calendário)
var mrBusca = "";

/* O que as duas listas compartilham. acoes: função(linha) -> html da coluna Ações, ou null (sem coluna). */
function odContexto(criar, vazio, legenda, dia){
  var comAcoes = pode("reservas.ver") && typeof odHtmlAcoes === "function";
  return {criar: criar, hoje: cdHoje(), reservas: reservas, vazio: vazio, legenda: legenda, dia: dia,
    acoes: comAcoes ? function(l){ return odHtmlAcoes(l, dia); } : null};
}
function odTextoSeMudou(el, texto){ if (el.textContent !== texto) el.textContent = texto; }   // não reanuncia o que não mudou

/* ---------- Calendário ---------- */
function odCabecalhoCalendario(cat, dia, linhas){
  var hoje = cdHoje(), quando = dia === hoje ? " (hoje)" : " (neste dia)";
  odTextoSeMudou($("cdListaTit"), cat ? odTitulo(cat, dia, hoje) : "Movimento de " + cdDataBR(dia) + quando);
  odTextoSeMudou($("cdListaResumo"), odContador(linhas, cat));
  odTextoSeMudou($("cdLimpar"), cat ? "Fechar lista" : "Limpar pesquisa");
}

/* ---------- Mapa da reserva ---------- */
function odDesenharPainelMapa(ind, dia){
  var cat = mrCategoria, painel = $("mrLista");
  mostrar(painel, !!cat && pode("reservas.ver"));
  if (!cat || !pode("reservas.ver")) return;
  var hoje = cdHoje(), f = cdFiltrar(ind.est, cat, mrBusca);
  odTextoSeMudou($("mrListaTit"), odTitulo(cat, dia, hoje));
  odTextoSeMudou($("mrListaCont"), odContador(f.linhas, cat) + (mrBusca.trim() ? " (de " + f.total + ")" : ""));
  cdTrocar($("mrTabela"), odHtmlTabela(f.linhas, dia, cat, odContexto(pode("reservas.criar"), odVazio(cat, mrBusca), OD_TITULO[cat] + " do dia", dia)));
}
function odAbrirMapa(cat){
  mrCategoria = cat; cdDesenharTudo();
  $("mrListaTit").focus();         // o foco vai para o título; o leitor de tela anuncia "Check-ins de ..."
}
function odFecharMapa(){
  var cat = mrCategoria;
  mrCategoria = null; mrBusca = ""; $("mrBusca").value = "";
  cdDesenharTudo();
  cdRestaurarFoco($("mrResumo"), "cat:" + cat);         // devolve o foco ao cartão
}
function odAlternarMapa(cat){ if (mrCategoria === cat) odFecharMapa(); else odAbrirMapa(cat); }
function odImprimirMapa(){
  document.body.classList.add("imp-lista-mapa");
  window.print();
  document.body.classList.remove("imp-lista-mapa");
}
function odLigarEventos(){
  $("mrResumo").addEventListener("click", function(ev){ var b = ev.target.closest(".cd-cartao"); if (b) odAlternarMapa(b.dataset.cat); });
  $("mrBusca").addEventListener("input", function(){ mrBusca = this.value; cdDesenharTudo(); });   // só a tabela é refeita, nunca o campo
  $("mrListaFechar").addEventListener("click", odFecharMapa);
  $("mrListaImp").addEventListener("click", odImprimirMapa);
  $("mrListaCal").addEventListener("click", function(){ cdVerNoCalendario(mrCategoria); });
  $("mrTabela").addEventListener("click", function(ev){ if (!odCliqueAcao(ev)) cdAbrirReservaDe(ev.target, mrDia || cdHoje()); });
  $("mrLista").addEventListener("keydown", function(ev){
    if (ev.key !== "Escape" || (ev.target.id === "mrBusca" && ev.target.value)) return;   // com texto, o Esc limpa a pesquisa (nativo)
    ev.preventDefault(); odFecharMapa();
  });
  window.addEventListener("afterprint", function(){ document.body.classList.remove("imp-lista-mapa"); });
}
if (typeof document !== "undefined") odLigarEventos();
