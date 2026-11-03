"use strict";
/* Resumo da conta: Manutenção de hóspedes (titular + acompanhantes). Painel em linha do cartão. Quem só pode ver (diretoria, consulta)
 * recebe a lista com o documento mascarado e sem os outros dados pessoais; quem gerencia (hospedes.gerir) edita e salva tudo de uma vez
 * (PUT /api/reservas/<id>/hospedes com a versão da reserva). O total de hóspedes fica ligado ao "n" (pessoas) da reserva.
 * Documento, nascimento, nacionalidade, profissão, procedência e destino são DADOS PESSOAIS: opcionais, nunca em logs. */

var RC_HP_OPCIONAIS = [["documento", "Documento (CPF, RG ou passaporte)", 20, "text"], ["nascimento", "Data de nascimento", 10, "date"],
  ["nacionalidade", "Nacionalidade", 40, "text"], ["profissao", "Profissão", 60, "text"], ["procedencia", "Procedência (cidade / UF / país)", 60, "text"],
  ["destino", "Destino (próxima cidade / UF / país)", 60, "text"]];
var rcHp = {dados: null, linhas: [], p: null};

function rcHpCampo(rotulo, valor, maximo, tipo){
  var id = "rc-hp" + (++ntSeq), c = ntEl("div", "campo"), lab = ntEl("label", null, rotulo), inp = ntEl("input");
  lab.htmlFor = id; inp.id = id; inp.type = tipo; inp.value = valor || ""; if (tipo !== "date") inp.maxLength = maximo; inp.autocomplete = "off";
  c.appendChild(lab); c.appendChild(inp);
  return {caixa: c, campo: inp};
}
function rcHpTipo(valor){
  var id = "rc-hp" + (++ntSeq), c = ntEl("div", "campo"), lab = ntEl("label", null, "Tipo"), sel = ntEl("select");
  lab.htmlFor = id; sel.id = id;
  [["adulto", "Adulto"], ["crianca", "Criança"]].forEach(function(o){ var op = ntEl("option", null, o[1]); op.value = o[0]; sel.appendChild(op); });
  sel.value = valor || "adulto"; c.appendChild(lab); c.appendChild(sel);
  return {caixa: c, campo: sel};
}
/* Uma linha (titular ou acompanhante): campos e botão Remover. dados = hóspede do servidor ou {} para um novo. */
function rcHpLinha(dados, titular, editavel){
  var li = ntEl("li", "rc-hp-linha"), l = {id: dados.id == null ? null : dados.id, titular: titular, campos: {}, li: li};
  li.appendChild(ntEl("h4", "rc-hp-tit", titular ? "Titular: " + rc.det.nome : "Acompanhante"));
  if (!titular){
    var n = rcHpCampo("Nome completo", dados.nome, 120, "text"); n.campo.required = true; l.campos.nome = n.campo; li.appendChild(n.caixa);
    if (!editavel){ n.campo.readOnly = true; }
  }
  var t = rcHpTipo(dados.tipo); l.campos.tipo = t.campo; li.appendChild(t.caixa);
  var det = ntEl("details", "rc-hp-mais"); det.appendChild(ntEl("summary", null, editavel ? "Documento e outros dados (opcionais)" : "Documento (mascarado)"));
  RC_HP_OPCIONAIS.forEach(function(o){
    if (!editavel && o[0] !== "documento") return;
    var c = rcHpCampo(o[1], dados[o[0]], o[2], o[3]); l.campos[o[0]] = c.campo; det.appendChild(c.caixa);
    if (!editavel) c.campo.readOnly = true;
    if (o[0] === "documento" || o[0] === "profissao" || o[0] === "destino" || o[0] === "procedencia" || o[0] === "nacionalidade"){
      c.campo.addEventListener("input", function(){ c.campo.classList.toggle("rc-hp-cartao", typeof ctContemNumeroCartao === "function" && ctContemNumeroCartao(c.campo.value)); });
    }
  });
  li.appendChild(det);
  if (!titular && editavel){
    var rem = ntBotao("Remover acompanhante", "rc-hp-rem", "Remover este acompanhante");
    rem.addEventListener("click", function(){ rcHp.linhas = rcHp.linhas.filter(function(x){ return x !== l; }); li.remove(); rcHpAtualizarAdicionar(); });
    li.appendChild(rem);
  }
  return l;
}
function rcHpValores(l){
  var o = {}, v;
  Object.keys(l.campos).forEach(function(k){ v = l.campos[k].value.trim(); o[k] = v === "" && k !== "nome" && k !== "tipo" ? null : v; });
  if (l.id != null) o.id = l.id;
  return o;
}
function rcHpAtualizarAdicionar(){
  var add = $("rcHpAdd"); if (!add) return;
  var cheio = 1 + rcHp.linhas.filter(function(x){ return !x.titular; }).length >= rcHp.dados.n;
  add.disabled = cheio; $("rcHpDica").textContent = cheio ? "Todas as " + rcPlural(rcHp.dados.n, "pessoa", "pessoas") + " da reserva já estão na lista. Para incluir mais, aumente o número de pessoas em Alterar estadia." : "";
}
function rcHpSalvar(btn){
  var tit = rcHp.linhas.filter(function(x){ return x.titular; })[0], acomp = rcHp.linhas.filter(function(x){ return !x.titular; });
  for (var k = 0; k < acomp.length; k++){
    if (!acomp[k].campos.nome.value.trim()){ rcAvisoPainel(rcHp.p, "Informe o nome de todos os acompanhantes (ou remova a linha vazia)."); acomp[k].campos.nome.focus(); return; }
  }
  var corpo = {versao: rcHp.dados.versao, titular: rcHpValores(tit), acompanhantes: acomp.map(rcHpValores)};
  rcEnviar("PUT", "/api/reservas/" + rc.det.id + "/hospedes", corpo, "Hóspedes salvos.", rcHp.p, btn);
}
function rcHpDesenhar(p, dados){
  var editavel = dados.pode_editar;
  rcHp.dados = dados; rcHp.p = p; rcHp.linhas = [];
  p.appendChild(ntEl("p", "suave", editavel ? "Titular e acompanhantes da hospedagem (" + rcPlural(dados.n, "pessoa", "pessoas") + " na reserva). Documento e demais dados pessoais são opcionais."
    : "Lista dos hóspedes. Documento mascarado: os dados pessoais completos são só de quem registra a hospedagem."));
  var ul = ntEl("ul", "rc-hp-lista"); p.appendChild(ul);
  rcHp.linhas.push(rcHpLinha(dados.titular, true, editavel)); ul.appendChild(rcHp.linhas[0].li);
  dados.acompanhantes.forEach(function(a){ var l = rcHpLinha(a, false, editavel); rcHp.linhas.push(l); ul.appendChild(l.li); });
  if (!editavel){ p.appendChild(rcBotoesPainel(function(){ rcFecharPainel(true); }, "Fechar", "").caixa); return; }
  var add = ntBotao("Adicionar acompanhante", "rc-hp-add"); add.id = "rcHpAdd";
  add.addEventListener("click", function(){
    var l = rcHpLinha({}, false, true); rcHp.linhas.push(l); ul.appendChild(l.li); rcHpAtualizarAdicionar(); l.campos.nome.focus();
  });
  p.appendChild(add); var dica = ntEl("p", "suave", ""); dica.id = "rcHpDica"; p.appendChild(dica);
  var bt = rcBotoesPainel(function(){ rcHpSalvar(bt.ok); }, "Salvar hóspedes", "primario");
  p.appendChild(bt.caixa); rcHpAtualizarAdicionar();
}
function rcHospedes(){
  api("GET", "/api/reservas/" + rc.det.id + "/hospedes").then(function(r){
    if (!r.ok){ aviso(rcMensagemErro(r.status, r.dados.erro)); return; }
    var tit = rcAbrirPainel("Manutenção de hóspedes", function(p){ rcHpDesenhar(p, r.dados); }, "hospedes");
    tit.focus();
  }).catch(function(){ aviso("Sem conexão com o servidor."); });
}
