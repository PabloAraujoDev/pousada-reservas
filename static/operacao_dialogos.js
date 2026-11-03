"use strict";
/* Operação do dia: diálogo INFORMAÇÕES (somente leitura) e o que os diálogos da coluna Ações têm em comum.
 *
 * Só dados que o sistema já tem (apartamento, hóspede, pessoas, período, situação do dia, sócio/convidado, grupo, pagamento e,
 * para quem tem governanca.ver, o estado da arrumação). Endereço e contato NÃO existem: a linha diz isso (decisão da especificação:
 * nada de campos de endereço até o cadastro de hóspedes). Sem valor de diária, sem observações (essas ficam em operacao_notas.js).
 * Todo texto entra por textContent (nunca innerHTML). */
if (typeof module !== "undefined" && typeof odPlural === "undefined") Object.assign(globalThis, require("./operacao_dia.js"));   // (só no teste em node)

var OD_SEM_CADASTRO = "Cadastro não preenchido (será habilitado com o cadastro de hóspedes).";
var odOrigem = null;           // de onde o diálogo foi aberto, para devolver o foco ao fechar

/* ---------- lógica pura ---------- */
function odNoites(i, f){ var a = i.split("-"), b = f.split("-"); return Math.round((Date.UTC(+b[0], +b[1] - 1, +b[2]) - Date.UTC(+a[0], +a[1] - 1, +a[2])) / 86400000); }
function odSituacaoDia(sit, troca){ return troca ? "Troca: sai às 12h e entra às 14h" : (CD_ROTULO_SIT[sit] || sit); }
/* [rótulo, valor] do diálogo. l = {tipo, a, r, situacao, troca}; x = {gov (texto da governança ou null), proxima (reserva ou null)}. */
function odLinhasInfo(l, x){
  var r = l.r, t = [["Apartamento", l.a]];
  if (l.tipo === "reserva"){
    var noites = odNoites(r.i, r.f);
    t.push(["Hóspede", r.nome], ["Reserva", "#" + r.id], ["Pessoas", String(r.n)]);
    t.push(["Período", "Entrada " + cdDataBR(r.i) + " (14h) | Saída " + cdDataBR(r.f) + " (12h) | " + odPlural(noites, "noite", "noites")]);
    t.push(["Situação no dia", odSituacaoDia(l.situacao, l.troca)], ["Sócio ou convidado", CD_ROTULO_TIPO[r.tipo] || "Não informado"]);
    t.push(["Grupo", r.grupo || "Não informado"], ["Pagamento", CD_ROTULO_PAG[r.p] || r.p]);
  } else {
    t.push(["Situação", l.tipo === "vaga" ? "Vaga" : "Interditada (fora de venda, sem previsão)"]);
    if (l.tipo === "vaga") t.push(["Próxima reserva", x.proxima ? x.proxima.nome + ", entra " + cdDataBR(x.proxima.i) + " 14h" : "Sem próxima reserva"]);
  }
  if (x.gov) t.push(["Governança", x.gov]);
  if (l.tipo === "reserva") t.push(["Endereço/contato", OD_SEM_CADASTRO]);
  return t;
}

/* ---------- tela ---------- */
function odLinhaDoBotao(b){        // reconstrói a linha da lista a partir dos atributos do botão (a reserva vem da lista atual)
  var r = b.dataset.rid ? reservaPorId(b.dataset.rid) : null;
  return {tipo: r ? "reserva" : (b.dataset.sit === "interditada" ? "interditada" : "vaga"), a: b.dataset.un, r: r,
    situacao: b.dataset.sit, troca: b.dataset.troca === "sim", dia: b.dataset.dia};
}
function odGuardarOrigem(b){ var t = b.closest("table"); odOrigem = t ? {foco: b.dataset.foco, tabela: t.id} : null; }   // sem tabela (aberto do Resumo): quem abriu devolve o foco
function odDevolverFoco(){
  var o = odOrigem; odOrigem = null;
  var t = o && document.getElementById(o.tabela);
  if (t) cdRestaurarFoco(t, o.foco);
}
function odTituloDialogo(l){ return "Apartamento " + l.a + (l.r ? " - " + l.r.nome : (l.tipo === "vaga" ? " (vago)" : " (interditado)")); }
function odBuscarGovernanca(un){   // item da unidade em /api/governanca (só quem tem governanca.ver); null se não der
  if (!pode("governanca.ver")) return Promise.resolve(null);
  return api("GET", "/api/governanca").then(function(r){
    return r.ok ? (r.dados.unidades.filter(function(u){ return u.u === un; })[0] || null) : null;
  }).catch(function(){ return null; });
}
function odDesenharInfo(l, gov){
  var dl = $("infoLista"), x = {gov: gov && GV_ROTULO[gov.situacao] ? GV_ROTULO[gov.situacao] : null, proxima: l.tipo === "vaga" ? odProximaReserva(reservas, l.a, l.dia) : null};
  dl.textContent = "";
  odLinhasInfo(l, x).forEach(function(par){
    var dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = par[0]; dd.textContent = par[1];
    if (par[0] === "Endereço/contato") dd.className = "suave";
    dl.appendChild(dt); dl.appendChild(dd);
  });
}
function odAbrirInfo(b){
  var l = odLinhaDoBotao(b);
  if (l.tipo === "reserva" && !l.r) return;
  odGuardarOrigem(b);
  odBuscarGovernanca(l.a).then(function(gov){
    $("infoTit").textContent = odTituloDialogo(l);
    odDesenharInfo(l, gov);
    mostrar($("infoAbrir"), l.tipo === "reserva");
    $("infoAbrir").onclick = function(){ $("dlgInfo").close(); abrirReserva(l.r); };
    $("dlgInfo").showModal();
    $("infoTit").focus();
  });
}
function odAbrirDialogo(b){ if (b.dataset.acao === "info") odAbrirInfo(b); else odAbrirNotas(b); }   // odAbrirNotas: operacao_notas.js
function odLigarDialogos(){
  ["infoFechar", "infoFechar2"].forEach(function(id){ $(id).addEventListener("click", function(){ $("dlgInfo").close(); }); });
  $("dlgInfo").addEventListener("close", odDevolverFoco);
}
if (typeof document !== "undefined") odLigarDialogos();
if (typeof module !== "undefined" && module.exports) module.exports = {odNoites: odNoites, odLinhasInfo: odLinhasInfo, odSituacaoDia: odSituacaoDia, OD_SEM_CADASTRO: OD_SEM_CADASTRO};
