"use strict";
/* Notas: o bloco (lista + formulário "Nova nota") de UM escopo, a reserva ou o apartamento. Usado pelo diálogo Observações
 * e pelo Resumo da conta. Tudo é montado por createElement/textContent (o texto das notas nunca vira HTML).
 * Cada nota mostra "Adicionado por X em ... · Modificado por Y em ..."; corrigir e ocultar só aparecem para quem pode
 * (o servidor decide e manda pode_corrigir/pode_ocultar; ele confere de novo). Ocultar nunca apaga. */

var ntSeq = 0;

function ntEl(tag, cls, texto){
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (texto != null) e.textContent = texto;
  return e;
}
function ntBotao(texto, cls, rotulo){
  var b = ntEl("button", cls, texto); b.type = "button";
  if (rotulo) b.setAttribute("aria-label", rotulo);
  return b;
}
/* Campo de texto com contador e aviso de número de cartão (cartao.js). Devolve {caixa, area, campo}. */
function ntCampoTexto(rotulo, valor, maximo, linhas){
  var id = "nt-c" + (++ntSeq), caixa = ntEl("div", "nt-campo");
  var lab = ntEl("label", null, rotulo); lab.htmlFor = id;
  var campo = ntEl(linhas > 1 ? "textarea" : "input"); campo.id = id; campo.maxLength = maximo; campo.value = valor || "";
  if (linhas > 1) campo.rows = linhas;
  var cont = ntEl("span", "nt-contador suave", ntContador(campo.value));
  var av = ntEl("p", "aviso-cartao oculto", "Isto parece um número de cartão. O sistema não guarda números de cartão: escreva só, por exemplo, \"pago no cartão (final 1234)\".");
  av.setAttribute("role", "alert");
  campo.addEventListener("input", function(){
    cont.textContent = ntContador(campo.value);
    av.classList.toggle("oculto", !(typeof ctContemNumeroCartao === "function" && ctContemNumeroCartao(campo.value)));
  });
  caixa.appendChild(lab); caixa.appendChild(campo); caixa.appendChild(cont); caixa.appendChild(av);
  return {caixa: caixa, campo: campo};
}

function ntBloco(host, op){      // op = {url, aoMudar, leitura (true = só ler: reserva cancelada)}
  var est = {dados: null, ocultas: false, ocupado: false, chave: ntNovaChave()};
  var msg = ntEl("p", "nt-msg", ""), lista = ntEl("ul", "nt-lista"), novo = ntEl("form", "nt-novo oculto");
  msg.setAttribute("role", "status"); msg.setAttribute("aria-live", "polite");
  host.textContent = "";
  host.appendChild(msg); host.appendChild(lista); host.appendChild(novo);
  if (typeof pode === "function" && pode("notas.ver_ocultas")) host.insertBefore(ntSeletorOcultas(est, carregar), lista);

  function dizer(texto, erro){ msg.textContent = texto || ""; msg.classList.toggle("nt-erro", !!erro); }
  function falha(r){ dizer(ntMensagemErro(r.status, r.dados && r.dados.erro), true); if (r.status === 409) carregar(true); }      // outra pessoa mexeu: recarrega a lista e mantém o aviso
  function enviar(metodo, url, corpo, depois){
    if (est.ocupado) return;
    est.ocupado = true; dizer("Salvando…", false);
    api(metodo, url, corpo).then(function(r){
      est.ocupado = false;
      if (r.ok){ dizer("", false); depois(r.dados); carregar(); if (op.aoMudar) op.aoMudar(); } else falha(r);
    }).catch(function(){ est.ocupado = false; dizer("Sem conexão com o servidor.", true); });
  }
  var ctx = {enviar: enviar, dizer: dizer, focar: function(id){ est.foco = id; }};
  function desenharNota(n){
    var li = ntEl("li", "nt-nota" + (n.oculta ? " nt-oculta" : "")); li.dataset.id = n.id;
    li.appendChild(ntEl("p", "nt-texto", n.texto)); li.appendChild(ntEl("p", "nt-meta suave", ntMeta(n)));
    if (n.oculta) li.appendChild(ntEl("p", "nt-meta suave", "Oculta por " + n.oculta_por + " em " + ntDataHora(n.oculta_em) + ". Motivo: " + n.oculta_motivo));
    if (n.anteriores && n.anteriores.length) li.appendChild(ntAnteriores(n.anteriores));
    if (n.pode_corrigir && !op.leitura){
      var ac = ntEl("div", "nt-acoes"), c = ntBotao("Corrigir", "nt-corrigir", "Corrigir a nota de " + n.por), o = ntBotao("Ocultar", "nt-ocultar", "Ocultar a nota de " + n.por);
      c.addEventListener("click", function(){ ntEditor(li, n, ac, "corrigir", ctx); });
      o.addEventListener("click", function(){ ntEditor(li, n, ac, "ocultar", ctx); });
      ac.appendChild(c); ac.appendChild(o); li.appendChild(ac);
    }
    return li;
  }
  function desenharLista(){
    lista.textContent = "";
    var d = est.dados;
    if (!d.notas.length) lista.appendChild(ntEl("li", "nt-vazio suave", "Nenhuma nota."));
    d.notas.forEach(function(n){ lista.appendChild(desenharNota(n)); });
    var f = est.foco && lista.querySelector('li[data-id="' + est.foco + '"] .nt-corrigir');      // devolve o foco à nota que acabou de mudar
    est.foco = null;
    if (f) f.focus();
  }
  function montarNovo(){
    novo.textContent = ""; novo.classList.remove("oculto");
    var c = ntCampoTexto("Nova nota", "", NT_MAX, 3), b = ntBotao("Adicionar nota", "primario nt-add");
    b.type = "submit"; novo.appendChild(c.caixa); novo.appendChild(b);
    novo.onsubmit = function(ev){
      ev.preventDefault();
      var v = ntConferirTexto(c.campo.value);
      if (v.erro){ dizer(v.erro, true); c.campo.focus(); return; }
      enviar("POST", op.url, {texto: v.texto, chave: est.chave}, function(){ est.chave = ntNovaChave(); c.campo.value = ""; c.campo.dispatchEvent(new Event("input")); c.campo.focus(); });
    };
    c.campo.addEventListener("keydown", function(ev){ if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)){ ev.preventDefault(); novo.requestSubmit(); } });
  }
  function carregar(manterAviso){
    api("GET", op.url + (est.ocultas ? "?ocultas=1" : "")).then(function(r){
      if (!r.ok){ dizer(ntMensagemErro(r.status, r.dados && r.dados.erro), true); return; }
      est.dados = r.dados; if (!manterAviso) dizer("", false);
      desenharLista();
      if (r.dados.pode_escrever && !op.leitura && novo.classList.contains("oculto")) montarNovo();
      if (r.dados.pode_escrever && !op.leitura && r.dados.total >= r.dados.limite) dizer("Limite de " + r.dados.limite + " notas atingido.", true);
    }).catch(function(){ dizer("Sem conexão com o servidor.", true); });
  }
  dizer("Carregando as notas…", false);
  carregar();
  return {recarregar: carregar};
}
