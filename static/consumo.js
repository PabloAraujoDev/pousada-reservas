"use strict";
/* Relatório de consumo do administrador (aba Despesas): lançamentos do período com a HORA exata, para conferir câmeras.
 * Só despesas.hora recebe este endpoint (o servidor confere). Imprime em A4 paisagem (body.imp-consumo). Texto por textContent. */

var cn = {dados: null};

function cnMsg(t, erro){ $("cnMsg").textContent = t ? (erro ? "Atenção: " : "") + t : ""; }
function cnCelula(tr, texto, classe){
  var td = document.createElement("td");
  td.textContent = texto;
  if (classe) td.className = classe;
  tr.appendChild(td);
}
function cnDesenhar(d){
  var corpo = $("cnLista");
  corpo.textContent = "";
  d.itens.forEach(function(l){
    var tr = document.createElement("tr"), q = dsQuando(l.em);
    if (l.tipo === "estorno") tr.className = "ds-s-estorno";
    cnCelula(tr, q.data + "/" + l.em.slice(0, 4) + " " + (q.hora || "-"));
    cnCelula(tr, l.apto); cnCelula(tr, l.hospede || "-");
    cnCelula(tr, l.descricao); cnCelula(tr, String(l.quantidade), "ds-num");
    cnCelula(tr, dsFormatarReais(l.valor_unit_centavos), "ds-num");
    cnCelula(tr, dsFormatarReais(l.total_centavos), "ds-num");
    cnCelula(tr, l.usuario_login); cnCelula(tr, cnObservacao(l));
    corpo.appendChild(tr);
  });
  $("cnTabela").classList.toggle("oculto", d.itens.length === 0);
  $("cnTotal").textContent = d.itens.length ? "Total líquido do período: " + dsFormatarReais(d.total_centavos) + " em " + d.itens.length + " linha(s)" +
    (d.cortado ? ". Atenção: lista cortada em 3000 linhas; reduza o período." : ".") : "";
  cnMsg(d.itens.length ? "" : "Nenhum lançamento no período.");
}
function cnGerar(){
  var ini = $("cnIni").value, fim = $("cnFim").value, erro = cnPeriodoValido(ini, fim);
  if (erro){ cnMsg(erro, true); return; }
  api("GET", "/api/relatorio/consumo?inicio=" + encodeURIComponent(ini) + "&fim=" + encodeURIComponent(fim)).then(function(r){
    if (!r.ok){ cnMsg(r.dados.erro || "Não foi possível gerar o relatório.", true); return; }
    cn.dados = r.dados; cnDesenhar(r.dados);
  }).catch(function(){ cnMsg("Sem conexão com o servidor.", true); });
}
function cnImprimir(){
  if (!cn.dados){ cnMsg("Gere o relatório antes de imprimir.", true); return; }
  $("cnImpCab").textContent = "Pousada Boa Esperança - Relatório de consumo de " + cdDataBR(cn.dados.inicio) + " a " + cdDataBR(cn.dados.fim) +
    " - emitido em " + new Date().toLocaleString("pt-BR") + " (uso interno: contém a hora exata dos lançamentos)";
  document.body.classList.add("imp-consumo");
  window.print();
  document.body.classList.remove("imp-consumo");
}
function cnLigar(){
  var hoje = new Date(), iso = hoje.getFullYear() + "-" + String(hoje.getMonth() + 1).padStart(2, "0") + "-" + String(hoje.getDate()).padStart(2, "0");
  $("cnIni").value = iso; $("cnFim").value = iso;
  $("cnGerar").addEventListener("click", cnGerar);
  $("cnImprimir").addEventListener("click", cnImprimir);
  window.addEventListener("afterprint", function(){ document.body.classList.remove("imp-consumo"); });
}
if (typeof document !== "undefined" && document.getElementById("cnGerar")) cnLigar();
