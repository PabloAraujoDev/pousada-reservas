"use strict";
/* Notas: as ABAS de observações (Reserva, Arrumação, Apartamento), usadas pelo diálogo Observações e pelo Resumo da conta.
 *   Reserva     = "Observação padrão" (campo o da reserva, intacto), extras e as notas da reserva (autor e data);
 *   Arrumação   = observação e manutenção da governança, só leitura (quem escreve é a tela da Governança);
 *   Apartamento = notas do apartamento (valem para reservas futuras).
 * ntMontarAbas(abasEl, painelEl, op): op = {rid (ou null), unidade, det (detalhe da reserva ou null), gov (item da governança ou null),
 *   aoEditarPadrao (função ou null), inicial (id da aba), leitura (true = reserva cancelada: sem escrever)}. Setas esquerda/direita trocam de aba (role=tablist). */

function ntSecao(titulo){
  var s = ntEl("section", "nt-secao"); s.appendChild(ntEl("h3", null, titulo));
  return s;
}
function ntPintarReserva(painel, op){
  var s = ntSecao("Observação padrão"), t = op.det && typeof op.det.o === "string" ? op.det.o.trim() : null;
  s.appendChild(ntEl("p", "od-nota-texto" + (t ? "" : " suave"), op.det ? (t || "Nenhuma observação padrão.") : "Não foi possível carregar a observação da reserva."));
  if (op.aoEditarPadrao){
    var b = ntBotao("Editar observação padrão", "nt-editar-padrao"); b.addEventListener("click", op.aoEditarPadrao); s.appendChild(b);
  }
  painel.appendChild(s);
  var x = op.det && typeof op.det.extras === "string" ? op.det.extras.trim() : "";
  if (x){ var e = ntSecao("Acompanhantes e extras"); e.appendChild(ntEl("p", "od-nota-texto", x)); painel.appendChild(e); }
  var n = ntSecao("Notas da reserva"), host = ntEl("div", "nt-host"); n.appendChild(host); painel.appendChild(n);
  ntBloco(host, {url: "/api/reservas/" + encodeURIComponent(op.rid) + "/notas", leitura: op.leitura});
}
function ntPintarArrumacao(painel, op){
  var s = ntSecao("Arrumação do apartamento " + op.unidade);
  ntTextoArrumacao(op.gov).forEach(function(l){ s.appendChild(ntEl("p", "od-nota-texto", l)); });
  painel.appendChild(s);
}
function ntPintarApartamento(painel, op){
  var s = ntSecao("Notas do apartamento " + op.unidade), host = ntEl("div", "nt-host");
  s.appendChild(ntEl("p", "suave nt-explica", "Valem para todas as reservas deste apartamento, hoje e no futuro."));
  s.appendChild(host); painel.appendChild(s);
  ntBloco(host, {url: "/api/unidades/" + encodeURIComponent(op.unidade) + "/notas"});
}
var NT_PINTORES = {reserva: ntPintarReserva, arrumacao: ntPintarArrumacao, apartamento: ntPintarApartamento};

function ntMontarAbas(abasEl, painelEl, op){
  var abas = ntAbas({reserva: op.rid != null, gov: typeof pode === "function" && pode("governanca.ver"), apto: true}), ativa = 0;
  abasEl.textContent = "";
  function mostrar(k){
    ativa = k; abasEl.dataset.ativa = abas[k].id;
    Array.prototype.forEach.call(abasEl.children, function(b, j){
      b.setAttribute("aria-selected", j === k ? "true" : "false"); b.tabIndex = j === k ? 0 : -1; b.classList.toggle("ativo", j === k);
    });
    painelEl.textContent = "";
    painelEl.setAttribute("aria-labelledby", abasEl.children[k].id);
    NT_PINTORES[abas[k].id](painelEl, op);
  }
  abas.forEach(function(a, k){
    var b = ntEl("button", null, a.rotulo); b.type = "button"; b.setAttribute("role", "tab"); b.id = "nt-aba-" + (++ntSeq);
    b.addEventListener("click", function(){ mostrar(k); });
    b.addEventListener("keydown", function(ev){
      var d = ev.key === "ArrowRight" ? 1 : (ev.key === "ArrowLeft" ? -1 : 0);
      if (!d) return;
      ev.preventDefault();
      var m = (ativa + d + abas.length) % abas.length; mostrar(m); abasEl.children[m].focus();
    });
    abasEl.appendChild(b);
  });
  var ini = abas.map(function(a){ return a.id; }).indexOf(op.inicial);
  if (abas.length) mostrar(ini >= 0 ? ini : 0);
  return {mostrar: mostrar};
}
