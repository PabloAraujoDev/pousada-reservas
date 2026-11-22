"use strict";
// Testa static/catalogo_logica.js. Roda com: node tests/js/catalogo_logica.js
const assert = require("assert");
const path = require("path");
const C = require(path.join(__dirname, "..", "..", "static", "catalogo_logica.js"));
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);

caso("formulário do item", () => {
  const f = {categoria: "bebidas", grupo: " Águas ", descricao: " Água com gás ", preco: "5,00"};
  assert.deepStrictEqual(C.cgConferirItem(f).dados, {categoria: "bebidas", grupo: "Águas", descricao: "Água com gás", preco_centavos: 500});
  for (const ruim of [{categoria: ""}, {descricao: "a"}, {descricao: "x".repeat(81)}, {grupo: "a"}, {grupo: "x".repeat(41)},
                      {preco: ""}, {preco: "0"}, {preco: "10.000,01"}, {preco: "-1"}, {preco: "abc"}])
    assert.ok(C.cgConferirItem(Object.assign({}, f, ruim)).erro, JSON.stringify(ruim));
  assert.strictEqual(C.cgConferirItem(Object.assign({}, f, {grupo: ""})).dados.grupo, "");
});
caso("texto do log", () => {
  const t = C.cgTextoLog({acao: "editado", por: "admin", em: "2026-10-29 09:05:12",
    antes: {descricao: "A", preco_centavos: 500, ativo: 1}, depois: {descricao: "A", preco_centavos: 700, ativo: 1}});
  assert.strictEqual(t, "Editado por admin em 29/10 09:05:12: valor: R$ 5,00 -> R$ 7,00");
  assert.match(C.cgTextoLog({acao: "criado", por: "x", em: "2026-10-29 09:05:12", antes: null, depois: {descricao: "Água", preco_centavos: 400}}), /Cadastrado.*descrição: Água; valor: R\$ 4,00/);
});
caso("observação e período do relatório", () => {
  assert.strictEqual(C.cnObservacao({tipo: "lancamento", item_id: 3}), "");
  assert.strictEqual(C.cnObservacao({tipo: "lancamento", item_id: null}), "Avulso/antigo");
  assert.strictEqual(C.cnObservacao({tipo: "estorno", motivo: "errado", item_id: 3}), "Estorno: errado");
  assert.strictEqual(C.cnObservacao({tipo: "estorno", transferencia_id: 1}), "Transferido para outra conta");
  assert.strictEqual(C.cnPeriodoValido("2026-10-01", "2026-10-31"), "");
  assert.ok(C.cnPeriodoValido("2026-10-31", "2026-10-01") && C.cnPeriodoValido("", "") && C.cnPeriodoValido("2026-01-01", "2026-12-31"));
});

let falhas = 0;
casos.forEach(([n, f]) => { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } });
if (falhas) process.exit(1);
console.log("catalogo_logica: " + casos.length + " casos ok");
