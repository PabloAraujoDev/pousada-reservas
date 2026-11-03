"use strict";
// Testa a lógica pura de static/notas_logica.js. Roda com: node tests/js/notas_logica.js
const assert = require("assert");
const path = require("path");
const N = require(path.join(__dirname, "..", "..", "static", "notas_logica.js"));
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);

caso("data e hora em dd/mm/aaaa hh:mm", () => {
  assert.strictEqual(N.ntDataHora("2026-10-29 09:05:00"), "29/10/2026 09:05");
  assert.strictEqual(N.ntDataHora(""), ""); assert.strictEqual(N.ntDataHora(null), "");
});
caso("autor e modificação", () => {
  const n = {por: "juliano", em: "2026-10-27 14:30:00", modificado_por: null, modificado_em: null};
  assert.strictEqual(N.ntMeta(n), "Adicionado por juliano em 27/10/2026 14:30");
  assert.strictEqual(N.ntMeta(Object.assign({}, n, {modificado_por: "maria", modificado_em: "2026-10-27 14:31:00"})),
    "Adicionado por juliano em 27/10/2026 14:30 · Modificado por maria em 27/10/2026 14:31");
});
caso("abas por situação", () => {
  const ids = p => N.ntAbas(p).map(a => a.id);
  assert.deepStrictEqual(ids({reserva: true, gov: true, apto: true}), ["reserva", "arrumacao", "apartamento"]);
  assert.deepStrictEqual(ids({reserva: false, gov: true, apto: true}), ["arrumacao", "apartamento"]);
  assert.deepStrictEqual(ids({reserva: true, gov: false, apto: true}), ["reserva", "apartamento"]);
  assert.deepStrictEqual(N.ntAbas({reserva: true, gov: true, apto: true}).map(a => a.rotulo), ["Reserva", "Arrumação", "Apartamento"]);
});
caso("texto da arrumação", () => {
  assert.deepStrictEqual(N.ntTextoArrumacao({obs: "Troca de lâmpada", manutencao_motivo: "", atualizado_em: "10:32", atualizado_por: "maria"}),
    ["Observação: Troca de lâmpada", "Última atualização às 10:32 por maria."]);
  assert.deepStrictEqual(N.ntTextoArrumacao({obs: "", manutencao_motivo: "Chuveiro"}), ["Manutenção: Chuveiro"]);
  assert.deepStrictEqual(N.ntTextoArrumacao({obs: "", manutencao_motivo: ""}), ["Nenhuma observação da arrumação."]);
  assert.deepStrictEqual(N.ntTextoArrumacao(null), ["Sem informações da arrumação."]);
});
caso("conferência de texto e motivo", () => {
  assert.deepStrictEqual(N.ntConferirTexto("  oi  "), {texto: "oi"});
  assert.ok(N.ntConferirTexto("   ").erro); assert.ok(N.ntConferirTexto("x".repeat(301)).erro); assert.ok(!N.ntConferirTexto("x".repeat(300)).erro);
  assert.ok(N.ntConferirMotivo("ab").erro); assert.deepStrictEqual(N.ntConferirMotivo(" erro "), {motivo: "erro"});
  assert.ok(N.ntConferirMotivo("x".repeat(141)).erro);
  assert.strictEqual(N.ntContador("abc"), "3/300");
});
caso("mensagens de erro e chave", () => {
  assert.strictEqual(N.ntMensagemErro(409, "Esta nota foi alterada"), "Esta nota foi alterada");
  assert.ok(N.ntMensagemErro(404).includes("não foi encontrada")); assert.ok(N.ntMensagemErro(403).includes("perfil"));
  const c = N.ntNovaChave(); assert.ok(c.length >= 8 && c.length <= 64 && /^[0-9a-f-]+$/.test(c));
});

let falhas = 0;
casos.forEach(([n, f]) => { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } });
if (falhas) process.exit(1);
console.log("notas_logica: " + casos.length + " casos ok");
