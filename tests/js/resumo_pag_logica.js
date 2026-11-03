"use strict";
// Testa a lógica pura de static/resumo_pag_logica.js. Roda com: node tests/js/resumo_pag_logica.js
const assert = require("assert");
const path = require("path");
const S = path.join(__dirname, "..", "..", "static");
const L = require(path.join(S, "resumo_logica.js"));
const P = require(path.join(S, "resumo_pag_logica.js"));
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);
const ITENS = [{id: "diaria", tipo: "diaria", descricao: "Diárias", centavos: 90000}, {id: "d1", tipo: "consumo", descricao: "Água", centavos: 1600},
  {id: "d2", tipo: "consumo", descricao: "Suco", centavos: 500}, {id: "p7", tipo: "credito", descricao: "Pagamento Pix", centavos: 20000}];
const CFG = {bandeiras: ["Visa", "Elo"], max_parcelas: 12, parcela_min_centavos: 500};
const cartao = t => /\d{13,}/.test(t.replace(/\D/g, ""));

caso("escopo: nada selecionado = conta inteira; selecionado = só o escolhido", () => {
  assert.strictEqual(P.rcEscopo(ITENS, {}).itens.length, 4);
  const e = P.rcEscopo(ITENS, {diaria: true});
  assert.deepStrictEqual([e.selecionou, e.itens.map(i => i.id)], [true, ["diaria"]]);
  assert.strictEqual(P.rcSomaCobrancas(ITENS), 92100); assert.strictEqual(P.rcSomaPagamentos(ITENS), 20000);
});
caso("valor sugerido: seleção limitada ao saldo; sem seleção, o saldo", () => {
  assert.strictEqual(P.rcValorSugerido(P.rcEscopo(ITENS, {}), 72100), 72100);
  assert.strictEqual(P.rcValorSugerido(P.rcEscopo(ITENS, {diaria: true}), 70000), 70000);
  assert.strictEqual(P.rcValorSugerido(P.rcEscopo(ITENS, {d1: true, d2: true}), 99999), 2100);
  assert.strictEqual(P.rcValorSugerido(P.rcEscopo(ITENS, {}), -5), 0);
});
caso("parcelas somam sempre o valor e a descrição é honesta", () => {
  [[10001, 3], [1, 1], [99999, 12], [6000, 12], [7, 12]].forEach(([v, n]) => {
    const p = P.rcParcelasValores(v, n); assert.strictEqual(p.length, n); assert.strictEqual(p.reduce((a, b) => a + b, 0), v);
  });
  assert.strictEqual(P.rcDescParcelas(10001, 3), "2x de R$ 33,34 e 1x de R$ 33,33");
  assert.strictEqual(P.rcDescParcelas(9000, 3), "3x de R$ 30,00");
});
caso("recebimento: dinheiro, valor acima do saldo, troco", () => {
  const f = {forma: "dinheiro", valor: "150,00", recebido: "200"};
  assert.deepStrictEqual(P.rcPagConferir(f, 20000, CFG, cartao).corpo, {forma: "dinheiro", valor_centavos: 15000, recebido_centavos: 20000});
  assert.ok(P.rcPagConferir(f, 14999, CFG, cartao).erro); assert.ok(P.rcPagConferir({forma: "dinheiro", valor: "0"}, 100, CFG, cartao).erro);
  assert.ok(P.rcPagConferir({forma: "dinheiro", valor: "10", recebido: "5"}, 100000, CFG, cartao).erro);
  assert.ok(P.rcPagConferir({forma: "dinheiro", valor: "abc"}, 100000, CFG, cartao).erro);
});
caso("recebimento no cartão: bandeira, modalidade, parcelas e NSU", () => {
  const base = {forma: "cartao", valor: "300,00", bandeira: "Visa", modalidade: "credito", parcelamento: "parcelado", parcelas: "3", nsu: "AB12cd"};
  assert.deepStrictEqual(P.rcPagConferir(base, 90000, CFG, cartao).corpo,
    {forma: "cartao", valor_centavos: 30000, bandeira: "Visa", modalidade: "credito", parcelas: 3, autorizacao: "AB12cd"});
  assert.strictEqual(P.rcPagConferir(Object.assign({}, base, {parcelamento: "avista"}), 90000, CFG, cartao).corpo.parcelas, 1);
  assert.strictEqual(P.rcPagConferir(Object.assign({}, base, {modalidade: "debito"}), 90000, CFG, cartao).corpo.parcelas, 1);
  assert.ok(P.rcPagConferir(Object.assign({}, base, {parcelas: "13"}), 90000, CFG, cartao).erro);
  assert.ok(P.rcPagConferir(Object.assign({}, base, {valor: "19,99", parcelas: "4"}), 90000, CFG, cartao).erro);
  assert.ok(P.rcPagConferir(Object.assign({}, base, {bandeira: "Xpto"}), 90000, CFG, cartao).erro);
  ["4111111111111111", "ab cd", "abcdefghijklm", "<b>"].forEach(n => assert.ok(P.rcPagConferir(Object.assign({}, base, {nsu: n}), 90000, CFG, cartao).erro, n));
  assert.ok(!JSON.stringify(P.rcPagConferir(Object.assign({}, base, {nsu: "4111111111111111"}), 90000, CFG, cartao)).includes("4111"));
});
caso("Pix: referência opcional só alfanumérica", () => {
  assert.deepStrictEqual(P.rcPagConferir({forma: "pix", valor: "1,00", referencia: ""}, 100, CFG, cartao).corpo, {forma: "pix", valor_centavos: 100});
  assert.strictEqual(P.rcPagConferir({forma: "pix", valor: "1,00", referencia: "E123abc"}, 100, CFG, cartao).corpo.referencia, "E123abc");
  assert.ok(P.rcPagConferir({forma: "pix", valor: "1,00", referencia: "a-b"}, 100, CFG, cartao).erro);
});
caso("motivo obrigatório e sem cartão", () => {
  assert.ok(P.rcMotivoConferir("", cartao).erro); assert.ok(P.rcMotivoConferir("abc", cartao).erro);
  assert.ok(P.rcMotivoConferir("erro no cartão 4111111111111111", cartao).erro); assert.strictEqual(P.rcMotivoConferir(" valor errado ", cartao).motivo, "valor errado");
});
caso("extrato: só o selecionado; saldo só na conta inteira", () => {
  const T = {saldo_centavos: 72100};
  const a = P.rcExtratoDados(ITENS, {diaria: true}, T); assert.deepStrictEqual([a.parcial, a.linhas.length, a.total, a.saldo], [true, 1, 90000, null]);
  const b = P.rcExtratoDados(ITENS, {}, T); assert.deepStrictEqual([b.parcial, b.linhas.length, b.total, b.pagamentos, b.saldo], [false, 4, 92100, 20000, 72100]);
  assert.strictEqual(b.linhas[3].valor, "-R$ 200,00");
});
caso("barra de botões por perfil e estado da conta", () => {
  const c = {ativa: true, veiculo: true, despesas: true, aberta: true, receber: true, estornar: true, transferir: true, fechar: true, reabrir: true, saldo: 5};
  assert.deepStrictEqual(P.rcBarraBotoes(c), ["placa", "extrato", "receber", "estornar", "transferir", "info"]);
  assert.ok(P.rcBarraBotoes(Object.assign({}, c, {saldo: 0})).includes("fechar"));
  assert.deepStrictEqual(P.rcBarraBotoes(Object.assign({}, c, {aberta: false})), ["placa", "extrato", "info", "reabrir_conta"]);
  assert.deepStrictEqual(P.rcBarraBotoes(Object.assign({}, c, {aberta: false, reabrir: false})), ["placa", "extrato", "info"]);
  assert.deepStrictEqual(P.rcBarraBotoes({ativa: true, despesas: true}), ["extrato", "info"]);
  assert.deepStrictEqual(P.rcBarraBotoes({ativa: false, despesas: true}), []);
});
caso("azulejos de Crédito e Saldo e itens de pagamento", () => {
  const RES = {i: "2026-10-27", f: "2026-10-30", diaria_centavos: 30000};
  const T = {despesas_centavos: 0, pagamentos_centavos: 20000, saldo_centavos: 70000, conta_centavos: 90000};
  const az = L.rcAzulejos(RES, T, {valores: true, despesas: true, temPagamentos: true});
  assert.deepStrictEqual(az.map(a => a.id), ["diaria", "evento", "consumo", "credito", "saldo"]);
  assert.strictEqual(az[3].valor, "R$ 200,00"); assert.ok(az[3].selecionavel && az[4].semCaixa);
  const it = L.rcItensConta(RES, [], {valores: true, despesas: true, pagamentos: true}, [{id: 7, tipo: "recebimento", estornado: false, forma: "cartao", bandeira: "Visa", modalidade: "credito", parcelas: 3, valor_centavos: 20000}]);
  assert.strictEqual(it[1].id, "p7"); assert.strictEqual(it[1].descricao, "Pagamento Cartão Visa crédito em 3x");
});

let falhas = 0;
casos.forEach(([n, f]) => { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } });
if (falhas) process.exit(1);
console.log("resumo_pag_logica: " + casos.length + " casos ok");
