"use strict";
// Funções puras de static/ocupacao_logica.js (sem navegador). Roda com: node tests/js/ocupacao_logica.js
const assert = require("assert");
const path = require("path");
const O = require(path.join(__dirname, "..", "..", "static", "ocupacao_logica.js"));
const casos = [];
const caso = (n, f) => casos.push([n, f]);

caso("atalhos de período", () => {
  assert.deepStrictEqual(O.ocPeriodo("hoje", "2026-10-29", null), {inicio: "2026-10-29", fim: "2026-10-29"});
  assert.deepStrictEqual(O.ocPeriodo("semana", "2026-10-29", null), {inicio: "2026-10-26", fim: "2026-11-01"});   // quinta -> seg..dom
  assert.deepStrictEqual(O.ocPeriodo("semana", "2026-11-01", null), {inicio: "2026-10-26", fim: "2026-11-01"});   // domingo fecha a semana
  assert.deepStrictEqual(O.ocPeriodo("mes", "2026-02-10", null), {inicio: "2026-02-01", fim: "2026-02-28"});
  assert.deepStrictEqual(O.ocPeriodo("mes", "2028-02-10", null), {inicio: "2028-02-01", fim: "2028-02-29"});
  assert.deepStrictEqual(O.ocPeriodo("proximo", "2026-12-15", null), {inicio: "2027-01-01", fim: "2027-01-31"});   // vira o ano
  assert.deepStrictEqual(O.ocPeriodo("mapa", "2026-10-29", {inicio: "2026-12-28", dias: 14}), {inicio: "2026-12-28", fim: "2027-01-10"});
});
caso("validação do período", () => {
  assert.strictEqual(O.ocValidar("2026-10-01", "2026-10-01").dias, 1);
  assert.strictEqual(O.ocValidar("2026-10-01", "2026-12-31").dias, 92);
  assert.ok(/máximo de 92/.test(O.ocValidar("2026-10-01", "2027-01-01").erro));
  assert.ok(/igual ou depois/.test(O.ocValidar("2026-10-02", "2026-10-01").erro));
  for (const [a, b] of [["", ""], ["2026-02-30", "2026-03-01"], ["2026-10-1", "2026-10-02"], ["abc", "2026-10-02"], ["2019-12-31", "2020-01-02"], ["2026-10-01", "2101-01-01"]])
    assert.ok(O.ocValidar(a, b).erro, a + " " + b);
});
caso("dias entre datas na virada de horário de verão/ano", () => {
  assert.strictEqual(O.ocDiasEntre("2026-12-30", "2027-01-02"), 4);
  assert.strictEqual(O.ocSoma("2026-12-31", 1), "2027-01-01");
});
caso("percentual em pt-BR", () => {
  assert.strictEqual(O.ocPct(50), "50%"); assert.strictEqual(O.ocPct(72.5), "72,5%"); assert.strictEqual(O.ocPct(0), "0%"); assert.strictEqual(O.ocPct(4.2), "4,2%");
});
caso("url com escape e orientação segura", () => {
  assert.strictEqual(O.ocUrl("/api/ocupacao", "2026-10-01", "2026-10-02", "retrato"), "/api/ocupacao?inicio=2026-10-01&fim=2026-10-02&orientacao=retrato");
  assert.ok(O.ocUrl("/x", "a&b=1", "c#", "<script>").endsWith("orientacao=paisagem"));
  assert.ok(!/[&=#]/.test(O.ocUrl("/x", "a&b=1", "c#", "").split("?")[1].split("&")[0].slice(7)));
});
const XSS = '<img src=x onerror="window.__xss=1">';
const rel = (nomes) => ({inicio: "2026-10-10", fim: "2026-10-11", com_nomes: nomes, emitido_por: XSS, orientacao: "paisagem",
  resumo: {dias: 2, reservaveis: 24, noites_ocupadas: 2, noites_disponiveis: 48, ocupacao_media: 4.2, pico: {data: "2026-10-10", ocupadas: 1, pct: 4.2}, entradas: 1, saidas: 0, pessoas_noites: 4},
  blocos: [{dias: ["2026-10-10", "2026-10-11"], totais: [{ocupadas: 1, livres: 23, pct: 4.2, entradas: 1, saidas: 0, pessoas: 2}, {ocupadas: 1, livres: 23, pct: 4.2, entradas: 0, saidas: 0, pessoas: 2}],
    linhas: [{a: "104", interditada: true, celulas: []},
      {a: "201", interditada: false, celulas: [{col: 0, span: 2, antes: false, depois: true, n: 2, nome: XSS, grupo: ""}]},
      {a: XSS, interditada: false, celulas: []}]}]});
caso("HTML da impressão escapa tudo que vem do servidor", () => {
  const h = O.ocHtml(rel(true), "02/11/2026 10:00");
  assert.ok(!h.includes("<img"), "tag crua vazou");
  assert.ok(h.includes("&lt;img src=x onerror=&quot;window.__xss=1&quot;&gt;"));
  assert.ok(h.includes('colspan="2"') && h.includes("&raquo;") === false && h.includes("»"));
  assert.ok(h.includes("Interditada") && h.includes("Emitido em 02/11/2026 10:00 por"));
  assert.ok(h.includes("Ocupação %") && h.includes("4,2%") && h.includes("Check-ins") && h.includes("Check-outs"));
});
caso("sem nomes mostra só Ocupada", () => {
  const h = O.ocHtml(rel(false), "x");
  assert.ok(h.includes("Ocupada (2) »") && !h.includes("Hóspede"));
});
caso("uma seção por bloco, resumo só na primeira", () => {
  const r = rel(true); r.blocos.push(JSON.parse(JSON.stringify(r.blocos[0])));
  const h = O.ocHtml(r, "x");
  assert.strictEqual((h.match(/<section class="oc-pagina">/g) || []).length, 2);
  assert.strictEqual((h.match(/Resumo do período/g) || []).length, 1);
  assert.strictEqual((h.match(/Legenda/g) || []).length, 1);
});
caso("cada linha fecha as colunas do bloco", () => {
  const h = O.ocHtml(rel(true), "x");
  const linha = h.split("<tr>").find((t) => t.includes("<th scope=\"row\">201"));
  const tds = (linha.match(/<td/g) || []).length, span = +/colspan="(\d+)"/.exec(linha)[1];
  assert.strictEqual(tds, 1); assert.strictEqual(span, 2);
});
let falhas = 0;
for (const [n, f] of casos) { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } }
console.log((casos.length - falhas) + "/" + casos.length + " casos ok");
process.exit(falhas ? 1 : 0);
