"use strict";
// Lógica pura de static/importar_cancel.js (sem navegador). Roda com: node tests/js/importar_cancel.js
const assert = require("assert");
const path = require("path");
const I = require(path.join(__dirname, "..", "..", "static", "importar_cancel.js"));
const casos = [];
const caso = (n, f) => casos.push([n, f]);

const canc = () => ({propostas: [
  {id: 1, versao: 1, origem: "planilha", selo: "s1", selo_em: 1700000000, confianca: "alta", marcada: true, bloqueio: "", apto: "201", nome: "<b>Ana</b>", entrada: "2026-11-05", saida: "2026-11-07", aba: "BOA NOVEMBRO", linha: 9, texto: "x <img>", motivo: "m"},
  {id: 2, versao: 3, origem: "planilha", confianca: "media", marcada: false, bloqueio: "", apto: "202", nome: "Bruno", entrada: "2026-11-10", saida: "2026-11-12", aba: "BOA NOVEMBRO", linha: 10, texto: "", motivo: "m"},
  {id: 3, versao: 1, origem: "sumiu", confianca: "sumiu", marcada: true, bloqueio: "O check-in já foi feito", apto: "203", nome: "Carla", entrada: "2026-11-15", saida: "2026-11-18", aba: "", linha: null, texto: "", motivo: ""}],
  nao_encontradas: [{linha: 4, unidade: "204", hospede: "<script>", entrada: null, saida: null}], nao_identificadas: [{linha: 5, texto: "\"><x>", motivo: "m"}]});
const linha = (o) => Object.assign({st: "ok", incluir: true, aba: "A", linha: 1, hospede: "N", extras: ["e1", "e2"], n: 2, entrada: "2026-11-01", saida: "2026-11-02",
  pagamento: "pendente", texto_pagamento: "", grupo: "", apto: "205"}, o);

caso("marcadas: só as marcadas e não bloqueadas", () => {
  assert.deepStrictEqual(Object.keys(I.icMarcadas(canc())), ["1"]);
});
caso("dependência: nova só entra com o cancelamento marcado", () => {
  const c = canc();
  assert.strictEqual(I.icDepsOk(linha({depende_de: [1]}), c), true);
  assert.strictEqual(I.icDepsOk(linha({depende_de: [2]}), c), false);
  assert.strictEqual(I.icDepsOk(linha({depende_de: [3]}), c), false);      // bloqueada nunca conta
  assert.strictEqual(I.icDepsOk(linha({}), c), true);
});
caso("corpo do pedido: novas, atualizações e cancelamentos marcados", () => {
  const c = canc();
  const ls = [linha({}), linha({depende_de: [2]}), linha({st: "atualizacao", atualizacao: {id: 7, versao: 4}}), linha({incluir: false}), linha({st: "erro"})];
  const b = I.icCorpo(ls, c, "a.xlsx", [], "h");
  assert.strictEqual(b.linhas.length, 1);
  assert.strictEqual(b.linhas[0].a, "205"); assert.strictEqual(b.linhas[0].extras, "e1\ne2");
  assert.deepStrictEqual(b.atualizacoes.map((x) => [x.id, x.versao]), [[7, 4]]);
  assert.strictEqual(I.icCorpo([linha({st: "atualizacao", atualizacao: {id: 7, versao: 4, selo: "ab"}})], c, "a", [], "h").atualizacoes[0].selo, "ab");
  assert.deepStrictEqual(b.cancelamentos, [{id: 1, versao: 1, origem: "planilha", aba: "BOA NOVEMBRO", linha: 9, selo: "s1", selo_em: 1700000000}]);
});
caso("HTML escapa todo texto da planilha e bloqueada fica desabilitada", () => {
  const h = I.icHtml(canc());
  assert.ok(!h.includes("<b>Ana") && !h.includes("<img>") && !h.includes("<script>") && !h.includes('"><x>'));
  assert.ok(h.includes("&lt;b&gt;Ana"));
  assert.strictEqual((h.match(/impCancChk/g) || []).length, 3);
  assert.strictEqual((h.match(/ checked/g) || []).length, 1);
  assert.strictEqual((h.match(/ disabled/g) || []).length, 1);
  assert.ok(h.includes("Bloqueada: O check-in"));
  assert.strictEqual(I.icHtml(null), ""); assert.strictEqual(I.icHtml({propostas: [], nao_encontradas: [], nao_identificadas: []}), "");
});
caso("diferenças e rótulo do botão", () => {
  assert.ok(I.icDifHtml([{rotulo: "Pessoas", antes: "3", depois: "<5>"}]).includes("&lt;5&gt;"));
  assert.strictEqual(I.icRotuloBotao(1, 0, 0), "Importar 1 reserva");
  assert.strictEqual(I.icRotuloBotao(3, 1, 2), "Importar 3 reservas, atualizar 1 e cancelar 2");
});
caso("cada caixa de cancelar tem rótulo próprio (nome, apto e datas), escapado", () => {
  const h = I.icHtml(canc());
  assert.ok(h.includes('aria-label="Cancelar a reserva de &lt;b&gt;Ana&lt;/b&gt;, 201, 05/11 a 07/11"'));
  assert.ok(!h.includes('aria-label="Cancelar esta reserva"'));
});
caso("aviso de planilha cortada (muitas sumiram) e de seção truncada", () => {
  const c = canc(); c.aviso_massa = [{mes: "2026-11", sumiram: 6, total: 8}]; c.truncado = true;
  const h = I.icHtml(c);
  assert.ok(h.includes("6 de 8 reservas de 11/2026") && h.includes("desmarcadas"));
  assert.ok(h.includes("só as primeiras 500"));
  assert.ok(!I.icHtml(canc()).includes("Atenção"));
});
let falhas = 0;
for (const [n, f] of casos) { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } }
console.log((casos.length - falhas) + "/" + casos.length + " casos ok");
process.exit(falhas ? 1 : 0);
