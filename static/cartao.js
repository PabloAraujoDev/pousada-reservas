"use strict";
// Aviso (só aviso: quem recusa é o servidor) de número de cartão nos campos de texto do formulário da reserva.
// A regra espelha pousada/cartao.py: 13 a 19 dígitos com Luhn, ou o desenho 4-4-4-x. Nunca repete o número.

var CT_INVISIVEIS = /[­​-‍⁠﻿]/g;
var CT_CORRIDO = /(?<!\d)\d{13,19}(?!\d)/g;
var CT_CADEIA = /(?<!\d)\d{4,}(?:[ \-.]\d{4,})+(?!\d)/g;
var CT_VISUAL = /(?<!\d)\d{4}([ \-.])\d{4}\1\d{4}\1\d{1,7}(?!\d)/;

function ctLuhn(digitos){
  var soma = 0;
  for (var k = 0; k < digitos.length; k++){
    var d = +digitos.charAt(digitos.length - 1 - k);
    if (k % 2){ d = d * 2; if (d > 9) d -= 9; }
    soma += d;
  }
  return soma % 10 === 0;
}

function ctCadeiaSuspeita(cadeia){
  var seps = {}, n = 0;
  cadeia.replace(/[ \-.]/g, function(c){ if (!seps[c]){ seps[c] = 1; n++; } return c; });
  var dig = cadeia.replace(/\D/g, "");
  return n === 1 && dig.length >= 13 && dig.length <= 19 && ctLuhn(dig);
}

function ctContemNumeroCartao(texto){
  if (typeof texto !== "string") return false;
  var t = texto.replace(CT_INVISIVEIS, "").normalize("NFKC");
  if (CT_VISUAL.test(t)) return true;
  return (t.match(CT_CORRIDO) || []).some(ctLuhn) || (t.match(CT_CADEIA) || []).some(ctCadeiaSuspeita);
}

function ctAtualizar(){
  var aviso = document.getElementById("avisoCartao");
  if (!aviso) return;
  var suspeito = ["fnome", "fgrupo", "fextras", "fo"].some(function(id){
    var c = document.getElementById(id);
    return c && ctContemNumeroCartao(c.value);
  });
  aviso.classList.toggle("oculto", !suspeito);
}

if (typeof document !== "undefined"){
  ["fnome", "fgrupo", "fextras", "fo"].forEach(function(id){
    var c = document.getElementById(id);
    if (c) c.addEventListener("input", ctAtualizar);
  });
  var ctForm = document.getElementById("form");
  if (ctForm) ctForm.addEventListener("reset", function(){ setTimeout(ctAtualizar, 0); });
  document.addEventListener("pousada:form-aberto", ctAtualizar);
}
if (typeof module !== "undefined" && module.exports) module.exports = {ctContemNumeroCartao: ctContemNumeroCartao};
