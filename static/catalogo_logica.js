"use strict";
/* Catálogo de itens e relatório de consumo: lógica PURA (sem DOM, sem rede; testada em node). Dinheiro em CENTAVOS INTEIROS. */

var CG_DS = (typeof module !== "undefined" && module.exports) ? require("./despesas_logica.js")
  : {dsParseReais: dsParseReais, dsFormatarReais: dsFormatarReais, dsQuando: dsQuando};
var CG_ROTULO_ACAO = {criado: "Cadastrado", editado: "Editado", desativado: "Desativado", reativado: "Reativado"};
var CG_ROTULO_CAMPO = {categoria: "categoria", grupo: "grupo", descricao: "descrição", preco_centavos: "valor", ativo: "situação"};

/* Formulário do item -> {erro} ou {dados} (o servidor confere tudo de novo). */
function cgConferirItem(f){
  var desc = String(f.descricao || "").trim(), grupo = String(f.grupo || "").trim(), preco = CG_DS.dsParseReais(f.preco);
  if (!f.categoria) return {erro: "Escolha a categoria."};
  if (desc.length < 2) return {erro: "Informe a descrição (pelo menos 2 letras)."};
  if (desc.length > 80) return {erro: "Descrição grande demais (máximo 80 caracteres)."};
  if (grupo && (grupo.length < 2 || grupo.length > 40)) return {erro: "O grupo deve ter de 2 a 40 caracteres (ou ficar vazio)."};
  if (preco === null || preco < 1) return {erro: "Informe o valor, por exemplo 8,50."};
  if (preco > 1000000) return {erro: "Valor acima do máximo permitido (" + CG_DS.dsFormatarReais(1000000) + ")."};
  return {dados: {categoria: f.categoria, grupo: grupo, descricao: desc, preco_centavos: preco}};
}
function cgValorDoLog(campo, v){
  if (campo === "preco_centavos") return CG_DS.dsFormatarReais(v);
  if (campo === "ativo") return v ? "ativo" : "desativado";
  return v === "" || v == null ? "(vazio)" : String(v);
}
/* Uma entrada do log do item -> texto: "Editado por admin em 29/10 09:05:12: valor: R$ 5,00 -> R$ 7,00". */
function cgTextoLog(l){
  var q = CG_DS.dsQuando(l.em), partes = [];
  Object.keys(l.depois || {}).forEach(function(k){
    var a = l.antes ? l.antes[k] : undefined, d = l.depois[k];
    if (l.antes && a === d) return;
    partes.push((CG_ROTULO_CAMPO[k] || k) + ": " + (l.antes ? cgValorDoLog(k, a) + " -> " : "") + cgValorDoLog(k, d));
  });
  return (CG_ROTULO_ACAO[l.acao] || l.acao) + " por " + l.por + " em " + q.data + " " + q.hora + (partes.length ? ": " + partes.join("; ") : "");
}
/* Linha do relatório de consumo -> {quando, hora, obs}: estorno e transferência ficam marcados; item avulso também. */
function cnObservacao(l){
  if (l.transferencia_id) return l.tipo === "estorno" ? "Transferido para outra conta" : "Recebido por transferência";
  if (l.tipo === "estorno") return "Estorno: " + l.motivo;
  return l.item_id ? "" : "Avulso/antigo";
}
function cnPeriodoValido(ini, fim){
  if (!/^\d{4}-\d{2}-\d{2}$/.test(ini) || !/^\d{4}-\d{2}-\d{2}$/.test(fim)) return "Informe as duas datas.";
  if (fim < ini) return "A data final não pode ser antes da inicial.";
  if ((Date.parse(fim) - Date.parse(ini)) / 86400000 > 93) return "Período grande demais (máximo 93 dias).";
  return "";
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {cgConferirItem: cgConferirItem, cgTextoLog: cgTextoLog, cnObservacao: cnObservacao, cnPeriodoValido: cnPeriodoValido};
}
