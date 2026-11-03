"use strict";
// Testa as funções puras de static/operacao_dia.js (listas dos cartões). Roda com: node tests/js/operacao_logica.js
const assert = require("assert");
const path = require("path");
const est = (n) => path.join(__dirname, "..", "..", "static", n);
const O = require(est("operacao_dia.js"));
const A = require(est("operacao_acoes.js"));
const D = require(est("operacao_dialogos.js"));

let seq = 0;
const R = (a, i, f, n, nome) => ({id: ++seq, a, nome: nome || "Hóspede " + a, n: n || 2, i, f, p: "pago", grupo: "", tipo: null});

const casos = [];
const caso = (nome, f) => casos.push([nome, f]);

caso("próxima reserva: a mais cedo com entrada a partir do dia", () => {
  const res = [R("201", "2026-11-10", "2026-11-12"), R("201", "2026-11-05", "2026-11-07", 2, "Ana"), R("201", "2026-10-01", "2026-10-03"), R("202", "2026-11-01", "2026-11-02")];
  assert.strictEqual(O.odProximaReserva(res, "201", "2026-11-02").nome, "Ana");
  assert.strictEqual(O.odProximaReserva(res, "201", "2026-11-05").nome, "Ana");        // entrada no próprio dia conta
  assert.strictEqual(O.odProximaReserva(res, "201", "2026-11-11"), null);
  assert.strictEqual(O.odProximaReserva(res, "999", "2026-11-02"), null);
});
caso("texto do vago", () => {
  const prox = R("201", "2026-11-05", "2026-11-07", 2, "Ana");
  assert.strictEqual(O.odQuandoVaga(null, prox, "2026-11-02"), "Livre até 05/11 (próxima: Ana, entra 05/11 14h).");
  assert.strictEqual(O.odQuandoVaga(null, null, "2026-11-02"), "Sem próxima reserva.");
  assert.strictEqual(O.odQuandoVaga(null, R("1", "2026-11-02", "2026-11-03", 1, "Bia"), "2026-11-02"), "Livre até hoje (próxima: Bia, entra hoje 14h).");
  const saindo = R("201", "2026-10-30", "2026-11-02", 2, "Caio");
  assert.strictEqual(O.odQuandoVaga(saindo, null, "2026-11-02"), "Sai Caio ao meio-dia: livre a partir das 12h. Sem próxima reserva.");
});
caso("título com (hoje) ou (neste dia)", () => {
  assert.strictEqual(O.odTitulo("ins", "2026-10-31", "2026-10-31"), "Check-ins de 31/10/2026 (hoje)");
  assert.strictEqual(O.odTitulo("outs", "2026-11-01", "2026-10-31"), "Check-outs de 01/11/2026 (neste dia)");
});
caso("contador conta unidades (troca = 2 linhas, 1 unidade) e pessoas", () => {
  const a = R("203", "2026-10-30", "2026-11-02", 3), b = R("203", "2026-11-02", "2026-11-04", 2), c = R("205", "2026-11-02", "2026-11-03", 1);
  const linhas = [{a: "203", r: a}, {a: "203", r: b}, {a: "205", r: c}];
  assert.strictEqual(O.odContador(linhas, "ins"), "2 apartamentos, 6 pessoas");
  assert.strictEqual(O.odContador([{a: "205", r: c}], "ins"), "1 apartamento, 1 pessoa");
  assert.strictEqual(O.odContador([{a: "101"}, {a: "102"}], "vagos"), "2 apartamentos");
  assert.strictEqual(O.odContador([], "outs"), "0 apartamentos, 0 pessoas");
  assert.strictEqual(O.odContador(linhas, null), "2 apartamentos");
});
caso("mensagens de vazio por categoria e para a pesquisa", () => {
  assert.strictEqual(O.odVazio("ins", ""), "Nenhum check-in neste dia.");
  assert.strictEqual(O.odVazio("interditados", ""), "Nenhum apartamento interditado.");
  assert.strictEqual(O.odVazio("vagos", ""), "Todos os apartamentos estão ocupados.");
  assert.strictEqual(O.odVazio("outs", "xyz"), "Nenhuma reserva corresponde à busca.");
  assert.strictEqual(O.odVazio("vagos", "xyz"), "Nenhum apartamento corresponde à busca.");
  assert.strictEqual(O.odVazio(null, ""), "Nenhuma reserva neste dia: nenhuma chegada, saída ou hóspede.");
});
caso("colunas por categoria", () => {
  assert.deepStrictEqual(O.odColunas("vagos", false), ["Apto", "Situação", "Quando fica ocupada/livre"]);
  assert.deepStrictEqual(O.odColunas("interditados", true), ["Ações", "Apto", "Situação", "Quando fica ocupada/livre"]);
  assert.ok(O.odColunas("ocupados", false).includes("Sai em") && !O.odColunas("ocupados", false).includes("Saída"));
  assert.ok(O.odColunas("ins", false).includes("Saída") && O.odColunas(null, false).length === 9);
});

caso("ações por perfil e tipo de linha (botões sem permissão nem existem)", () => {
  const todos = {despesas: true, ver: true, governanca: true, temNota: true};
  assert.deepStrictEqual(A.odAcoesDisponiveis("reserva", todos, false), ["info", "obs"]);                 // interruptor desligado: sem Despesas
  assert.deepStrictEqual(A.odAcoesDisponiveis("reserva", todos, true), ["despesas", "info", "obs"]);
  assert.deepStrictEqual(A.odAcoesDisponiveis("reserva", {despesas: false, ver: true}, true), ["info", "obs"]);   // consulta
  assert.deepStrictEqual(A.odAcoesDisponiveis("reserva", {despesas: true, ver: false}, true), []);            // camareira nunca vê
  assert.deepStrictEqual(A.odAcoesDisponiveis("vaga", todos, true), ["info", "obs"]);                    // vaga nunca tem Despesas
  assert.deepStrictEqual(A.odAcoesDisponiveis("vaga", {ver: true, governanca: true, temNota: false}, true), ["info"]);   // sem texto: sem Observações
  assert.deepStrictEqual(A.odAcoesDisponiveis("interditada", {ver: true, governanca: false, temNota: true}, true), ["info"]);
});
caso("o interruptor de Despesas está ligado (Parte 2A) e o ponto vem do servidor", () => {
  assert.deepStrictEqual(A.odAcoesDisponiveis("reserva", {despesas: true, ver: true}), ["despesas", "info", "obs"]);
  const l = {tipo: "reserva", a: "412", r: {nome: "Luciana", tem_despesa: true}, temNota: false};
  assert.strictEqual(A.odRotuloAcao("despesas", l), "Despesas do apartamento 412, hóspede Luciana (há lançamentos)");
});
caso("rótulos acessíveis completos e indicador só booleano", () => {
  const l = {tipo: "reserva", a: "412", r: {nome: "Luciana"}, temNota: false};
  assert.strictEqual(A.odRotuloAcao("despesas", l), "Despesas do apartamento 412, hóspede Luciana");
  assert.strictEqual(A.odRotuloAcao("obs", Object.assign({}, l, {temNota: true})), "Observações do apartamento 412, hóspede Luciana (há observações)");
  assert.strictEqual(A.odRotuloAcao("info", {tipo: "vaga", a: "101"}), "Informações da unidade 101");
  assert.strictEqual(A.odTemNota({o: "  ", extras: ""}), false);
  assert.strictEqual(A.odTemNota({o: "", extras: "berço"}), true);
  assert.strictEqual(A.odTemNota({o: "", extras: "", tem_nota: true}), true);        // nota com autor (013): o servidor manda só o sim/não
  assert.strictEqual(A.odTemNota({o: "", extras: "", tem_nota: false}), false);
  assert.strictEqual(A.odTemNota(null), false);
});
caso("informações da reserva: só dados existentes, endereço não preenchido, sem valor", () => {
  const r = {id: 7, a: "412", nome: "Luciana Rezende", n: 2, i: "2026-10-29", f: "2026-10-31", p: "parcial", tipo: "socio", grupo: "Turma A", diaria_centavos: 35000};
  const t = D.odLinhasInfo({tipo: "reserva", a: "412", r: r, situacao: "ocupada", troca: false}, {gov: "Pronta"});
  const m = Object.fromEntries(t);
  assert.strictEqual(m["Período"], "Entrada 29/10/2026 (14h) | Saída 31/10/2026 (12h) | 2 noites");
  assert.strictEqual(m["Pessoas"], "2"); assert.strictEqual(m["Sócio ou convidado"], "Sócio do clube");
  assert.strictEqual(m["Grupo"], "Turma A"); assert.strictEqual(m["Pagamento"], "Parcial"); assert.strictEqual(m["Governança"], "Pronta");
  assert.strictEqual(m["Situação no dia"], "Ocupado");
  assert.ok(m["Endereço/contato"].startsWith("Cadastro não preenchido"));
  assert.ok(!JSON.stringify(t).includes("35000") && !JSON.stringify(t).toLowerCase().includes("diaria"));
  const sem = Object.fromEntries(D.odLinhasInfo({tipo: "reserva", a: "1", r: Object.assign({}, r, {tipo: null, grupo: ""}), situacao: "saindo", troca: true}, {gov: null}));
  assert.strictEqual(sem["Sócio ou convidado"], "Não informado"); assert.strictEqual(sem["Grupo"], "Não informado");
  assert.ok(!("Governança" in sem)); assert.ok(sem["Situação no dia"].startsWith("Troca"));
});
caso("informações da vaga e da interditada", () => {
  const prox = {nome: "Ana", i: "2026-11-05"};
  const v = Object.fromEntries(D.odLinhasInfo({tipo: "vaga", a: "101"}, {proxima: prox, gov: "Suja"}));
  assert.strictEqual(v["Próxima reserva"], "Ana, entra 05/11/2026 14h"); assert.strictEqual(v["Situação"], "Vaga"); assert.ok(!("Endereço/contato" in v));
  assert.strictEqual(Object.fromEntries(D.odLinhasInfo({tipo: "vaga", a: "101"}, {proxima: null}))["Próxima reserva"], "Sem próxima reserva");
  assert.ok(Object.fromEntries(D.odLinhasInfo({tipo: "interditada", a: "104"}, {}))["Situação"].startsWith("Interditada"));
});
caso("noites", () => { assert.strictEqual(D.odNoites("2026-10-30", "2026-11-02"), 3); assert.strictEqual(D.odNoites("2026-12-31", "2027-01-01"), 1); });
let falhas = 0;
casos.forEach(([n, f]) => { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } });
if (falhas) process.exit(1);
console.log("operacao_logica: " + casos.length + " casos ok");
