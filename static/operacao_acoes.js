"use strict";
/* Operação do dia: a coluna AÇÕES das listas (Calendário e painel do Mapa): Despesas, Informações, Observações.
 *
 * Quem vê cada botão (botões sem permissão nem entram no HTML; o servidor continua sendo a barreira):
 *   Informações e Observações: reservas.ver (a camareira não tem, então nunca vê a coluna; consulta vê só estes dois).
 *   Despesas: despesas.ver (o módulo está em despesas.js: odAbrirDespesas). Vagas e interditadas nunca têm Despesas.
 * Indicadores: só um ponto (booleano) nos botões Observações e Despesas (tem_despesa, vindo do servidor só para despesas.ver);
 * nunca valores. */
if (typeof module !== "undefined" && typeof esc === "undefined") globalThis.esc = function(s){ return String(s); };

var OD_DESPESAS_LIGADO = true;
var OD_ICONES = {     // desenhos simples próprios (24x24)
  despesas: "M3 6h18v12H3V6zm9 2.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  info: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z",
  obs: "M4 4h16v12H8l-4 4V4zm4 4v2h8V8H8zm0 3v2h5v-2H8z"
};
var OD_ROTULO_ACAO = {despesas: "Despesas", info: "Informações", obs: "Observações"};
var OD_CURTO_ACAO = {despesas: "Despesas", info: "Dados", obs: "Notas"};      // rótulo curto (celular)

/* ---------- lógica pura ---------- */
function odTemNota(r){ return !!r && (r.tem_nota === true || (typeof r.o === "string" && r.o.trim() !== "") || (typeof r.extras === "string" && r.extras.trim() !== "")); }   // tem_nota: notas com autor (servidor)
function odAcoesDisponiveis(tipo, p, despesasLigado){      // tipo: reserva|vaga|interditada; p: {despesas, ver, governanca, temNota}
  var a = [], ligado = despesasLigado === undefined ? OD_DESPESAS_LIGADO : despesasLigado;
  if (!p.ver) return a;                     // sem reservas.ver (camareira) não há coluna nenhuma
  if (tipo === "reserva" && ligado && p.despesas) a.push("despesas");
  if (p.ver) a.push("info");
  if (p.ver && (tipo === "reserva" || (p.governanca && p.temNota))) a.push("obs");   // unidade sem texto na governança: sem botão
  return a;
}
function odRotuloAcao(acao, l){
  var alvo = l.tipo === "reserva" ? "do apartamento " + l.a + ", hóspede " + l.r.nome : "da unidade " + l.a;
  return OD_ROTULO_ACAO[acao] + " " + alvo + (acao === "obs" && l.temNota ? " (há observações)" : "") + (acao === "despesas" && l.r && l.r.tem_despesa ? " (há lançamentos)" : "");
}
function odAssinaturaNotas(){      // entra na assinatura do redesenho: só booleanos, nunca o texto
  var gov = typeof cdGov === "undefined" ? {} : cdGov;
  return (typeof reservas === "undefined" ? [] : reservas).map(function(r){ return (odTemNota(r) ? 1 : 0) + (r.tem_despesa ? "d" : ""); }).join("") + Object.keys(gov).filter(function(u){ return gov[u].nota; }).join(",");
}

/* ---------- HTML ---------- */
function odHtmlIconeAcao(acao){
  return '<svg class="od-ico" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="' + esc(OD_ICONES[acao]) + '"/></svg>';
}
function odHtmlBotaoAcao(acao, l, dia){
  var chave = "acao:" + acao + ":" + (l.r ? l.r.id : l.a);
  var h = '<button type="button" class="od-acao od-acao-' + esc(acao) + '" data-acao="' + esc(acao) + '" data-rid="' + esc(l.r ? l.r.id : "") + '" data-un="' + esc(l.a) + '" data-dia="' + esc(dia);
  h += '" data-sit="' + esc(l.situacao) + '" data-troca="' + esc(l.troca ? "sim" : "nao") + '" data-foco="' + esc(chave) + '" aria-label="' + esc(odRotuloAcao(acao, l)) + '" title="' + esc(OD_ROTULO_ACAO[acao]) + '">';
  h += odHtmlIconeAcao(acao) + '<span class="od-acao-rot"><span class="od-rot-longo">' + esc(OD_ROTULO_ACAO[acao]) + '</span><span class="od-rot-curto">' + esc(OD_CURTO_ACAO[acao]) + '</span></span>';
  if ((acao === "obs" && l.temNota) || (acao === "despesas" && l.r && l.r.tem_despesa)) h += '<span class="od-ponto" aria-hidden="true"></span>';
  return h + '</button>';
}
function odHtmlAcoes(l, dia){     // o conteúdo da célula Ações (vazio se o perfil não pode nada)
  var temNota = l.tipo === "reserva" ? odTemNota(l.r) : !!(typeof cdGov !== "undefined" && cdGov[l.a] && cdGov[l.a].nota);
  var linha = Object.assign({}, l, {temNota: temNota});
  var p = {despesas: pode("despesas.ver"), ver: pode("reservas.ver"), governanca: pode("governanca.ver"), temNota: temNota};
  return '<div class="od-acoes">'.concat(odAcoesDisponiveis(l.tipo, p).map(function(a){ return odHtmlBotaoAcao(a, linha, dia); }).join(""), '</div>');
}
/* Clique num botão da coluna Ações (chamado pelos dois eventos de tabela). Devolve true se tratou o clique. */
function odCliqueAcao(ev){
  var b = ev.target.closest("[data-acao]");
  if (!b) return false;
  if (b.dataset.acao === "despesas") { if (typeof odAbrirDespesas === "function") odAbrirDespesas(b); }
  else odAbrirDialogo(b);          // operacao_dialogos.js
  return true;
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {odTemNota: odTemNota, odAcoesDisponiveis: odAcoesDisponiveis, odRotuloAcao: odRotuloAcao};
}
