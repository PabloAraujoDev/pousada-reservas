"use strict";
/* Relatório de ocupação: lógica PURA (sem DOM, sem rede; testada em node). O servidor calcula tudo (pousada/ocupacao.py);
 * aqui só se escolhe o período, se confere o formulário e se monta o HTML da folha de impressão. Todo texto vindo do
 * servidor passa por ocEsc (mesmo escape do esc() do app.js). */

var OC_MAX_DIAS = 92;
var OC_SEM = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

function ocEsc(s){
  return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; });
}
function ocData(s){                       // "AAAA-MM-DD" real -> Date UTC; senão null
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
  if (!m) return null;
  var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.toISOString().slice(0, 10) === s ? d : null;
}
function ocSoma(s, n){ var d = ocData(s); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
function ocBR(s){ return s.slice(8) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4); }
function ocDiasEntre(a, b){ return Math.round((ocData(b) - ocData(a)) / 86400000) + 1; }
function ocPct(v){ var t = (Math.round(v * 10) / 10).toFixed(1).replace(".", ","); return (t.slice(-2) === ",0" ? t.slice(0, -2) : t) + "%"; }

/* Atalhos do diálogo. hoje = "AAAA-MM-DD"; mapa = {inicio, dias} do que o Mapa mostra. */
function ocPeriodo(atalho, hoje, mapa){
  var d = ocData(hoje), a, b;
  if (atalho === "hoje") return {inicio: hoje, fim: hoje};
  if (atalho === "semana"){ a = ocSoma(hoje, -((d.getUTCDay() + 6) % 7)); return {inicio: a, fim: ocSoma(a, 6)}; }
  if (atalho === "mes" || atalho === "proximo"){
    var ano = d.getUTCFullYear(), mes = d.getUTCMonth() + (atalho === "proximo" ? 1 : 0);
    a = new Date(Date.UTC(ano, mes, 1)); b = new Date(Date.UTC(ano, mes + 1, 0));
    return {inicio: a.toISOString().slice(0, 10), fim: b.toISOString().slice(0, 10)};
  }
  return {inicio: mapa.inicio, fim: ocSoma(mapa.inicio, mapa.dias - 1)};     // "mapa"
}

/* Confere as duas datas do formulário. Devolve {erro: texto|null, dias: n|0}. */
function ocValidar(inicio, fim){
  if (!ocData(inicio) || !ocData(fim)) return {erro: "Informe as duas datas (início e fim).", dias: 0};
  if (+inicio.slice(0, 4) < 2020 || +fim.slice(0, 4) > 2100 || +fim.slice(0, 4) < 2020 || +inicio.slice(0, 4) > 2100)
    return {erro: "O ano das datas deve estar entre 2020 e 2100.", dias: 0};
  if (fim < inicio) return {erro: "A data final deve ser igual ou depois da inicial.", dias: 0};
  var n = ocDiasEntre(inicio, fim);
  if (n > OC_MAX_DIAS) return {erro: "Período grande demais: máximo de " + OC_MAX_DIAS + " dias (você escolheu " + n + ").", dias: 0};
  return {erro: null, dias: n};
}
function ocUrl(base, inicio, fim, orientacao){
  return base + "?inicio=" + encodeURIComponent(inicio) + "&fim=" + encodeURIComponent(fim) + "&orientacao=" + (orientacao === "retrato" ? "retrato" : "paisagem");
}

/* ---------- HTML da folha de impressão ---------- */
function ocTextoCelula(c, comNomes){
  var base = comNomes ? (c.grupo || c.nome) : "Ocupada";
  return (c.antes ? "« " : "") + base + " (" + c.n + ")" + (c.depois ? " »" : "");
}
function ocLinha(u, n, comNomes){
  if (u.interditada) return '<tr><th scope="row">' + ocEsc(u.a) + '</th><td colspan="' + n + '" class="oc-int">Interditada (fora de venda)</td></tr>';
  var h = '<tr><th scope="row">' + ocEsc(u.a) + '</th>', col = 0, k = 0;
  while (col < n){
    var c = u.celulas[k];
    if (c && c.col === col){
      h += '<td colspan="' + c.span + '" class="oc-ocup"><span>' + ocEsc(ocTextoCelula(c, comNomes)) + '</span></td>';
      col += c.span; k++;
    } else { h += '<td></td>'; col++; }
  }
  return h + '</tr>';
}
var OC_TOTAIS = [["ocupadas", "Ocupadas"], ["livres", "Livres"], ["pct", "Ocupação %"], ["entradas", "Check-ins"], ["saidas", "Check-outs"], ["pessoas", "Pessoas"]];
function ocGrade(b, comNomes){
  var n = b.dias.length, h = '<table class="oc-grade"><thead><tr><th scope="col">Unidade</th>';
  b.dias.forEach(function(d){
    var w = ocData(d).getUTCDay();
    h += '<th scope="col" class="' + (w === 0 || w === 6 ? "oc-fds" : "") + '">' + OC_SEM[w] + '<br>' + ocEsc(d.slice(8) + "/" + d.slice(5, 7)) + '</th>';
  });
  h += '</tr></thead><tbody>';
  b.linhas.forEach(function(u){ h += ocLinha(u, n, comNomes); });
  OC_TOTAIS.forEach(function(par, k){
    h += '<tr class="oc-tot' + (k === 0 ? " oc-tot-ini" : "") + '"><th scope="row">' + par[1] + '</th>';
    b.totais.forEach(function(t){ h += '<td>' + ocEsc(par[0] === "pct" ? ocPct(t.pct) : t[par[0]]) + '</td>'; });
    h += '</tr>';
  });
  return h + '</tbody></table>';
}
function ocResumo(r){
  return '<p class="oc-resumo"><b>Resumo do período</b> (' + ocEsc(r.dias) + ' dias, ' + ocEsc(r.reservaveis) + ' unidades reserváveis): ocupação média <b>' +
    ocEsc(ocPct(r.ocupacao_media)) + '</b>; diárias ocupadas <b>' + ocEsc(r.noites_ocupadas) + '</b> de ' + ocEsc(r.noites_disponiveis) +
    '; pico <b>' + ocEsc(r.pico.ocupadas) + ' unidades (' + ocEsc(ocPct(r.pico.pct)) + ')</b> em ' + ocEsc(ocBR(r.pico.data)) +
    '; check-ins ' + ocEsc(r.entradas) + '; check-outs ' + ocEsc(r.saidas) + '; pessoas-noite ' + ocEsc(r.pessoas_noites) + '.</p>';
}
var OC_LEGENDA = '<p class="oc-legenda"><b>Legenda:</b> célula marcada = unidade ocupada na noite do dia (grupo ou hóspede e nº de pessoas); « continua do período anterior, » continua depois; ' +
  'cinza = unidade interditada (fora do cálculo); vazio = livre. Saída e entrada no mesmo dia na mesma unidade é permitida.</p>';

/* emitido = "dd/mm/aaaa hh:mm" (relógio do navegador). Uma <section> por bloco = uma página impressa. */
function ocHtml(rel, emitido){
  var h = "";
  rel.blocos.forEach(function(b, k){
    h += '<section class="oc-pagina"><div class="oc-cab"><p class="oc-pousada">Pousada Boa Esperança</p><p class="oc-titulo">Relatório de ocupação - ' +
      ocEsc(ocBR(rel.inicio)) + ' a ' + ocEsc(ocBR(rel.fim)) + '</p><p class="oc-emitido">Emitido em ' + ocEsc(emitido) + ' por ' + ocEsc(rel.emitido_por) + '</p></div>';
    if (k === 0) h += ocResumo(rel.resumo) + OC_LEGENDA;
    h += ocGrade(b, rel.com_nomes) + '</section>';
  });
  return h;
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {ocPeriodo: ocPeriodo, ocValidar: ocValidar, ocUrl: ocUrl, ocHtml: ocHtml, ocPct: ocPct, ocEsc: ocEsc, ocSoma: ocSoma,
    ocDiasEntre: ocDiasEntre, OC_MAX_DIAS: OC_MAX_DIAS};
}
