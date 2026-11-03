"use strict";
/* Notas: editor em linha (corrigir e ocultar), versões anteriores e a chave "ver ocultas" do administrador.
 * Usa os ajudantes de notas_painel.js (ntEl, ntBotao, ntCampoTexto). Esc fecha só o editor (não o diálogo). */

function ntAnteriores(lista){
  var d = ntEl("details", "nt-anteriores"), s = ntEl("summary", null, "Versões anteriores (" + lista.length + ")");
  d.appendChild(s);
  lista.forEach(function(v){
    var p = ntEl("p", "nt-texto nt-antigo", v.texto);
    p.appendChild(ntEl("span", "nt-meta suave", " — " + v.por + ", " + ntDataHora(v.em)));
    d.appendChild(p);
  });
  return d;
}
function ntSeletorOcultas(est, recarregar){
  var lab = ntEl("label", "nt-ver-ocultas"), c = document.createElement("input");
  c.type = "checkbox"; c.checked = est.ocultas;
  c.addEventListener("change", function(){ est.ocultas = c.checked; recarregar(); });
  lab.appendChild(c); lab.appendChild(document.createTextNode(" Mostrar notas ocultas e versões anteriores"));
  return lab;
}
/* modo "corrigir": caixa com o texto atual; modo "ocultar": caixa do motivo. ctx = {enviar, dizer, focar}. */
function ntEditor(li, n, acoes, modo, ctx){
  var corrigir = modo === "corrigir", ed = ntEl("div", "nt-editor");
  var c = corrigir ? ntCampoTexto("Corrigir a nota", n.texto, NT_MAX, 3) : ntCampoTexto("Motivo para ocultar (a nota não é apagada)", "", NT_MOTIVO_MAX, 1);
  var ok = ntBotao(corrigir ? "Salvar correção" : "Ocultar nota", corrigir ? "primario" : "perigo"), nao = ntBotao("Cancelar", "");
  function fechar(){ ed.remove(); acoes.classList.remove("oculto"); acoes.querySelector(corrigir ? ".nt-corrigir" : ".nt-ocultar").focus(); }
  ok.addEventListener("click", function(){
    var v = corrigir ? ntConferirTexto(c.campo.value) : ntConferirMotivo(c.campo.value);
    if (v.erro){ ctx.dizer(v.erro, true); c.campo.focus(); return; }
    var corpo = corrigir ? {texto: v.texto, versao: n.versao} : {motivo: v.motivo, versao: n.versao};
    ctx.enviar("POST", "/api/notas/" + n.id + "/" + (corrigir ? "corrigir" : "ocultar"), corpo, function(){ ctx.focar(n.id); });
  });
  nao.addEventListener("click", fechar);
  ed.addEventListener("keydown", function(ev){ if (ev.key === "Escape"){ ev.preventDefault(); ev.stopPropagation(); fechar(); } });
  ed.appendChild(c.caixa);
  var bt = ntEl("div", "nt-acoes"); bt.appendChild(ok); bt.appendChild(nao); ed.appendChild(bt);
  acoes.classList.add("oculto"); li.appendChild(ed); c.campo.focus();
}
