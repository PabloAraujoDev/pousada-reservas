"use strict";
// Testa as funções puras de static/governanca_logica.js e o selo do Calendário. Roda com: node tests/js/governanca_logica.js
const assert = require("assert");
const path = require("path");
const G = require(path.join(__dirname, "..", "..", "static", "governanca_logica.js"));
const C = require(path.join(__dirname, "..", "..", "static", "calendario_dia.js"));

const UN = ["101","102","103","104","201","202","203","204","205","206","207","208",
  "301","302","303","304","305","306","307","308","Chalé A","Chalé B","Chalé C","Chalé D","Chalé E"];
const andar = u => /^Chal/.test(u) ? "Chalés" : ({1: "Térreo", 2: "2º andar", 3: "3º andar"})[u[0]];
const U = (u, extra) => Object.assign({u, andar: andar(u), situacao: "pronta", saida_hoje: null, chegada_hoje: null, troca_hoje: false,
  atrasada: false, pessoas: null, dias_sem_arrumacao: null, alerta_enxoval: false, pronta_ha_dias: null, obs: "", versao: 1, pode: []}, extra || {});
const TODAS = UN.map(u => U(u, u === "104" ? {situacao: "interditada"} : {}));
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);

caso("agrupa por andar na ordem fixa e ignora grupo vazio", () => {
  const g = G.gvAgrupar(TODAS);
  assert.deepStrictEqual(g.map(x => x.nome), ["Térreo", "2º andar", "3º andar", "Chalés"]);
  assert.deepStrictEqual(g.map(x => x.itens.length), [4, 8, 8, 5]);
  assert.deepStrictEqual(G.gvAgrupar(TODAS.filter(i => i.andar === "Chalés")).map(x => x.nome), ["Chalés"]);
});
caso("filtros: andar, situação, chegada, saída, busca (com e sem acento)", () => {
  const L = [U("201", {situacao: "suja", saida_hoje: {hora: "12:00"}}), U("202", {chegada_hoje: {hora: "14:00", pessoas: 2}}), U("Chalé A", {situacao: "suja"})];
  const f = x => G.gvFiltrar(L, Object.assign({}, G.GV_FILTRO_VAZIO, x)).map(i => i.u);
  assert.deepStrictEqual(f({}), ["201", "202", "Chalé A"]);
  assert.deepStrictEqual(f({andar: "2º andar"}), ["201", "202"]);
  assert.deepStrictEqual(f({situacao: "suja"}), ["201", "Chalé A"]);
  assert.deepStrictEqual(f({chegada: true}), ["202"]);
  assert.deepStrictEqual(f({saida: true}), ["201"]);
  assert.deepStrictEqual(f({busca: "20"}), ["201", "202"]);
  assert.deepStrictEqual(f({busca: "chale a"}), ["Chalé A"]);
  assert.deepStrictEqual(f({busca: "  "}), ["201", "202", "Chalé A"]);
  assert.deepStrictEqual(f({situacao: "suja", andar: "Chalés"}), ["Chalé A"]);
  assert.strictEqual(G.gvFiltroAtivo(G.GV_FILTRO_VAZIO), false); assert.strictEqual(G.gvFiltroAtivo({busca: "2"}), true);
});
caso("contagens do grupo (104 interditada não entra)", () => {
  const c = G.gvContagens([U("101", {situacao: "suja", saida_hoje: {hora: "12:00"}}), U("102", {situacao: "em_arrumacao"}), U("103"), U("104", {situacao: "interditada"})]);
  assert.deepStrictEqual(c, {saida: 1, suja: 1, em_arrumacao: 1, pronta: 1});
  assert.strictEqual(G.gvTextoContagens(c), "Saída 1 | Suja 1 | Em arrumação 1 | Pronta 1");
});
caso("ações em massa: só as comuns a TODAS", () => {
  const a = U("201", {pode: ["iniciar", "pronta"]}), b = U("202", {pode: ["iniciar", "pronta", "suja"]}), c = U("203", {pode: ["pronta"]});
  assert.deepStrictEqual(G.gvAcoesComuns([a, b]), ["iniciar", "pronta"]);
  assert.deepStrictEqual(G.gvAcoesComuns([a, b, c]), ["pronta"]);
  assert.deepStrictEqual(G.gvAcoesComuns([U("204", {pode: []}), a]), []);
  assert.deepStrictEqual(G.gvAcoesComuns([]), []);
  assert.ok(/204/.test(G.gvMotivoSemAcao([U("204", {pode: []}), a])));
  assert.ok(/mesma situação/.test(G.gvMotivoSemAcao([U("201", {pode: ["iniciar"]}), U("202", {pode: ["suja"]})])));
});
caso("seleção: interditada não é selecionável; conflitos saem da seleção", () => {
  assert.strictEqual(G.gvSelecionaveis(TODAS).length, 24);
  assert.deepStrictEqual(G.gvSelecaoSemConflitos(["202", "203", "204"], [{u: "203"}]), ["202", "204"]);
  assert.deepStrictEqual(G.gvSelecaoSemConflitos(["202"], undefined), ["202"]);
});
caso("assinatura muda só quando os dados mudam (agora/hora não contam)", () => {
  const d = {hoje: "2026-10-29", dia: "2026-10-29", agora: "09:00", totais: {suja: 1}, unidades: [U("201")]};
  const mesma = Object.assign({}, d, {agora: "09:01"});
  assert.strictEqual(G.gvAssinatura(d), G.gvAssinatura(mesma));
  assert.notStrictEqual(G.gvAssinatura(d), G.gvAssinatura(Object.assign({}, d, {unidades: [U("201", {versao: 2})]})));
});
caso("mudanças de situação entre duas leituras", () => {
  const m = G.gvMudancas([U("201"), U("202")], [U("201", {situacao: "suja"}), U("202"), U("203")]);
  assert.deepStrictEqual(m, [{u: "201", de: "pronta", para: "suja"}]);
});
caso("textos do cartão: só o que vale", () => {
  assert.deepStrictEqual(G.gvTextoDias(U("201", {situacao: "suja", dias_sem_arrumacao: 8})), ["Há 8 dias sem arrumação"]);
  assert.deepStrictEqual(G.gvTextoDias(U("201", {situacao: "suja", dias_sem_arrumacao: 1})), ["Há 1 dia sem arrumação"]);
  assert.deepStrictEqual(G.gvTextoDias(U("301", {situacao: "hospedada", dias_sem_arrumacao: 8, alerta_enxoval: true})), ["Troca de enxoval (8 dias)"]);
  assert.deepStrictEqual(G.gvTextoDias(U("302", {pronta_ha_dias: 10, dias_sem_arrumacao: 10})), ["Pronta há 10 dias"]);
  assert.deepStrictEqual(G.gvTextoDias(U("303")), []);
  const t = U("202", {troca_hoje: true, atrasada: true, saida_hoje: {hora: "12:00"}, chegada_hoje: {hora: "14:00", pessoas: 2}});
  assert.deepStrictEqual(G.gvSelos(t).map(s => s.txt), ["In 14:00", "Out 12:00", "TROCA HOJE", "ATRASADA"]);
  assert.strictEqual(G.gvPessoasDoCartao(t), "2 pessoas"); assert.strictEqual(G.gvPessoasDoCartao(U("201", {pessoas: 1})), "1 pessoa");
});
caso("aria-label completo e 'pode entrar'", () => {
  const i = U("202", {situacao: "suja", saida_hoje: {hora: "12:00"}, chegada_hoje: {hora: "14:00", pessoas: 2}, dias_sem_arrumacao: 8});
  assert.strictEqual(G.gvAria(i), "Apartamento 202, suja, saída 12:00, chegada 14:00, 2 pessoas, há 8 dias sem arrumação");
  assert.strictEqual(G.gvAria(U("Chalé B")), "Chalé B, pronta");
  assert.strictEqual(G.gvPodeEntrar(U("205", {chegada_hoje: {hora: "14:00", pessoas: 2}})), true);
  assert.strictEqual(G.gvPodeEntrar(U("205", {situacao: "suja", chegada_hoje: {hora: "14:00", pessoas: 2}})), false);
  assert.ok(/pode entrar/.test(G.gvAria(U("205", {chegada_hoje: {hora: "14:00", pessoas: 2}}))));
});
caso("resumo do resultado e texto do conflito", () => {
  assert.strictEqual(G.gvResumoResultado([{resultado: "ok"}, {resultado: "ok"}], 2), "2 de 2 atualizadas");
  assert.strictEqual(G.gvResumoResultado([{resultado: "ok"}], 1), "1 de 1 atualizada");
  assert.strictEqual(G.gvResumoResultado([{resultado: "ok"}, {resultado: "ja_estava"}], 2), "1 de 2 atualizadas (1 já estava assim)");
  assert.strictEqual(G.gvTextoConflito({u: "203", situacao_atual: "em_arrumacao", por: "ana", em: "09:02"}), "203: agora está em arrumação (ana às 09:02)");
  assert.strictEqual(G.gvTextoConflito({u: "203", situacao_atual: "pronta", por: null}), "203: agora está pronta (outra pessoa)");
});
caso("impressão: trocas, saídas, chegadas, enxoval, demais; interditada fora; atrasada primeiro", () => {
  const L = [U("101"), U("104", {situacao: "interditada"}), U("201", {chegada_hoje: {hora: "14:00", pessoas: 1}}), U("202", {saida_hoje: {hora: "12:00"}}),
    U("203", {troca_hoje: true, saida_hoje: {hora: "12:00"}, chegada_hoje: {hora: "14:00", pessoas: 2}}),
    U("204", {troca_hoje: true, atrasada: true, saida_hoje: {hora: "12:00"}, chegada_hoje: {hora: "14:00", pessoas: 2}}),
    U("301", {situacao: "hospedada", alerta_enxoval: true})];
  assert.deepStrictEqual(G.gvOrdenarImpressao(L, UN).map(i => i.u), ["204", "203", "202", "201", "301", "101"]);
});
caso("Calendário: selo só para suja, em arrumação e pronta; 'pode entrar' = pronta + chegada hoje", () => {
  assert.deepStrictEqual(C.cdGovSelo({situacao: "suja", chegada: false}), {classe: "suja", texto: "Suja", entrar: false});
  assert.strictEqual(C.cdGovSelo({situacao: "em_arrumacao", chegada: true}).texto, "Em arrumação");
  assert.strictEqual(C.cdGovSelo({situacao: "pronta", chegada: true}).texto, "Pronta · pode entrar");
  assert.strictEqual(C.cdGovSelo({situacao: "pronta", chegada: false}).texto, "Pronta");
  ["hospedada", "manutencao", "interditada", "aguardando_saida"].forEach(s => assert.strictEqual(C.cdGovSelo({situacao: s, chegada: true}), null));
  assert.strictEqual(C.cdGovSelo(undefined), null);
});

let falhas = 0;
for (const [nome, f] of casos) {
  try { f(); console.log("ok   " + nome); } catch (e) { falhas++; console.log("FALHA " + nome + ": " + e.message); }
}
process.exit(falhas ? 1 : 0);
