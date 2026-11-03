"use strict";
/* Ficha de check-in no padrão da FNRH (Ficha Nacional de Registro de Hóspedes), A4 em retrato, para preencher à mão.
 * Os campos informados saem preenchidos; os que faltam saem em branco com a linha para escrever. MODELO DE APOIO: a adequação ao
 * modelo oficial da FNRH/Cadastur é decisão do clube (veja docs/OPERACAO.md). Campos usados: nome, documento, nacionalidade,
 * procedência, destino, data de nascimento, profissão, motivo da viagem, meio de transporte e placa. Nada além disso.
 * A parte pura (fnrhLinhas) é testada em node; a montagem usa só createElement/textContent (dados pessoais nunca viram HTML). */

var FNRH_PESSOA = [["Nome completo", "nome"], ["Documento (tipo e número)", "documento"], ["Data de nascimento", "nascimento"],
  ["Nacionalidade", "nacionalidade"], ["Profissão", "profissao"], ["Procedência (cidade / UF / país)", "procedencia"],
  ["Destino (próxima cidade / UF / país)", "destino"]];
var FNRH_TIPO = {adulto: "Adulto", crianca: "Criança"};

function fnrhData(s){ var p = String(s || "").split("-"); return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : ""; }
function fnrhValor(chave, v){ return v == null || v === "" ? "" : chave === "nascimento" ? fnrhData(v) : String(v); }
/* d = resposta de POST /ficha. Devolve a estrutura da folha: campos da hospedagem e uma ficha por pessoa (as não cadastradas, em branco). */
function fnrhLinhas(d, nomeTitular){
  var r = d.reserva;
  var hosp = [["Apartamento", r.a], ["Entrada (a partir das 14h)", fnrhData(r.i)], ["Saída (até as 12h)", fnrhData(r.f)],
    ["Número de pessoas", String(r.n)], ["Placa do veículo", r.placa || ""], ["Meio de transporte", ""], ["Motivo da viagem", ""]];
  var pessoas = [{titulo: "Hóspede titular", tipo: FNRH_TIPO[d.titular.tipo] || "", dados: d.titular, nome: nomeTitular || d.titular.nome}];
  d.acompanhantes.forEach(function(a, k){ pessoas.push({titulo: "Acompanhante " + (k + 1), tipo: FNRH_TIPO[a.tipo] || "", dados: a, nome: a.nome}); });
  for (var k = 0; k < d.em_branco; k++) pessoas.push({titulo: "Acompanhante " + (d.acompanhantes.length + k + 1), tipo: "", dados: {}, nome: ""});
  pessoas.forEach(function(p){
    p.campos = FNRH_PESSOA.map(function(c){ return [c[0], c[1] === "nome" ? (p.nome || "") : fnrhValor(c[1], p.dados[c[1]])]; });
  });
  return {hospedagem: hosp.map(function(c){ return [c[0], c[1] == null ? "" : String(c[1])]; }), pessoas: pessoas, emitido: r.emitido_em};
}

function fnrhCampo(rotulo, valor){
  var c = document.createElement("div"); c.className = "fnrh-campo";
  var l = document.createElement("span"); l.className = "fnrh-rot"; l.textContent = rotulo;
  var v = document.createElement("span"); v.className = "fnrh-val"; v.textContent = valor;     // em branco = linha para escrever à mão
  c.appendChild(l); c.appendChild(v);
  return c;
}
function fnrhBloco(titulo, campos, classe){
  var b = document.createElement("section"); b.className = "fnrh-bloco " + (classe || "");
  var h = document.createElement("h3"); h.textContent = titulo; b.appendChild(h);
  var g = document.createElement("div"); g.className = "fnrh-grade";
  campos.forEach(function(c){ g.appendChild(fnrhCampo(c[0], c[1])); });
  b.appendChild(g);
  return b;
}
function fnrhMontar(host, d){
  var f = fnrhLinhas(d, d.titular && d.titular.nome), t;
  host.textContent = "";
  t = document.createElement("p"); t.className = "fnrh-pousada"; t.textContent = "Pousada Boa Esperança - Clube dos Oficiais da PM MG"; host.appendChild(t);
  t = document.createElement("h2"); t.className = "fnrh-titulo"; t.textContent = "Ficha de check-in (modelo FNRH)"; host.appendChild(t);
  t = document.createElement("p"); t.className = "fnrh-emitido"; t.textContent = "Emitida em " + fnrhData(f.emitido.slice(0, 10)) + " " + f.emitido.slice(11, 16); host.appendChild(t);
  host.appendChild(fnrhBloco("Hospedagem", f.hospedagem, "fnrh-hosp"));
  f.pessoas.forEach(function(p){ host.appendChild(fnrhBloco(p.titulo + (p.tipo ? " (" + p.tipo + ")" : ""), p.campos, "fnrh-pessoa")); });
  t = document.createElement("div"); t.className = "fnrh-ass";
  ["Assinatura do hóspede", "Recepção"].forEach(function(x){ var s = document.createElement("span"); s.textContent = x; t.appendChild(s); });
  host.appendChild(t);
  t = document.createElement("p"); t.className = "fnrh-nota"; t.textContent = "Modelo de apoio ao registro de hóspedes. Dados pessoais: guarde e descarte esta ficha com segurança.";
  host.appendChild(t);
}
if (typeof module !== "undefined" && module.exports) module.exports = {fnrhLinhas: fnrhLinhas, fnrhData: fnrhData, FNRH_PESSOA: FNRH_PESSOA};
