"use strict";
/* Resumo da conta, etapa 3B: Receber pagamento (cifrão). Leva o que estiver selecionado; sem seleção fecha o saldo da conta na tela.
 * O valor é editável (recebimento parcial); nunca passa do saldo (o servidor confere de novo, com a versão da conta e a chave contra
 * duplo clique). Formas do clube: dinheiro, Pix e cartão. NUNCA existe campo para número do cartão: só bandeira, modalidade, parcelas
 * e um código curto de autorização/NSU (letras e números, até 12). Só createElement/textContent. */

function rcCampo(rotulo, el, dica){
  var c = ntEl("div", "campo"), l = ntEl("label", null, rotulo); el.id = el.id || "rcPg" + (++rcCampo.seq); l.htmlFor = el.id;
  c.appendChild(l); c.appendChild(el); if (dica) c.appendChild(ntEl("p", "suave rc-dica", dica));
  return c;
}
rcCampo.seq = 0;
function rcSelect(opcoes){
  var s = ntEl("select"); opcoes.forEach(function(o){ var e = ntEl("option", null, o[1]); e.value = o[0]; s.appendChild(e); });
  return s;
}
function rcReaisCampo(c){ return Math.floor(c / 100) + "," + String(c % 100).padStart(2, "0"); }
function rcTexto(max, ac){ var i = ntEl("input"); i.type = "text"; i.maxLength = max; i.autocomplete = "off"; if (ac) i.setAttribute("autocapitalize", "off"); return i; }

function rcReceber(){
  var escopo = rcEscopo(rcItensDaConta().filter(function(i){ return i.tipo !== "credito"; }), rc.marcados);
  var saldo = (rc.totais && rc.totais.saldo_centavos) || 0, cfg = rc.pagcfg, chave = dsNovaChave();
  if (saldo <= 0){ aviso("Não há saldo a receber nesta conta."); return; }
  var tit = rcAbrirPainel("Receber pagamento", function(p){
    p.appendChild(ntEl("p", "suave", "Saldo a pagar: " + dsFormatarReais(saldo) + ". " + (escopo.selecionou ? "Valor sugerido: o que está selecionado (" + rcPlural(escopo.itens.length, "item", "itens") + ")." : "Nada selecionado: o valor sugerido fecha a conta inteira.") +
      " O valor pode ser menor (recebimento parcial), nunca maior que o saldo."));
    var forma = rcSelect(RC_FORMAS), valor = rcTexto(14), rec = rcTexto(14), ref = rcTexto(32, true), nsu = rcTexto(12, true);
    var band = rcSelect(cfg.bandeiras.map(function(b){ return [b, b]; })), mod = rcSelect([["credito", "Crédito"], ["debito", "Débito"]]);
    var parc = rcSelect([["avista", "À vista"], ["parcelado", "Parcelado"]]), np = ntEl("input");
    np.type = "number"; np.min = 2; np.max = cfg.max_parcelas; np.value = 2; np.inputMode = "numeric";
    valor.value = rcReaisCampo(rcValorSugerido(escopo, saldo)); valor.inputMode = rec.inputMode = "decimal";
    var cValor = rcCampo("Valor a receber (R$)", valor), cRec = rcCampo("Valor entregue pelo hóspede (R$, opcional)", rec), troco = ntEl("p", "rc-dica", "");
    var cRef = rcCampo("Referência do Pix (opcional, só letras e números)", ref), cBand = rcCampo("Bandeira", band), cMod = rcCampo("Modalidade", mod);
    var cParc = rcCampo("Pagamento no crédito", parc), cNp = rcCampo("Número de parcelas (2 a " + cfg.max_parcelas + ")", np), info = ntEl("p", "rc-dica", "");
    var cNsu = rcCampo("Código de autorização / NSU da maquineta (opcional)", nsu, "Só letras e números. Nunca digite o número do cartão.");
    [cValor, forma.parentNode, cRec, troco, cRef, cBand, cMod, cParc, cNp, info, cNsu].forEach(function(e){ if (e) p.appendChild(e); });
    p.insertBefore(rcCampo("Forma de pagamento", forma), cValor);
    function mostrar2(){
      var f = forma.value, cr = f === "cartao" && mod.value === "credito", pa = cr && parc.value === "parcelado";
      [[cRec, f === "dinheiro"], [troco, f === "dinheiro"], [cRef, f === "pix"], [cBand, f === "cartao"], [cMod, f === "cartao"], [cParc, cr], [cNp, pa], [info, pa], [cNsu, f === "cartao"]].forEach(function(x){ x[0].classList.toggle("oculto", !x[1]); });
      var v = dsParseReais(valor.value), r = dsParseReais(rec.value), n = parseInt(np.value, 10);
      troco.textContent = v !== null && r !== null && r >= v ? "Troco: " + dsFormatarReais(r - v) + " (informativo)" : "";
      info.textContent = pa && v !== null && n >= 2 && n <= cfg.max_parcelas ? rcDescParcelas(v, n) : "";
    }
    [forma, mod, parc].forEach(function(e){ e.addEventListener("change", mostrar2); });
    [valor, rec, np].forEach(function(e){ e.addEventListener("input", mostrar2); });
    var bt = rcBotoesPainel(function(){
      var c = rcPagConferir({forma: forma.value, valor: valor.value, recebido: rec.value, referencia: ref.value, bandeira: band.value, modalidade: mod.value,
        parcelamento: parc.value, parcelas: np.value, nsu: nsu.value}, saldo, cfg, typeof ctContemNumeroCartao === "function" ? ctContemNumeroCartao : null);
      if (c.erro){ rcAvisoPainel(p, c.erro); valor.focus(); return; }
      var corpo = Object.assign({chave: chave, conta_versao: rc.conta.versao}, c.corpo);
      if (escopo.selecionou) corpo.itens = escopo.itens.map(function(i){ return i.id; });
      rcEnviar("POST", rcUrl("pagamentos"), corpo, "Pagamento de " + dsFormatarReais(c.corpo.valor_centavos) + " registrado.", p, bt.ok);
    }, "Confirmar recebimento", "primario");
    p.appendChild(bt.caixa); mostrar2(); valor.select();
  }, "receber", "rcPainelItens");
  tit.focus();
}
