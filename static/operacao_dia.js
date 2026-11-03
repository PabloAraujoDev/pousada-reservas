"use strict";
/* Operação do dia: as LISTAS dos cartões (Check-ins, Check-outs, Interditados, Ocupados, Vagos).
 *
 * Parte 1 (funções puras, testadas em node: tests/js/operacao_logica.js) e Parte 2 (HTML da tabela, a MESMA para o
 * Calendário e para o painel do Mapa da reserva). A tela do painel do Mapa fica em operacao_dia_tela.js.
 * Usa de calendario_dia.js: cdDataBR, cdNorm, cdHtmlIcone, CD_ROTULO_*; e de app.js: esc.
 *
 * Privacidade: a lista só mostra o que a lista de reservas já traz (nome, grupo, tipo, pessoas, datas, pagamento). Nunca
 * dinheiro, contato nem textos livres. */
if (typeof module !== "undefined" && typeof cdDataBR === "undefined") Object.assign(globalThis, require("./calendario_dia.js"));   // (só no teste em node)

var OD_TITULO = {ins: "Check-ins", outs: "Check-outs", interditados: "Interditados", ocupados: "Ocupados", vagos: "Vagos"};
var OD_VAZIO = {ins: "Nenhum check-in neste dia.", outs: "Nenhum check-out neste dia.", ocupados: "Nenhum apartamento ocupado.",
  interditados: "Nenhum apartamento interditado.", vagos: "Todos os apartamentos estão ocupados."};

/* ---------- Parte 1: lógica pura ---------- */
function odProximaReserva(reservas, apto, dia){     // próxima reserva ativa da unidade com entrada em/depois de dia (ou null)
  var prox = null;
  reservas.forEach(function(r){ if (r.a === apto && r.i >= dia && (!prox || r.i < prox.i)) prox = r; });
  return prox;
}
function odDataCurta(iso, hoje){ return iso === hoje ? "hoje" : cdDataBR(iso).slice(0, 5); }
function odQuandoVaga(saindo, prox, hoje){      // texto da coluna "Quando fica ocupada/livre" de uma unidade vaga
  var t = [];
  if (saindo) t.push("Sai " + saindo.nome + " ao meio-dia: livre a partir das 12h.");
  if (prox) t.push("Livre até " + odDataCurta(prox.i, hoje) + " (próxima: " + prox.nome + ", entra " + odDataCurta(prox.i, hoje) + " 14h).");
  else t.push("Sem próxima reserva.");
  return t.join(" ");
}
function odTitulo(cat, dia, hoje){ return OD_TITULO[cat] + " de " + cdDataBR(dia) + (dia === hoje ? " (hoje)" : " (neste dia)"); }
function odPlural(n, um, varios){ return n + " " + (n === 1 ? um : varios); }
function odContador(linhas, cat){       // "4 apartamentos, 9 pessoas": conta UNIDADES (troca = 2 linhas, 1 unidade)
  var un = {}, pessoas = 0, t;
  linhas.forEach(function(l){ un[l.a] = true; if (l.r) pessoas += l.r.n; });
  var n = Object.keys(un).length;
  t = odPlural(n, "apartamento", "apartamentos");
  return (!cat || cat === "vagos" || cat === "interditados") ? t : t + ", " + odPlural(pessoas, "pessoa", "pessoas");
}
function odVazio(cat, busca){
  if (String(busca || "").trim()) return cat === "vagos" || cat === "interditados" ? "Nenhum apartamento corresponde à busca." : "Nenhuma reserva corresponde à busca.";
  return OD_VAZIO[cat] || "Nenhuma reserva neste dia: nenhuma chegada, saída ou hóspede.";
}
function odTipoLista(cat){ return cat === "vagos" || cat === "interditados" ? "unidade" : "reserva"; }
function odColunas(cat, comAcoes){      // cabeçalhos da tabela, por categoria
  var c = cat === "vagos" || cat === "interditados" ? ["Apto", "Situação", "Quando fica ocupada/livre"]
    : ["Apto", "Reserva", "Hóspede", "Grupo / Tipo", "Pessoas", "Situação", "Entrada", cat === "ocupados" ? "Sai em" : "Saída", "Pagamento"];
  return comAcoes ? ["Ações"].concat(c) : c;
}

/* ---------- Parte 2: HTML da tabela ---------- */
function odHtmlCabecalho(cat, comAcoes){
  var h = "<thead><tr>";
  odColunas(cat, comAcoes).forEach(function(c){ h += '<th scope="col"' + (c === "Ações" ? ' class="od-col-acoes nao-imprimir"' : "") + '>' + esc(c) + '</th>'; });
  return h + "</tr></thead>";
}
function odHtmlApto(l, dia, ctx){
  var r = l.r;
  if (l.tipo === "reserva")
    return '<button type="button" class="cd-apto-btn cd-est-' + esc(l.troca ? "troca" : l.situacao) + '" data-id="' + esc(r.id) + '" data-foco="' + esc("linha:" + r.id + ":" + l.situacao) +
      '" aria-label="' + esc("Abrir a reserva de " + r.nome + ", unidade " + l.a) + '">' + esc(l.a) + '</button>';
  if (l.tipo === "vaga" && ctx.criar && dia >= ctx.hoje)
    return '<button type="button" class="cd-apto-btn cd-est-vaga" data-apto="' + esc(l.a) + '" data-foco="' + esc("vaga:" + l.a) + '" aria-label="' + esc("Nova reserva na unidade " + l.a) + '">' + esc(l.a) + '</button>';
  return '<span class="cd-apto-btn cd-est-' + esc(l.tipo === "vaga" ? "vaga" : "interditada") + '">' + esc(l.a) + '</span>';
}
function odHtmlSituacao(l){
  var h = '<span class="cd-sit cd-sit-' + esc(l.situacao) + '">' + cdHtmlIcone(l.situacao) + esc(CD_ROTULO_SIT[l.situacao]) + '</span>';
  return l.troca ? h + ' <span class="cd-selo">Troca</span>' : h;
}
function odHtmlColunasReserva(l, dia, cat){
  var r = l.r, h = '<td data-r="Reserva">' + esc(r.id) + '</td>';
  h += '<td data-r="Hóspede" class="cd-nome" title="' + esc(r.nome) + '">' + esc(r.nome) + '</td><td data-r="Grupo / Tipo">';
  if (r.grupo) h += '<span class="cd-grupo">Grupo: ' + esc(r.grupo) + '</span> ';
  h += '<span class="suave">' + esc(CD_ROTULO_TIPO[r.tipo] || "-") + '</span></td><td data-r="Pessoas">' + esc(r.n) + '</td>';
  h += '<td data-r="Situação">' + odHtmlSituacao(l) + '</td><td data-r="Entrada" class="' + esc(r.i === dia ? "cd-dia-igual" : "") + '">' + esc(cdDataBR(r.i)) + '</td>';
  h += '<td data-r="' + esc(cat === "ocupados" ? "Sai em" : "Saída") + '" class="' + esc(r.f === dia ? "cd-dia-igual" : "") + '">' + esc(cdDataBR(r.f) + (cat === "ocupados" ? " 12h" : "")) + '</td>';
  return h + '<td data-r="Pagamento"><span class="pilula ' + esc(r.p) + '">' + esc(CD_ROTULO_PAG[r.p] || r.p) + '</span></td>';
}
function odHtmlColunasUnidade(l, ctx){
  var quando = l.tipo === "vaga" ? odQuandoVaga(l.saindo, odProximaReserva(ctx.reservas, l.a, ctx.dia), ctx.hoje) : "Fora de venda (sem previsão).";
  var h = '<td data-r="Situação">' + odHtmlSituacao({situacao: l.situacao, troca: false}) + '</td>';
  h += '<td data-r="Quando" class="suave od-quando">' + esc(quando);
  if (l.tipo === "vaga" && ctx.criar && ctx.dia >= ctx.hoje)
    h += ' <button type="button" class="od-nova" data-apto="' + esc(l.a) + '" data-foco="' + esc("nova:" + l.a) + '">Nova reserva</button>';
  return h + '</td>';
}
function odHtmlCelulaAcoes(ctx, l){      // a coluna Ações é montada por operacao_acoes.js (ctx.acoes devolve HTML já protegido)
  return '<td data-r="Ações" class="od-col-acoes nao-imprimir">'.concat(ctx.acoes(l), '</td>');    // o HTML dos botões vem pronto (odHtmlAcoes, com esc())
}
function odHtmlLinha(l, dia, cat, ctx){
  var h = '<tr class="cd-linha">';
  if (ctx.acoes) h += odHtmlCelulaAcoes(ctx, l);
  h += '<td data-r="Apto">' + odHtmlApto(l, dia, ctx) + '</td>';
  h += l.tipo === "reserva" ? odHtmlColunasReserva(l, dia, cat) : odHtmlColunasUnidade(l, Object.assign({dia: dia}, ctx));
  return h + '</tr>';
}
/* A tabela das listas. ctx = {criar, hoje, reservas, vazio, legenda, acoes(l) -> html | null}. Mantém os blocos da visão padrão do dia. */
function odHtmlTabela(linhas, dia, cat, ctx){
  var h = '<caption class="so-leitor">' + esc(ctx.legenda || "Lista do dia") + '</caption>' + odHtmlCabecalho(cat, !!ctx.acoes) + "<tbody>", atual = null, cont = {}, ehHoje = dia === ctx.hoje;
  var colunas = odColunas(cat, !!ctx.acoes).length;
  linhas.forEach(function(l){ if (l.bloco) cont[l.bloco] = (cont[l.bloco] || 0) + 1; });
  linhas.forEach(function(l){
    if (l.bloco && l.bloco !== atual){
      atual = l.bloco;
      h += '<tr class="cd-bloco-tit"><th scope="colgroup" colspan="' + esc(colunas) + '">' + esc(cdRotuloBloco(l.bloco, ehHoje) + " (" + cont[l.bloco] + ")") + '</th></tr>';
    }
    h += odHtmlLinha(l, dia, cat, ctx);
  });
  if (!linhas.length) h += '<tr><td colspan="' + esc(colunas) + '" class="suave cd-vazio">' + esc(ctx.vazio) + '</td></tr>';
  return h + "</tbody>";
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {odProximaReserva: odProximaReserva, odQuandoVaga: odQuandoVaga, odTitulo: odTitulo, odContador: odContador,
    odVazio: odVazio, odColunas: odColunas, odPlural: odPlural, odTipoLista: odTipoLista};
}
