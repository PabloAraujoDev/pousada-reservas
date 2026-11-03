"use strict";
// Testa as funções puras de static/calendario_dia.js (sem navegador). Roda com: node tests/js/calendario_logica.js
const assert = require("assert");
const path = require("path");
const C = require(path.join(__dirname, "..", "..", "static", "calendario_dia.js"));

const UN = ["101","102","103","104","201","202","203","204","205","206","207","208",
  "301","302","303","304","305","306","307","308","Chalé A","Chalé B","Chalé C","Chalé D","Chalé E"];
const OC = {"104": true};
const D = "2026-10-29";
let seq = 0;
const R = (a, i, f, n, extra) => Object.assign({id: ++seq, a, nome: "Hóspede " + a, n: n || 2, i, f, p: "pago", grupo: "", tipo: null}, extra || {});
const ind = (res, dia, hoje, hora) => C.cdIndicadores(res, dia || D, UN, OC, hoje || "2026-01-01", hora == null ? 10 : hora);
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);

caso("1 dia sem reservas", () => {
  const x = ind([]);
  assert.deepStrictEqual([x.ins, x.outs, x.ocupados, x.vagos, x.interditados], [0, 0, 0, 24, 1]);
  assert.strictEqual(x.prevista.pct, "0%"); assert.strictEqual(x.prevista.pessoas, 0);
  const c = C.cdContarEstados(x.est);
  assert.strictEqual(c.vaga, 24); assert.strictEqual(c.interditada, 1);
  assert.strictEqual(x.est.length, 25);
});
caso("2 virada no mesmo apartamento", () => {
  const res = [R("201", "2026-10-27", D), R("201", D, "2026-11-01")];
  let x = ind(res);
  assert.strictEqual(x.ins, 1); assert.strictEqual(x.outs, 1); assert.strictEqual(x.prevista.unidades, 1);   // nunca 2
  assert.strictEqual(x.est.find(e => e.a === "201").estado, "troca");
  assert.strictEqual(ind(res, D, D, 10).ocupados, 1);
  assert.strictEqual(ind(res, D, D, 13).ocupados, 0);
  assert.strictEqual(ind(res, D, D, 15).ocupados, 1);
});
caso("3 reserva de uma noite", () => {
  const res = [R("102", D, "2026-10-30")];
  const a = ind(res), b = ind(res, "2026-10-30");
  assert.strictEqual(a.ins, 1); assert.strictEqual(a.prevista.unidades, 1);
  assert.strictEqual(b.outs, 1); assert.strictEqual(b.prevista.unidades, 0); assert.strictEqual(b.ins, 0);
});
caso("4 estadia longa", () => {
  const x = ind([R("301", "2026-10-19", "2026-11-08", 2)]);
  assert.strictEqual(x.est.find(e => e.a === "301").estado, "ocupada");
  assert.deepStrictEqual([x.ins, x.outs, x.prevista.unidades, x.prevista.pessoas], [0, 0, 1, 2]);
});
caso("5 unidade 104 sempre interditada e reserva legada ignorada", () => {
  const x = ind([R("104", D, "2026-10-30")]);
  assert.strictEqual(x.ins, 0); assert.strictEqual(x.vagos, 24); assert.strictEqual(x.prevista.unidades, 0);
  assert.strictEqual(x.est.find(e => e.a === "104").estado, "interditada");
  assert.ok(x.avisos[0].includes("104"));
  assert.strictEqual(C.cdLivresNoite([R("104", D, "2026-10-30")], D, UN, OC), 24);
});
caso("6 lotação", () => {
  const res = UN.filter(u => !OC[u]).map(u => R(u, "2026-10-28", "2026-10-30", 2));
  const x = ind(res);
  assert.strictEqual(x.prevista.pct, "100%"); assert.strictEqual(x.prevista.pessoas, 48);
  assert.strictEqual(C.cdLivresNoite(res, D, UN, OC), 0);
  assert.strictEqual(C.cdFaixaDisp(0), "zero");
});
caso("7 pessoas e arredondamento", () => {
  const ns = [2, 2, 3, 1, 4, 2, 2], aptos = ["101", "102", "103", "201", "202", "203", "204"];
  const x = ind(aptos.map((a, k) => R(a, "2026-10-28", "2026-10-30", ns[k])));
  assert.strictEqual(x.prevista.pessoas, 16); assert.strictEqual(x.prevista.pct, "29,2%");
});
caso("8 saída hoje sem entrada", () => {
  const res = [R("202", "2026-10-27", D)];
  assert.strictEqual(ind(res, D, D, 10).ocupados, 1);
  const x = ind(res, D, D, 12);
  assert.strictEqual(x.ocupados, 0); assert.strictEqual(x.est.find(e => e.a === "202").estado, "saindo");
  assert.strictEqual(x.outs, 1); assert.strictEqual(x.prevista.unidades, 0);
});
caso("9 dia futuro e passado: sem momentânea", () => {
  assert.strictEqual(ind([], "2026-11-05", D).momentanea, null);
  assert.strictEqual(ind([], "2026-10-20", D).momentanea, null);
  assert.ok(ind([], D, D).momentanea);
});
caso("10 busca sem acento, várias palavras e filtro", () => {
  const res = [R("Chalé A", D, "2026-10-31", 2, {nome: "JOSÉ Silva"}), R("201", D, "2026-10-31", 2, {nome: "Ana Silva"}), R("202", "2026-10-25", "2026-10-31", 2, {nome: "Rui Silva"})];
  const est = ind(res).est;
  assert.strictEqual(C.cdFiltrar(est, null, "jose").linhas.length, 1);
  assert.strictEqual(C.cdFiltrar(est, null, "chale a").linhas[0].a, "Chalé A");
  const f = C.cdFiltrar(est, "ins", "silva");
  assert.strictEqual(f.linhas.length, 2); assert.strictEqual(f.total, 2);
  assert.strictEqual(C.cdFiltrar(est, null, "").total, 3);
  assert.strictEqual(C.cdFiltrar(est, "vagos", "").linhas.length, 21);
  assert.strictEqual(C.cdFiltrar(est, "interditados", "").linhas[0].a, "104");
});
caso("11 troca aparece nas duas listas com selo", () => {
  const est = ind([R("201", "2026-10-27", D), R("201", D, "2026-11-01")]).est;
  const l = C.cdFiltrar(est, null, "").linhas;
  assert.deepStrictEqual(l.map(x => x.bloco), ["ins", "outs"]); assert.ok(l.every(x => x.troca));
});
caso("12 totais: ocupados + vagos = 24, com interditados = 25", () => {
  const res = [R("101", D, "2026-10-31"), R("201", "2026-10-20", "2026-11-02"), R("Chalé C", "2026-10-28", D)];
  [10, 13, 15].forEach(h => {
    const x = ind(res, D, D, h);
    assert.strictEqual(x.ocupados + x.vagos, 24); assert.strictEqual(x.ocupados + x.vagos + x.interditados, 25);
  });
});
caso("13 mês e ano virando; calendário de 42 dias", () => {
  assert.strictEqual(C.cdSomaDias("2026-12-31", 1), "2027-01-01");
  assert.strictEqual(C.cdSomaDias("2027-03-01", -1), "2027-02-28");
  assert.strictEqual(C.cdSomaDias("2028-02-28", 1), "2028-02-29");
  assert.strictEqual(C.cdSomaMeses("2026-12-15", 1), "2027-01-01");
  assert.strictEqual(C.cdSomaMeses("2026-01-31", -1), "2025-12-01");
  const d = C.cdDiasDoMes("2026-10-29");
  assert.strictEqual(d.length, 42); assert.strictEqual(d[0], "2026-09-27"); assert.ok(d.includes("2026-10-31") && d.includes("2026-11-07"));
  assert.strictEqual(C.cdRotuloMes("2026-10-29"), "outubro 2026");
  const res = [R("101", "2026-12-30", "2027-01-02")];
  assert.strictEqual(C.cdLivresNoite(res, "2026-12-31", UN, OC), 23); assert.strictEqual(C.cdLivresNoite(res, "2027-01-01", UN, OC), 23);
  assert.strictEqual(C.cdLivresNoite(res, "2027-01-02", UN, OC), 24);
});
caso("14 roscas: arco, limites e porcentagem", () => {
  const a = C.cdArco(0.5, 38); assert.ok(Math.abs(a.dash * 2 - a.circ) < 0.02);
  assert.strictEqual(C.cdArco(0, 38).dash, 0); assert.strictEqual(C.cdArco(2, 38).dash, C.cdArco(1, 38).circ);
  assert.ok(C.cdArco(0.001, 38).dash >= 1.5);
  assert.strictEqual(C.cdFracao(5, 0), 0); assert.strictEqual(C.cdFracao(30, 24), 1);
  assert.strictEqual(C.cdPct(1, 0), "0%"); assert.strictEqual(C.cdPct(7, 24), "29,2%");
  const x = ind([R("101", D, "2026-10-30")]);
  assert.ok(x.fracoes.vagos > 0.95 && x.fracoes.interditados === 1 / 25);
});

caso("rótulos dos blocos: 'hoje' só no dia de hoje", () => {
  assert.strictEqual(C.cdRotuloBloco("ins", true), "Chegam hoje"); assert.strictEqual(C.cdRotuloBloco("outs", true), "Saem hoje");
  assert.strictEqual(C.cdRotuloBloco("ins", false), "Chegam neste dia"); assert.strictEqual(C.cdRotuloBloco("outs", false), "Saem neste dia");
  assert.strictEqual(C.cdRotuloBloco("ocup", false), "Ocupados (ficam)");
});

let falhas = 0;
for (const [nome, f] of casos) {
  try { f(); console.log("ok   " + nome); } catch (e) { falhas++; console.log("FALHA " + nome + ": " + e.message); }
}
process.exit(falhas ? 1 : 0);
