"use strict";
// Testa a parte pura de static/fnrh.js. Roda com: node tests/js/fnrh.js
const assert = require("assert");
const path = require("path");
const F = require(path.join(__dirname, "..", "..", "static", "fnrh.js"));
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);
const D = {reserva: {id: 1, a: "201", i: "2026-10-27", f: "2026-10-30", n: 4, placa: "ABC-1234", emitido_em: "2026-10-29 09:05:00"},
  titular: {nome: "Maria Silva", tipo: "adulto", documento: "123.456.789-09", nascimento: "1980-05-17", nacionalidade: null, profissao: "Médica", procedencia: null, destino: null},
  acompanhantes: [{nome: "Ana Silva", tipo: "crianca", documento: null, nascimento: "2018-02-01"}], em_branco: 2};

caso("campos exatamente os pedidos, sem inventar obrigatórios", () => {
  assert.deepStrictEqual(F.FNRH_PESSOA.map(c => c[1]), ["nome", "documento", "nascimento", "nacionalidade", "profissao", "procedencia", "destino"]);
  const f = F.fnrhLinhas(D, "Maria Silva");
  assert.deepStrictEqual(f.hospedagem.map(c => c[0]), ["Apartamento", "Entrada (a partir das 14h)", "Saída (até as 12h)", "Número de pessoas", "Placa do veículo", "Meio de transporte", "Motivo da viagem"]);
});
caso("preenchidos saem com valor e os que faltam ficam em branco", () => {
  const f = F.fnrhLinhas(D, "Maria Silva"), t = f.pessoas[0];
  const val = (p, r) => p.campos.find(c => c[0].startsWith(r))[1];
  assert.strictEqual(val(t, "Nome"), "Maria Silva"); assert.strictEqual(val(t, "Data"), "17/05/1980"); assert.strictEqual(val(t, "Nacionalidade"), "");
  assert.strictEqual(f.hospedagem[4][1], "ABC-1234"); assert.strictEqual(f.hospedagem[5][1], ""); assert.strictEqual(f.hospedagem[6][1], "");
  assert.strictEqual(t.titulo, "Hóspede titular");
});
caso("acompanhantes cadastrados e linhas em branco para os demais", () => {
  const f = F.fnrhLinhas(D, "Maria Silva");
  assert.deepStrictEqual(f.pessoas.map(p => p.titulo), ["Hóspede titular", "Acompanhante 1", "Acompanhante 2", "Acompanhante 3"]);
  assert.strictEqual(f.pessoas[1].tipo, "Criança"); assert.ok(f.pessoas[3].campos.every(c => c[1] === ""));
});
caso("sem placa nem hóspedes: tudo em branco", () => {
  const f = F.fnrhLinhas({reserva: Object.assign({}, D.reserva, {placa: null, n: 1}), titular: {nome: "X Y", tipo: "adulto"}, acompanhantes: [], em_branco: 0}, "X Y");
  assert.strictEqual(f.hospedagem[4][1], ""); assert.strictEqual(f.pessoas.length, 1);
});
let falhas = 0;
casos.forEach(([n, f]) => { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } });
if (falhas) process.exit(1);
console.log("fnrh: " + casos.length + " casos ok");
