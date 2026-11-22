"use strict";
// Testa a lógica pura de static/despesas_logica.js. Roda com: node tests/js/despesas_logica.js
const assert = require("assert");
const path = require("path");
const D = require(path.join(__dirname, "..", "..", "static", "despesas_logica.js"));
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);

caso("parser de reais: formas aceitas", () => {
  const ok = {"8": 800, "8,5": 850, "8,50": 850, "8.50": 850, "0,05": 5, "0,5": 50, "R$ 8,00": 800, "r$8": 800,
              "1.234,56": 123456, "1.234": 123400, "10000": 1000000, "10.000,00": 1000000, " 12,5 ": 1250, "1.050,00": 105000};
  for (const [t, c] of Object.entries(ok)) assert.strictEqual(D.dsParseReais(t), c, t);
});
caso("parser de reais: recusas", () => {
  for (const t of ["", "  ", "abc", "-5", "8,555", "8,", ",5", "1,2,3", "1..2", "12a", "R$", "8e2", "1.2345,00", null, undefined, "99999999"])
    assert.strictEqual(D.dsParseReais(t), null, String(t));
});
caso("parser nunca devolve float", () => {
  for (const t of ["0,07", "19,99", "1.234,56", "8.07"]) assert.ok(Number.isInteger(D.dsParseReais(t)), t);
  assert.strictEqual(D.dsParseReais("0,07"), 7);                      // 0.07 * 100 daria 7.000000000000001
  assert.strictEqual(D.dsParseReais("19,99") * 3, 5997);
});
caso("formatador", () => {
  assert.strictEqual(D.dsFormatarReais(0), "R$ 0,00");
  assert.strictEqual(D.dsFormatarReais(5), "R$ 0,05");
  assert.strictEqual(D.dsFormatarReais(800), "R$ 8,00");
  assert.strictEqual(D.dsFormatarReais(113750), "R$ 1.137,50");
  assert.strictEqual(D.dsFormatarReais(100000000), "R$ 1.000.000,00");
  assert.strictEqual(D.dsFormatarReais(-1600), "-R$ 16,00");
});
caso("ida e volta: formatar e ler dá o mesmo número", () => {
  for (const c of [1, 99, 100, 101, 12345, 999999, 1000000]) assert.strictEqual(D.dsParseReais(D.dsFormatarReais(c)), c);
});
caso("quantidade", () => {
  assert.strictEqual(D.dsParseQuantidade("2"), 2);
  assert.strictEqual(D.dsParseQuantidade(" 99 "), 99);
  for (const t of ["0", "100", "1,5", "-1", "", "x", "1e1"]) assert.strictEqual(D.dsParseQuantidade(t), null, t);
});
caso("formulário: caminho feliz, total e recusas", () => {
  const f = {categoria: "bar", descricao: "  Água 500ml ", quantidade: "2", valor: "8,00"};
  const r = D.dsConferirFormulario(f);
  assert.deepStrictEqual(r.dados, {categoria: "bar", descricao: "Água 500ml", quantidade: 2, valor_unit_centavos: 800});
  assert.strictEqual(r.total, 1600);
  assert.ok(D.dsConferirFormulario(Object.assign({}, f, {descricao: "a"})).erro);
  assert.ok(D.dsConferirFormulario(Object.assign({}, f, {descricao: "x".repeat(81)})).erro);
  assert.ok(D.dsConferirFormulario(Object.assign({}, f, {quantidade: "0"})).erro);
  assert.ok(D.dsConferirFormulario(Object.assign({}, f, {valor: ""})).erro);
  assert.ok(D.dsConferirFormulario(Object.assign({}, f, {valor: "0"})).erro);
  assert.match(D.dsConferirFormulario(Object.assign({}, f, {valor: "10.000,01"})).erro, /R\$ 10\.000,00/);
  assert.ok(D.dsConferirFormulario(Object.assign({}, f, {valor: "10.000,00"})).dados);
});
caso("motivo", () => {
  assert.ok(D.dsConferirMotivo("erro").erro);
  assert.strictEqual(D.dsConferirMotivo("  digitado errado ").motivo, "digitado errado");
  assert.ok(D.dsConferirMotivo("x".repeat(141)).erro);
});
caso("chave: 8 a 64 caracteres e diferente a cada vez", () => {
  const a = D.dsNovaChave(), b = D.dsNovaChave();
  assert.ok(a.length >= 8 && a.length <= 64 && /^[0-9a-f-]+$/.test(a));
  assert.notStrictEqual(a, b);
});
caso("data e hora, categoria, situação da linha", () => {
  assert.strictEqual(D.dsDataHora("2026-10-29 09:05:33"), "29/10 09:05");
  assert.strictEqual(D.dsRotuloCategoria("bar"), "Bar / frigobar");
  assert.strictEqual(D.dsSituacaoLinha({tipo: "estorno"}), "estorno");
  assert.strictEqual(D.dsSituacaoLinha({tipo: "lancamento", estornado: true}), "estornado");
  assert.strictEqual(D.dsSituacaoLinha({tipo: "lancamento", estornado: false}), "normal");
});
caso("mensagens de erro", () => {
  assert.strictEqual(D.dsMensagemErro(403, "x", "lancar"), "Seu perfil não pode lançar despesas.");
  assert.strictEqual(D.dsMensagemErro(403, "x", "estornar"), "Seu perfil não pode estornar lançamentos.");
  assert.strictEqual(D.dsMensagemErro(409, "A conta já foi fechada."), "A conta já foi fechada.");
  assert.ok(D.dsMensagemErro(500, ""));
});
caso("totais: com diária, sem diária, sem permissão de valores", () => {
  assert.deepStrictEqual(D.dsLinhasTotais({despesas_centavos: 8750, noites: 3, diaria_centavos: 35000, diarias_centavos: 105000, estadia_centavos: 113750}),
    [["Diárias", "R$ 350,00 x 3 noites = R$ 1.050,00"], ["Despesas", "R$ 87,50"], ["Total da estadia", "R$ 1.137,50"]]);
  assert.deepStrictEqual(D.dsLinhasTotais({despesas_centavos: 8750, noites: 3, diaria_centavos: null}),
    [["Diária", "Diária não informada"], ["Despesas", "R$ 87,50"]]);
  assert.deepStrictEqual(D.dsLinhasTotais({despesas_centavos: 8750, noites: 3}), [["Despesas", "R$ 87,50"]]);
});
caso("mensagem de lançado", () => {
  assert.strictEqual(D.dsDescricaoLancado({quantidade: 2, descricao: "Água", valor_unit_centavos: 800}), "Lançado: 2 x Água R$ 8,00.");
});
caso("data/hora: admin recebe a hora, os outros só a data", () => {
  assert.strictEqual(D.dsDataHora("2026-10-29"), "29/10");
  assert.deepStrictEqual(D.dsQuando("2026-10-29 09:05:33"), {data: "29/10", hora: "09:05:33"});
  assert.deepStrictEqual(D.dsQuando("2026-10-29"), {data: "29/10", hora: ""});
});
caso("lançamento por item: o total vem do preço do item", () => {
  const item = {id: 3, versao: 2, preco_centavos: 1500};
  const r = D.dsConferirPorItem(item, "3");
  assert.deepStrictEqual(r.dados, {item_id: 3, item_versao: 2, quantidade: 3});
  assert.strictEqual(r.total, 4500);
  assert.ok(D.dsConferirPorItem(null, "1").erro);
  for (const q of ["0", "100", "1,5", "", "a"]) assert.ok(D.dsConferirPorItem(item, q).erro, q);
  assert.ok(!("valor_unit_centavos" in r.dados) && !("descricao" in r.dados));
});
caso("agrupa itens por categoria e grupo mantendo a ordem do servidor", () => {
  const g = D.dsAgruparItens([{categoria_rotulo: "Bebidas", grupo: "Águas"}, {categoria_rotulo: "Bebidas", grupo: "Águas"},
    {categoria_rotulo: "Bebidas", grupo: "Sucos"}, {categoria_rotulo: "Porções", grupo: ""}]);
  assert.deepStrictEqual(g.map(x => [x.rotulo, x.itens.length]), [["Bebidas - Águas", 2], ["Bebidas - Sucos", 1], ["Porções", 1]]);
});

let falhas = 0;
casos.forEach(([n, f]) => { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } });
if (falhas) process.exit(1);
console.log("despesas_logica: " + casos.length + " casos ok");
