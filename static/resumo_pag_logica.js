"use strict";
/* Resumo da conta, etapa 3B: lógica PURA de recebimento, escopo da seleção, extrato e botões da barra de itens (testada em node:
 * tests/js/resumo_pag_logica.js). Centavos inteiros; nada de float. O servidor confere tudo de novo. NUNCA há campo para número de cartão. */
if (typeof module !== "undefined" && typeof dsFormatarReais === "undefined") Object.assign(globalThis, require("./despesas_logica.js"));   // (só no node)

var RC_FORMAS = [["dinheiro", "Dinheiro"], ["pix", "Pix"], ["cartao", "Cartão"]];
var RC_TIPO_ITEM = {diaria: "Diária", consumo: "Consumo", credito: "Pagamento"};

function rcRotuloForma(f){ var r = RC_FORMAS.filter(function(x){ return x[0] === f; })[0]; return r ? r[1] : f; }
/* Itens a usar: os marcados; se nada estiver marcado, TODOS (extrato e recebimento da conta inteira). */
function rcEscopo(itens, marcados){
  var sel = itens.filter(function(i){ return marcados[i.id]; });
  return {itens: sel.length ? sel : itens, selecionou: sel.length > 0};
}
function rcSomaCobrancas(itens){ return itens.reduce(function(s, i){ return s + (i.tipo === "credito" ? 0 : i.centavos); }, 0); }
function rcSomaPagamentos(itens){ return itens.reduce(function(s, i){ return s + (i.tipo === "credito" ? i.centavos : 0); }, 0); }
/* Valor sugerido: o selecionado (limitado ao saldo) ou, sem seleção, o saldo da conta na tela. */
function rcValorSugerido(escopo, saldo){
  return escopo.selecionou ? Math.max(0, Math.min(rcSomaCobrancas(escopo.itens), saldo)) : Math.max(0, saldo);
}
function rcParcelasValores(valor, n){
  var base = Math.floor(valor / n), resto = valor - base * n, l = [];
  for (var k = 0; k < n; k++) l.push(base + (k < resto ? 1 : 0));
  return l;
}
function rcDescParcelas(valor, n){
  var p = rcParcelasValores(valor, n), k = p.filter(function(x){ return x === p[0]; }).length;
  return k === n ? n + "x de " + dsFormatarReais(p[0]) : k + "x de " + dsFormatarReais(p[0]) + " e " + (n - k) + "x de " + dsFormatarReais(p[n - 1]);
}
/* Código curto (NSU/autorização, referência do Pix): só letras e números. Devolve {valor} ou {erro}. Mensagens nunca repetem o texto. */
function rcCodigo(texto, rotulo, maximo, ehCartao){
  var t = String(texto == null ? "" : texto).trim();
  if (!t) return {valor: null};
  if (ehCartao && ehCartao(t) || /^\d{13,}$/.test(t)) return {erro: "Isto parece um número de cartão. O sistema não guarda números de cartão: apague os números."};
  if (!/^[A-Za-z0-9]+$/.test(t)) return {erro: rotulo + ": use só letras e números, sem espaços."};
  if (t.length > maximo) return {erro: rotulo + ": no máximo " + maximo + " caracteres."};
  return {valor: t};
}
/* Formulário do recebimento -> {erro} ou {corpo} (sem chave/versão: quem envia acrescenta). f.valor e f.recebido são textos de reais. cfg = config do servidor. */
function rcPagConferir(f, saldo, cfg, ehCartao){
  var valor = dsParseReais(f.valor);
  if (valor === null || valor < 1) return {erro: "Informe o valor a receber, por exemplo 150,00."};
  if (valor > saldo) return {erro: "O valor não pode passar do saldo a pagar (" + dsFormatarReais(Math.max(saldo, 0)) + ")."};
  var c = {forma: f.forma, valor_centavos: valor};
  if (f.forma === "dinheiro"){
    if (String(f.recebido || "").trim()){
      var rec = dsParseReais(f.recebido);
      if (rec === null || rec < valor) return {erro: "O valor entregue em dinheiro não pode ser menor que o valor recebido."};
      c.recebido_centavos = rec;
    }
  } else if (f.forma === "pix"){
    var rf = rcCodigo(f.referencia, "Referência do Pix", 32, ehCartao); if (rf.erro) return rf;
    if (rf.valor) c.referencia = rf.valor;
  } else if (f.forma === "cartao"){
    if (cfg.bandeiras.indexOf(f.bandeira) < 0) return {erro: "Escolha a bandeira do cartão."};
    if (f.modalidade !== "credito" && f.modalidade !== "debito") return {erro: "Escolha crédito ou débito."};
    var n = f.modalidade === "credito" && f.parcelamento === "parcelado" ? parseInt(f.parcelas, 10) : 1;
    if (!(n >= 1 && n <= cfg.max_parcelas)) return {erro: "Parcelas: de 2 a " + cfg.max_parcelas + "."};
    if (n > 1 && rcParcelasValores(valor, n)[n - 1] < cfg.parcela_min_centavos) return {erro: "Cada parcela deve ter no mínimo " + dsFormatarReais(cfg.parcela_min_centavos) + "."};
    var nsu = rcCodigo(f.nsu, "Código de autorização", 12, ehCartao); if (nsu.erro) return nsu;
    c.bandeira = f.bandeira; c.modalidade = f.modalidade; c.parcelas = n;
    if (nsu.valor) c.autorizacao = nsu.valor;
  } else return {erro: "Escolha a forma de pagamento."};
  return {corpo: c};
}
/* Motivo obrigatório (estorno, reabertura): 5 a 140 caracteres e sem cara de cartão. */
function rcMotivoConferir(texto, ehCartao){
  var m = dsConferirMotivo(texto);
  if (m.erro) return m;
  if (ehCartao && ehCartao(m.motivo)) return {erro: "Isto parece um número de cartão. O sistema não guarda números de cartão: apague os números."};
  return m;
}
/* Extrato: só o escolhido (ou a conta inteira). saldo só aparece na conta inteira, para não misturar com um recorte. */
function rcExtratoDados(itens, marcados, totais){
  var e = rcEscopo(itens, marcados), cob = rcSomaCobrancas(e.itens), pag = rcSomaPagamentos(e.itens);
  var saldo = !e.selecionou && totais && typeof totais.saldo_centavos === "number" ? totais.saldo_centavos : null;
  return {parcial: e.selecionou, linhas: e.itens.map(function(i){ return {tipo: RC_TIPO_ITEM[i.tipo] || i.tipo, descricao: i.descricao, valor: dsFormatarReais(i.tipo === "credito" ? -i.centavos : i.centavos)}; }),
    total: cob, pagamentos: pag, saldo: saldo};
}
/* Botões da barra de itens. c = {veiculo, despesas, receber, estornar, transferir, fechar, reabrir, aberta (conta), saldo, ativa}. */
function rcBarraBotoes(c){
  var b = [];
  if (!c.ativa) return b;
  if (c.veiculo) b.push("placa");
  if (c.despesas){ b.push("extrato"); if (c.aberta && c.receber) b.push("receber"); if (c.aberta && c.estornar) b.push("estornar");
    if (c.aberta && c.transferir) b.push("transferir"); b.push("info");
    if (c.aberta && c.fechar && c.saldo === 0) b.push("fechar"); if (!c.aberta && c.reabrir) b.push("reabrir_conta"); }
  return b;
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {rcEscopo: rcEscopo, rcSomaCobrancas: rcSomaCobrancas, rcSomaPagamentos: rcSomaPagamentos, rcValorSugerido: rcValorSugerido,
    rcParcelasValores: rcParcelasValores, rcDescParcelas: rcDescParcelas, rcCodigo: rcCodigo, rcPagConferir: rcPagConferir,
    rcMotivoConferir: rcMotivoConferir, rcExtratoDados: rcExtratoDados, rcBarraBotoes: rcBarraBotoes, rcRotuloForma: rcRotuloForma};
}
