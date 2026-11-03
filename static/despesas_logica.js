"use strict";
/* Despesas: lógica PURA do diálogo (sem DOM, sem rede; testada em node). Dinheiro sempre em CENTAVOS INTEIROS:
 * nada de float, nada de somar números quebrados. O servidor recalcula tudo; aqui só se lê, se formata e se confere. */

var DS_CATEGORIAS = [["restaurante", "Restaurante"], ["bar", "Bar / frigobar"], ["lavanderia", "Lavanderia"], ["outros", "Outros"]];
var DS_MAX_UNIT = 1000000;           // R$ 10.000,00 (igual ao servidor)
var DS_MAX_QTD = 99;

/* "12,50" | "12.50" | "1.234,56" | "R$ 8" -> centavos inteiros. Vazio, negativo, letras ou 3+ casas -> null. */
function dsParseReais(texto){
  var t = String(texto == null ? "" : texto).replace(/R\$/gi, "").replace(/\s+/g, "");
  if (!/^[\d.,]+$/.test(t)) return null;
  var m = /^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/.exec(t) ||                 // 1.234,56 | 8,5 | 8
          /^(\d+)\.(\d{1,2})$/.exec(t);                                          // 8.50 (ponto como decimal)
  if (!m) return null;
  var inteiro = m[1].replace(/\./g, "");
  if (inteiro.length > 7) return null;
  return parseInt(inteiro, 10) * 100 + parseInt(((m[2] || "") + "00").slice(0, 2), 10);
}
/* 12345 -> "R$ 123,45"; 105000 -> "R$ 1.050,00"; negativo -> "-R$ 8,00". */
function dsFormatarReais(centavos){
  var neg = centavos < 0, c = Math.abs(centavos);
  var inteiro = String(Math.floor(c / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return (neg ? "-" : "") + "R$ " + inteiro + "," + String(c % 100).padStart(2, "0");
}
/* Quantidade inteira de 1 a 99 (texto do campo) ou null. */
function dsParseQuantidade(texto){
  var t = String(texto == null ? "" : texto).trim();
  if (!/^\d{1,3}$/.test(t)) return null;
  var n = parseInt(t, 10);
  return n >= 1 && n <= DS_MAX_QTD ? n : null;
}
/* Confere o formulário; devolve {erro} ou {dados, total} (total só para mostrar: o servidor calcula o de verdade). */
function dsConferirFormulario(f){
  var desc = String(f.descricao || "").trim();
  var qtd = dsParseQuantidade(f.quantidade), unit = dsParseReais(f.valor);
  if (desc.length < 2) return {erro: "Informe a descrição (pelo menos 2 letras)."};
  if (desc.length > 80) return {erro: "Descrição grande demais (máximo 80 caracteres)."};
  if (qtd === null) return {erro: "A quantidade deve ser um número inteiro de 1 a " + DS_MAX_QTD + "."};
  if (unit === null || unit < 1) return {erro: "Informe o valor unitário, por exemplo 8,50."};
  if (unit > DS_MAX_UNIT) return {erro: "Valor acima do máximo permitido (" + dsFormatarReais(DS_MAX_UNIT) + ")."};
  return {dados: {categoria: f.categoria, descricao: desc, quantidade: qtd, valor_unit_centavos: unit}, total: qtd * unit};
}
function dsConferirMotivo(texto){
  var t = String(texto || "").trim();
  return t.length < 5 ? {erro: "Explique o motivo (pelo menos 5 letras)."} : (t.length > 140 ? {erro: "Motivo grande demais (máximo 140 caracteres)."} : {motivo: t});
}
/* Chave contra duplo clique: gerada ao abrir o formulário e trocada a cada lançamento bem-sucedido (8 a 64 caracteres). */
function dsNovaChave(){
  var c = typeof crypto !== "undefined" ? crypto : null;
  if (c && c.randomUUID) return c.randomUUID();
  var b = new Uint8Array(16);
  if (c && c.getRandomValues) c.getRandomValues(b); else for (var i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  return Array.prototype.map.call(b, function(x){ return (x < 16 ? "0" : "") + x.toString(16); }).join("");
}
/* "2026-10-29 09:05:00" -> "29/10 09:05" */
function dsDataHora(em){
  var m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(String(em || ""));
  return m ? m[3] + "/" + m[2] + " " + m[4] + ":" + m[5] : String(em || "");
}
function dsRotuloCategoria(cat){
  var r = DS_CATEGORIAS.filter(function(c){ return c[0] === cat; })[0];
  return r ? r[1] : cat;
}
/* Situação de uma linha: 'estornado' (lançamento já estornado), 'estorno' (a linha negativa) ou 'normal'. */
function dsSituacaoLinha(it){ return it.tipo === "estorno" ? "estorno" : (it.estornado ? "estornado" : "normal"); }
/* Mensagem para o balcão a partir do status HTTP e do texto do servidor. */
function dsMensagemErro(status, texto, acao){
  if (status === 403) return acao === "estornar" ? "Seu perfil não pode estornar lançamentos." : "Seu perfil não pode lançar despesas.";
  if (status === 404) return "Esta reserva ou lançamento não foi encontrado. Feche e abra de novo.";
  return texto || "Não foi possível concluir. Tente de novo.";
}
/* Linhas do bloco de totais [rótulo, valor] (a diária e o total da estadia só existem para quem recebeu esses campos). */
function dsLinhasTotais(t){
  var l = [];
  if (t.diaria_centavos !== undefined){
    if (t.diaria_centavos === null) l.push(["Diária", "Diária não informada"]);
    else l.push(["Diárias", dsFormatarReais(t.diaria_centavos) + " x " + t.noites + (t.noites === 1 ? " noite" : " noites") + " = " + dsFormatarReais(t.diarias_centavos)]);
  }
  l.push(["Despesas", dsFormatarReais(t.despesas_centavos)]);
  if (t.estadia_centavos !== undefined) l.push(["Total da estadia", dsFormatarReais(t.estadia_centavos)]);
  return l;
}
function dsDescricaoLancado(dados){ return "Lançado: " + dados.quantidade + " x " + dados.descricao + " " + dsFormatarReais(dados.valor_unit_centavos) + "."; }

if (typeof module !== "undefined" && module.exports){
  module.exports = {dsParseReais: dsParseReais, dsFormatarReais: dsFormatarReais, dsParseQuantidade: dsParseQuantidade,
    dsConferirFormulario: dsConferirFormulario, dsConferirMotivo: dsConferirMotivo, dsNovaChave: dsNovaChave, dsDataHora: dsDataHora,
    dsRotuloCategoria: dsRotuloCategoria, dsSituacaoLinha: dsSituacaoLinha, dsMensagemErro: dsMensagemErro,
    dsLinhasTotais: dsLinhasTotais, dsDescricaoLancado: dsDescricaoLancado, DS_CATEGORIAS: DS_CATEGORIAS};
}
