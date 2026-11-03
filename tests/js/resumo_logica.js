"use strict";
// Testa a lógica pura de static/resumo_logica.js. Roda com: node tests/js/resumo_logica.js
const assert = require("assert");
const path = require("path");
const R = require(path.join(__dirname, "..", "..", "static", "resumo_logica.js"));
const casos = [];
const caso = (nome, f) => casos.push([nome, f]);
const RES = {id: 123, a: "302", nome: "Antonio", i: "2026-10-29", f: "2026-10-31", n: 2, p: "pago", tipo: "socio", grupo: "", status: "ativa", versao: 3, diaria_centavos: 35000};
const TOT = {despesas_centavos: 8750, noites: 2, diaria_centavos: 35000, diarias_centavos: 70000, estadia_centavos: 78750};

caso("situação com texto sempre junto da cor", () => {
  const s = (i, f, h, st) => R.rcSituacao({i, f, status: st || "ativa"}, h);
  assert.strictEqual(s("2026-10-29", "2026-10-31", "2026-10-29").chave, "chegando");
  assert.strictEqual(s("2026-10-29", "2026-10-31", "2026-10-30").rotulo, "Hospedado");
  assert.strictEqual(s("2026-10-29", "2026-10-31", "2026-10-31").chave, "saindo");
  assert.strictEqual(s("2026-10-29", "2026-10-31", "2026-11-01").chave, "encerrada");
  assert.strictEqual(s("2026-11-05", "2026-11-07", "2026-10-31").chave, "futura");
  assert.strictEqual(s("2026-10-29", "2026-10-31", "2026-10-30", "cancelada").rotulo, "Cancelada");
});
caso("período, noites e títulos", () => {
  assert.strictEqual(R.rcPeriodo(RES), "In 29/10/2026 (14h) | Out 31/10/2026 (12h) | 2 noites");
  assert.strictEqual(R.rcNoites("2026-12-31", "2027-01-01"), 1);
  assert.strictEqual(R.rcTitulo(RES), "Apartamento 302 · Reserva #123");
  assert.strictEqual(R.rcTipoGrupo(RES), "Sócio do clube");
  assert.strictEqual(R.rcTipoGrupo({tipo: null, grupo: "Turma Azul"}), "Tipo não informado · Grupo Turma Azul");
});
caso("botões por perfil, na ordem da referência", () => {
  const adm = {editar: 1, editarPag: 1, cancelar: 1, reativar: 1, historico: 1, despesas: 1, liberar: 1, ficha: 1, checkin: 1, reverter: 1};
  assert.deepStrictEqual(R.rcBotoes(adm, false, "pendente"), ["editar", "hospedes", "trocar", "liberar", "ficha", "checkin", "cancelar", "imprimir", "historico", "despesas"]);
  assert.deepStrictEqual(R.rcBotoes(adm, false, "efetuado"), ["editar", "hospedes", "trocar", "liberar", "ficha", "reverter", "cancelar", "imprimir", "historico", "despesas"]);
  assert.deepStrictEqual(R.rcBotoes(adm, false, "conta_aberta"), ["editar", "hospedes", "trocar", "reabrir", "ficha", "cancelar", "imprimir", "historico", "despesas"]);
  const rec = {editarPag: 1, despesas: 1, ficha: 1, checkin: 1};                                                         // recepção: sem reverter nem liberar
  assert.deepStrictEqual(R.rcBotoes(rec, false, "pendente"), ["editar", "hospedes", "ficha", "checkin", "imprimir", "despesas"]);
  assert.deepStrictEqual(R.rcBotoes(rec, false, "efetuado"), ["editar", "hospedes", "ficha", "imprimir", "despesas"]);
  assert.deepStrictEqual(R.rcBotoes({despesas: 1}, false, "pendente"), ["hospedes", "imprimir", "despesas"]);            // diretoria: só ver
  assert.deepStrictEqual(R.rcBotoes({}, false, "pendente"), ["hospedes", "imprimir"]);                                    // consulta
  assert.deepStrictEqual(R.rcBotoes(adm, true, "pendente"), ["reativar", "imprimir", "historico"]);                      // cancelada
  assert.deepStrictEqual(R.rcBotoes({}, true), ["imprimir"]);
});
caso("rótulos acessíveis completos e categoria pelo andar", () => {
  assert.strictEqual(R.rcAriaBotao("trocar", RES), "Transferir o apartamento 302 da reserva de Antonio");
  assert.strictEqual(R.rcAriaBotao("editar", RES), "Alterar estadia (apartamento 302, hóspede Antonio)");
  assert.strictEqual(R.rcAriaBotao("liberar", RES), "Liberar o apartamento e deixar a conta aberta (apartamento 302, hóspede Antonio)");
  ["editar", "hospedes", "trocar", "liberar", "reabrir", "ficha", "checkin", "reverter", "placa"].forEach(id => assert.ok(R.RC_ROTULO[id] && R.RC_CURTO[id], id));
  assert.deepStrictEqual(["101", "204", "307", "Chalé C"].map(R.rcAndar), ["Térreo", "2º andar", "3º andar", "Chalés"]);
  assert.strictEqual(R.rcTituloCartao(RES), "Apartamento 302 - 3º andar");
  assert.strictEqual(R.rcEstado({estado_hospedagem: "conta_aberta"}), "Apartamento liberado, conta aberta");
  assert.strictEqual(R.rcEstado({}), "Check-in pendente");
});
caso("subtotais: total só com os dois acessos e a diária", () => {
  const completo = R.rcSubtotais(RES, TOT, {valores: true, despesas: true});
  assert.deepStrictEqual(completo.linhas.map(l => l.id), ["diarias", "despesas"]);
  assert.strictEqual(completo.linhas[0].texto, "R$ 700,00 (2 x R$ 350,00)"); assert.strictEqual(completo.total, "R$ 787,50");
  const so_valores = R.rcSubtotais(RES, null, {valores: true, despesas: false});
  assert.deepStrictEqual(so_valores.linhas.map(l => l.id), ["diarias"]); assert.strictEqual(so_valores.total, null);
  const so_desp = R.rcSubtotais(Object.assign({}, RES, {diaria_centavos: undefined}), TOT, {valores: false, despesas: true});
  assert.deepStrictEqual(so_desp.linhas.map(l => l.id), ["despesas"]); assert.strictEqual(so_desp.total, null);
  const sem_diaria = R.rcSubtotais(Object.assign({}, RES, {diaria_centavos: null}), TOT, {valores: true, despesas: true});
  assert.strictEqual(sem_diaria.linhas[0].texto, "Diária não informada"); assert.strictEqual(sem_diaria.total, null);
  const nada = R.rcSubtotais(Object.assign({}, RES, {diaria_centavos: undefined}), null, {valores: false, despesas: false});
  assert.deepStrictEqual(nada, {linhas: [], total: null});
  assert.ok(!JSON.stringify(nada).includes("R$"));
});
caso("azulejos: sem permissão nem existem; Evento e Crédito são 'Em breve' e desabilitados", () => {
  assert.deepStrictEqual(R.rcAzulejos(RES, TOT, {valores: true, despesas: true}).map(a => a.id), ["diaria", "evento", "consumo", "credito"]);
  assert.deepStrictEqual(R.rcAzulejos(RES, TOT, {valores: false, despesas: true}).map(a => a.id), ["evento", "consumo", "credito"]);
  assert.deepStrictEqual(R.rcAzulejos(RES, null, {valores: false, despesas: false}), []);
  const todos = R.rcAzulejos(RES, TOT, {valores: true, despesas: true});
  ["evento", "credito"].forEach(id => { const a = todos.find(x => x.id === id); assert.strictEqual(a.valor, "Em breve"); assert.ok(a.desabilitado); });
  assert.strictEqual(todos[0].valor, "R$ 700,00"); assert.strictEqual(todos[0].nota, "2 noites x R$ 350,00");
  assert.strictEqual(R.rcAzulejos(Object.assign({}, RES, {diaria_centavos: null}), null, {valores: true})[0].valor, "Não informada");
});
caso("itens selecionáveis e total selecionado", () => {
  const desp = [{id: 5, tipo: "lancamento", descricao: "Água", quantidade: 2, total_centavos: 1600, estornado: false},
    {id: 6, tipo: "lancamento", descricao: "Suco", quantidade: 1, total_centavos: 900, estornado: true},
    {id: 7, tipo: "estorno", descricao: "Suco", quantidade: 1, total_centavos: -900, estornado: false},
    {id: 8, tipo: "lancamento", descricao: "Cerveja", quantidade: 1, total_centavos: 1200, estornado: false}];
  const it = R.rcItensConta(RES, desp, {valores: true, despesas: true});
  assert.deepStrictEqual(it.map(i => i.id), ["diaria", "d5", "d8"]);            // estornados e estornos ficam fora
  assert.strictEqual(it[1].descricao, "Água (x2)");
  assert.strictEqual(R.rcTotalSelecionado(it, {}), 0);
  assert.strictEqual(R.rcTotalSelecionado(it, {diaria: true, d8: true}), 70000 + 1200);
  assert.deepStrictEqual(R.rcEstadoAzulejo(it, {d5: true}, "consumo"), {marcado: false, parcial: true, vazio: false});
  assert.deepStrictEqual(R.rcEstadoAzulejo(it, {d5: true, d8: true}, "consumo"), {marcado: true, parcial: false, vazio: false});
  assert.ok(R.rcEstadoAzulejo(it, {}, "evento").vazio);
  assert.deepStrictEqual(R.rcItensConta(RES, desp, {valores: false, despesas: false}), []);        // sem permissão não há itens
  assert.deepStrictEqual(R.rcItensConta(Object.assign({}, RES, {diaria_centavos: null}), null, {valores: true, despesas: true}), []);
  assert.deepStrictEqual(R.rcItensConta(Object.assign({}, RES, {diaria_centavos: 0}), null, {valores: true, despesas: true}), []);   // diária zerada: sem linha de R$ 0,00 para marcar
});
caso("placa: normaliza como o servidor", () => {
  assert.deepStrictEqual(R.rcPlacaNormalizar(" abc-1234 "), {placa: "ABC1234"});
  assert.deepStrictEqual(R.rcPlacaNormalizar("abc1d23"), {placa: "ABC1D23"});
  assert.deepStrictEqual(R.rcPlacaNormalizar("  "), {vazia: true});
  ["AB-1234", "ABCD123", "ABC12345", "123ABCD", "ABC1DD3"].forEach(v => assert.ok(R.rcPlacaNormalizar(v).erro, v));
});
caso("apartamentos livres para a troca", () => {
  const lista = [RES, {id: 9, a: "303", i: "2026-10-30", f: "2026-11-02"}, {id: 8, a: "304", i: "2026-10-31", f: "2026-11-02"}];
  const livres = R.rcLivres(lista, RES, ["301", "302", "303", "304", "104"], {"104": true});
  assert.deepStrictEqual(livres, ["301", "304"]);        // 303 conflita; 304 começa quando a reserva sai; 104 interditado; o próprio apto fica fora
});
caso("motivo, mudança e mensagens", () => {
  assert.ok(R.rcConferirMotivo("  ").erro); assert.deepStrictEqual(R.rcConferirMotivo(" desistiu "), {motivo: "desistiu"}); assert.ok(R.rcConferirMotivo("x".repeat(301)).erro);
  assert.strictEqual(R.rcMudou({versao: 3, status: "ativa"}, {versao: 3, status: "ativa"}), false);
  assert.strictEqual(R.rcMudou({versao: 3, status: "ativa"}, {versao: 4, status: "ativa"}), true);
  assert.strictEqual(R.rcMudou({versao: 3, status: "ativa"}, null), true);
  assert.ok(R.rcMensagemErro(403).includes("perfil")); assert.strictEqual(R.rcMensagemErro(409, "Conflito"), "Conflito");
});

let falhas = 0;
casos.forEach(([n, f]) => { try { f(); } catch (e) { falhas++; console.error("FALHOU: " + n + "\n  " + e.message); } });
if (falhas) process.exit(1);
console.log("resumo_logica: " + casos.length + " casos ok");
