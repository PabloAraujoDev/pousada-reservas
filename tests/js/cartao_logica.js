"use strict";
// Testa static/cartao.js (aviso de cartão no navegador) com os mesmos casos do servidor. Roda com: node tests/js/cartao_logica.js
const assert = require("assert");
const path = require("path");
const {ctContemNumeroCartao: f} = require(path.join(__dirname, "..", "..", "static", "cartao.js"));

const recusa = ["Cartão 4111 1111 1111 1111 val 04/28", "4111-1111-1111-1111", "4111111111111111", "cartao4111111111111111",
  "4000 1234 5678 9010", "4000 1234 5678 9", "3782 822463 10005", "４１１１ １１１１ １１１１ １１１１", "4111​1111​1111​1111"];
const aceita = ["final 1234", "5550 ....", "**** 1234", "123.456.789-09", "(11) 98765-4321", "1234567890123", "31/10/2026",
  "2026-10-31 2026-11-02", "Pago no cartão (final 4242)", "11 98765-4321 11 98765-4321", ""];
recusa.forEach(t => assert.strictEqual(f(t), true, "deveria recusar: " + t));
aceita.forEach(t => assert.strictEqual(f(t), false, "deveria aceitar: " + t));
assert.strictEqual(f(null), false);
console.log("cartao_logica: " + (recusa.length + aceita.length + 1) + " casos ok");
