"use strict";
/* Governança: a tela de trabalho das camareiras (menu "Governança").
 * Usa de app.js: $, esc, api, aviso, pode, mostrar, UNIDADES, OCUPADAS, sessao. Usa de governanca_logica.js: tudo que começa com gv.
 *
 * Princípios:
 *  - O servidor decide o que cada perfil recebe e pode fazer (campo `pode`); aqui só se desenha.
 *  - Estado fora do HTML: filtros, seleção e grupos recolhidos ficam em `gv`; o polling de 8 s só redesenha a lista
 *    quando a ASSINATURA dos dados muda, e devolve o foco ao botão que o tinha. Nunca apaga seleção nem filtros.
 *  - Texto vindo do servidor (observação, motivo, login) entra no HTML sempre por esc() ou por textContent. */

var GV_INTERVALO = 8000;
var GV_UNDO_MS = 8000;
var GV_CHAVE_RECOLHIDOS = "pousada.governanca.recolhidos";
var GV_ICONES = {
  suja: "M12 3 22 20H2zm-1 6v5h2V9zm0 6v2h2v-2z",
  em_arrumacao: "M6 3h12v3.4l-4 4.6 4 4.6V19H6v-3.4l4-4.6-4-4.6z",
  pronta: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1.5 14.5-4-4 1.4-1.4 2.6 2.6 5.6-5.6 1.4 1.4z",
  hospedada: "M3 18v-8h2v2h14v-2h2v8h-2v-2H5v2zM6 9V7a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v2zm8 0V7a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v2z",
  aguardando_saida: "M5 3h8v2H7v14h6v2H5zm10 4 5 5-5 5v-4H9v-2h6z",
  manutencao: "M21 6.5 17.5 10 15 7.5 18.5 4A5 5 0 0 0 11 9.8L3 17.8 6.2 21l8-8a5 5 0 0 0 6.8-6.5z",
  interditada: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 2a8 8 0 0 1 6.3 12.9L7.1 5.7A8 8 0 0 1 12 4zm0 16a8 8 0 0 1-6.3-12.9l11.2 11.2A8 8 0 0 1 12 20z"
};

var gv = {
  dados: null, assinatura: "", filtros: Object.assign({}, GV_FILTRO_VAZIO), sel: {}, modoSel: false,
  recolhidos: {}, offline: false, horaDados: "", ocupado: false, seq: 0, desenhado: "", pendente: false,
  tentar: null, undoTimer: null, menuU: null, timer: null, aberto: false, longo: null
};

/* ---------- ajudantes ---------- */
function gvItens(){ return gv.dados ? gv.dados.unidades : []; }
function gvItem(u){ var l = gvItens(); for (var k = 0; k < l.length; k++) if (l[k].u === u) return l[k]; return null; }
function gvSelecionadas(){ return gvItens().filter(function(i){ return gv.sel[i.u]; }); }
function gvPodeAtualizar(){ return pode("governanca.atualizar"); }
function gvDataBR(s){ return s ? s.slice(8) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : ""; }
function gvIcone(s){
  return '<svg class="gv-icone" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path d="' + esc(GV_ICONES[s] || "") + '"/></svg>';
}
function gvLerRecolhidos(){
  try { gv.recolhidos = JSON.parse(window.localStorage.getItem(GV_CHAVE_RECOLHIDOS) || "{}") || {}; } catch (e) { gv.recolhidos = {}; }
}
function gvSalvarRecolhidos(){
  try { window.localStorage.setItem(GV_CHAVE_RECOLHIDOS, JSON.stringify(gv.recolhidos)); } catch (e) { /* sem armazenamento: só não lembra */ }
}
function gvAnunciar(txt){ $("gvLive").textContent = ""; setTimeout(function(){ $("gvLive").textContent = txt; }, 30); }

/* ---------- desenho do cartão ---------- */
function gvBotaoPrincipal(i){        // {acao, rotulo} do botão grande do cartão, ou null
  var p = i.pode || [];
  if (i.situacao === "em_arrumacao" && p.indexOf("pronta") >= 0) return {acao: "pronta", rotulo: "Pronto"};
  if ((i.situacao === "suja" || i.situacao === "hospedada" || i.situacao === "aguardando_saida") && p.indexOf("iniciar") >= 0)
    return {acao: "iniciar", rotulo: "Iniciar"};
  if (i.situacao === "aguardando_saida" && p.indexOf("suja") >= 0) return {acao: "suja", rotulo: "Hóspede saiu"};
  if (i.situacao === "suja" && p.indexOf("pronta") >= 0) return {acao: "pronta", rotulo: "Pronto"};
  return null;
}
function gvHtmlSelos(i){
  return gvSelos(i).map(function(s){ return '<span class="gv-selo gv-selo-' + esc(s.tipo) + '">' + esc(s.txt) + '</span>'; }).join("");
}
function gvHtmlLinhaInfo(i){
  var partes = [], pes = gvPessoasDoCartao(i);
  if (pes) partes.push(esc(pes));
  gvTextoDias(i).forEach(function(t){ partes.push('<span class="gv-dias' + (i.alerta_enxoval ? " gv-alerta" : "") + '">' + esc(t) + '</span>'); });
  if (gvPodeEntrar(i)) partes.push('<b class="gv-entrar">Pode entrar</b>');
  return partes.join(" · ");
}
function gvNomeHospede(i){          // só existe para quem pode ver reservas (o servidor decide)
  var n = (i.hospede && i.hospede.nome) || (i.chegada_hoje && i.chegada_hoje.nome) || (i.saida_hoje && i.saida_hoje.nome) || "";
  return n ? '<div class="gv-hospede">' + esc(n) + '</div>' : "";
}
function gvHtmlObs(i){
  var t = i.situacao === "manutencao" && i.manutencao_motivo ? "Manutenção: " + i.manutencao_motivo : i.obs;
  var extra = i.obs_reserva && !i.obs ? i.obs_reserva : "";
  var texto = t || extra;
  if (!texto) return "";
  return '<button type="button" class="gv-obs" data-obs="' + esc(i.u) + '" title="Tocar para ver a observação completa">' +
    (extra && !t ? '<span class="gv-obs-rot">Reserva:</span> ' : '') + esc(texto) + '</button>';
}
function gvHtmlCartao(i){
  var principal = gvBotaoPrincipal(i), sel = !!gv.sel[i.u], bloqueado = i.situacao === "interditada";
  var cls = "gv-card gv-sit-" + i.situacao + (sel ? " gv-selecionado" : "") + (i.atrasada ? " gv-atrasado" : "") + (i.troca_hoje ? " gv-troca" : "");
  var h = '<article class="' + esc(cls) + '" data-u="' + esc(i.u) + '" aria-label="' + esc(gvAria(i)) + '">';
  h += '<label class="gv-marca"><input type="checkbox" class="gv-sel-in" data-foco="' + esc("sel:" + i.u) + '"' + (sel ? " checked" : "") + (bloqueado ? " disabled" : "") +
    ' aria-label="Selecionar ' + esc(gvNomeUnidade(i.u)) + '"></label>';
  h += '<div class="gv-num"><b>' + esc(i.u.replace("Chalé ", "")) + '</b><small>' + (/^Chal/.test(i.u) ? "Chalé" : "Apto") + '</small></div>';
  h += '<div class="gv-corpo"><div class="gv-linha"><span class="gv-sit">' + gvIcone(i.situacao) + esc(GV_ROTULO[i.situacao]) + '</span>' + gvHtmlSelos(i) + '</div>';
  var info = gvHtmlLinhaInfo(i);
  if (info) h += '<div class="gv-info">' + info + '</div>';
  h += gvNomeHospede(i) + gvHtmlObs(i) + '</div><div class="gv-acoes">';
  if (principal) h += '<button type="button" class="gv-principal" data-acao="' + esc(principal.acao) + '" data-u="' + esc(i.u) + '" data-foco="' + esc("p:" + i.u) + '">' + esc(principal.rotulo) + '</button>';
  h += '<button type="button" class="gv-mais" data-mais="' + esc(i.u) + '" data-foco="' + esc("m:" + i.u) + '" aria-haspopup="dialog" aria-label="Mais ações de ' + esc(gvNomeUnidade(i.u)) + '"><span aria-hidden="true">&#8943;</span></button>';
  return h + '</div></article>';
}
function gvHtmlGrupo(g, filtrados){
  var recolhido = !!gv.recolhidos[g.nome], todos = g.itens.filter(function(i){ return filtrados.indexOf(i) >= 0; });
  var c = gvTextoContagens(gvContagens(g.itens)), selecionaveis = gvSelecionaveis(todos);
  var marcado = selecionaveis.length > 0 && selecionaveis.every(function(i){ return gv.sel[i.u]; });
  var h = '<section class="gv-grupo" data-grupo="' + esc(g.nome) + '"><div class="gv-grupo-cab">';
  h += '<label class="gv-marca gv-marca-grupo"><input type="checkbox" class="gv-sel-grupo" data-grupo="' + esc(g.nome) + '"' + (marcado ? " checked" : "") + ' aria-label="Selecionar o grupo ' + esc(g.nome) + '"></label>';
  h += '<button type="button" class="gv-recolher" data-grupo="' + esc(g.nome) + '" aria-expanded="' + (recolhido ? "false" : "true") + '" data-foco="' + esc("g:" + g.nome) + '">';
  h += '<span class="gv-seta" aria-hidden="true"></span><b>' + esc(g.nome) + '</b> <span class="gv-contagens">' + esc(c) + '</span></button></div>';
  if (!recolhido) h += '<div class="gv-cards">' + todos.map(gvHtmlCartao).join("") + '</div>';
  return h + '</section>';
}
function gvHtmlLista(){
  var filtrados = gvFiltrar(gvItens(), gv.filtros);
  if (!gv.dados) return '<div class="gv-esqueleto" aria-hidden="true">' + new Array(7).join('<div class="gv-card gv-fantasma"></div>') + '</div><p class="suave">Carregando...</p>';
  if (!filtrados.length) return '<p class="gv-vazio">Nenhuma unidade com esse filtro. <button type="button" id="gvLimparVazio">Limpar filtros</button></p>';
  return gvAgrupar(gvItens()).map(function(g){
    var tem = g.itens.some(function(i){ return filtrados.indexOf(i) >= 0; });
    return tem ? gvHtmlGrupo({nome: g.nome, itens: g.itens}, filtrados) : "";
  }).join("");
}
function gvTotaisBotoes(){
  var t = gv.dados.totais, f = gv.filtros;
  return [["saida", "Saída", t.saida_hoje, f.saida], ["chegada", "Chegada", t.chegada_hoje, f.chegada], ["suja", "Suja", t.suja, f.situacao === "suja"],
    ["em_arrumacao", "Em arrumação", t.em_arrumacao, f.situacao === "em_arrumacao"], ["pronta", "Pronta", t.pronta, f.situacao === "pronta"]];
}
function gvHtmlTotais(){
  if (!gv.dados) return "";
  return gvTotaisBotoes().map(function(x){
    return '<button type="button" class="gv-total' + (x[3] ? " gv-total-ativo" : "") + '" data-total="' + esc(x[0]) + '" aria-pressed="' + (x[3] ? "true" : "false") + '" data-foco="' + esc("t:" + x[0]) + '">' +
      esc(x[1]) + ' <b>' + esc(x[2]) + '</b></button>';
  }).join("");
}
function gvHtmlBarra(){
  var s = gvSelecionadas();
  if (!s.length) return "";
  var acoes = gvAcoesComuns(s), h = '<span class="gv-barra-n" role="status">' + esc(s.length) + (s.length === 1 ? " selecionada" : " selecionadas") + '</span>';
  acoes.forEach(function(a){ h += '<button type="button" class="gv-massa' + (a === "pronta" ? " primario" : "") + '" data-massa="' + esc(a) + '">' + esc(GV_ROTULO_ACAO[a]) + '</button>'; });
  if (!acoes.length) h += '<span class="gv-barra-motivo">' + esc(gvMotivoSemAcao(s)) + '</span>';
  return h + '<button type="button" class="gv-limpar-sel" id="gvLimparSel">Limpar seleção</button>';
}

/* ---------- desenhar (sem piscar, sem perder foco) ---------- */
function gvTextoAssinaturaTela(){
  return [gv.assinatura, JSON.stringify(gv.filtros), Object.keys(gv.sel).sort().join(","), JSON.stringify(gv.recolhidos), gv.modoSel].join("|");
}
function gvPodeDesenhar(){ return !$("gvDlg").open && !$("gvMenu").open; }
function gvFocoAtual(){
  var a = document.activeElement;
  return a && $("aba-governanca").contains(a) && a.dataset && a.dataset.foco ? a.dataset.foco : null;
}
function gvDevolverFoco(chave){
  if (!chave) return;
  var el = $("aba-governanca").querySelector('[data-foco="' + chave.replace(/(["\\])/g, "\\$1") + '"]');
  if (el && !el.disabled) el.focus();
}
function gvDesenharControles(){
  var f = gv.filtros;
  if (document.activeElement !== $("gvBusca")) $("gvBusca").value = f.busca;
  $("gvAndar").value = f.andar; $("gvSituacao").value = f.situacao;
  [["gvChipSujas", f.situacao === "suja"], ["gvChipArrumacao", f.situacao === "em_arrumacao"], ["gvChipChegam", f.chegada], ["gvChipSaem", f.saida]].forEach(function(c){
    $(c[0]).setAttribute("aria-pressed", c[1] ? "true" : "false"); $(c[0]).classList.toggle("gv-chip-ativo", c[1]);
  });
  $("gvSelecionar").setAttribute("aria-pressed", gv.modoSel ? "true" : "false");
  $("gvSelecionar").textContent = gv.modoSel ? "Sair da seleção" : "Selecionar";
  mostrar($("gvTodos"), gv.modoSel);
  mostrar($("gvRestaurar"), gvFiltroAtivo(f));
  $("gvLista").classList.toggle("gv-modo-sel", gv.modoSel);
  $("aba-governanca").classList.toggle("gv-offline", gv.offline);
  gvTravar();
}
function gvTravar(){        // sem conexão ou com ação em andamento, os botões de ação ficam desligados (sem falso sucesso)
  document.querySelectorAll("#aba-governanca .gv-principal, #aba-governanca .gv-massa").forEach(function(b){ b.disabled = (gv.offline || gv.ocupado) && b !== document.activeElement; });   /* o botão com foco não desliga: senão o teclado perderia o lugar */
}
function gvDesenharCabecalho(){
  if (!gv.dados) return;
  $("gvData").textContent = gvDataBR(gv.dados.hoje);
  $("gvHora").textContent = gv.horaDados ? "Atualizado às " + gv.horaDados : "";
}
function gvDesenhar(){
  gvDesenharControles(); gvDesenharCabecalho();
  var tela = gvTextoAssinaturaTela();
  if (tela === gv.desenhado) return;
  if (!gvPodeDesenhar()){ gv.pendente = true; return; }
  gv.pendente = false;
  var foco = gvFocoAtual();
  $("gvLista").innerHTML = gvHtmlLista();
  $("gvTotais").innerHTML = gvHtmlTotais();
  $("gvBarra").innerHTML = gvHtmlBarra();
  var temBarra = $("gvBarra").childNodes.length > 0;
  mostrar($("gvBarra"), temBarra);
  $("aba-governanca").classList.toggle("gv-com-barra", temBarra);
  gv.desenhado = tela;
  gvTravar();
  gvDevolverFoco(foco);
}
function gvLimparSelecaoInvalida(){        // seleção só guarda unidades que ainda existem e aceitam ação
  Object.keys(gv.sel).forEach(function(u){ var i = gvItem(u); if (!i || i.situacao === "interditada") delete gv.sel[u]; });
}

/* ---------- carregar (polling) ---------- */
function gvAvisarMudancas(antes, depois){
  var mud = gvMudancas(antes, depois).filter(function(m){ return gvCorresponde(gvItem(m.u), gv.filtros); }).slice(0, 3);
  if (mud.length) gvAnunciar("Atualizado: " + mud.map(function(m){ return m.u + " agora " + GV_ROTULO[m.para].toLowerCase(); }).join(", "));
}
function gvAplicar(d){
  var antes = gv.dados ? gv.dados.unidades : null, nova = gvAssinatura(d);
  gv.offline = false; gv.horaDados = d.agora;
  if (nova !== gv.assinatura){
    gv.dados = d; gv.assinatura = nova; gvLimparSelecaoInvalida();
    if (antes) gvAvisarMudancas(antes, d.unidades);
  } else { gv.dados.agora = d.agora; }
  mostrar($("gvOffline"), false);
  gvDesenhar();
}
function gvFalhou(){
  gv.offline = true;
  $("gvOfflineTxt").textContent = "Sem conexão. Mostrando dados de " + (gv.horaDados || "antes") + ".";
  mostrar($("gvOffline"), true);
  gvDesenhar();
}
function gvCarregar(){
  var meu = ++gv.seq;
  return api("GET", "/api/governanca").then(function(r){
    if (meu !== gv.seq) return;
    if (r.ok) gvAplicar(r.dados); else gvFalhou();
  }).catch(function(){ if (meu === gv.seq) gvFalhou(); });
}
function gvAbaAtiva(){ return $("aba-governanca").classList.contains("ativa"); }
function gvLigarPolling(){
  clearInterval(gv.timer);
  gv.timer = setInterval(function(){ if (gvAbaAtiva() && !document.hidden && !gv.ocupado) gvCarregar(); }, GV_INTERVALO);
}

/* ---------- diálogo genérico (confirmação, texto, histórico) ---------- */
function gvDialogo(o){
  return new Promise(function(resolve){
    var dlg = $("gvDlg"), campo = $("gvDlgCampo"), lista = $("gvDlgLista");
    $("gvDlgTit").textContent = o.titulo; $("gvDlgTexto").textContent = o.texto || "";
    mostrar(campo, !!o.campo); mostrar(lista, !!o.lista);
    lista.textContent = "";
    (o.lista || []).forEach(function(t){ var li = document.createElement("li"); li.textContent = t; lista.appendChild(li); });
    if (o.campo){ $("gvDlgRotulo").textContent = o.campo.rotulo; $("gvDlgValor").value = o.campo.valor || ""; gvContador(); }
    $("gvDlgAviso").textContent = "";
    $("gvDlgOk").textContent = o.ok || "Confirmar"; mostrar($("gvDlgOk"), !!o.ok);
    $("gvDlgNao").textContent = o.nao || "Cancelar";
    var fim = function(v){ dlg.removeEventListener("close", aoFechar); resolve(v); };
    var aoFechar = function(){ fim(dlg.returnValue === "ok" ? (o.campo ? $("gvDlgValor").value : true) : null); };
    dlg.returnValue = ""; dlg.addEventListener("close", aoFechar);
    dlg.showModal();
    (o.campo ? $("gvDlgValor") : $("gvDlgOk")).focus();
  });
}
function gvContador(){ $("gvDlgContador").textContent = $("gvDlgValor").value.length + "/140"; }
$("gvDlgValor").addEventListener("input", gvContador);
$("gvDlgForm").addEventListener("submit", function(ev){
  ev.preventDefault();
  if (!$("gvDlgCampo").classList.contains("oculto") && $("gvDlgRotulo").dataset.obrigatorio === "1" && !$("gvDlgValor").value.trim()){
    $("gvDlgAviso").textContent = "Preencha este campo."; return;
  }
  $("gvDlg").close("ok");
});
$("gvDlgNao").addEventListener("click", function(){ $("gvDlg").close("nao"); });
$("gvDlg").addEventListener("close", function(){ if (gv.pendente) setTimeout(gvDesenhar, 0); });

/* ---------- executar ações ---------- */
function gvMensagem(txt, tipo, tentar){
  var m = $("gvMsg"); m.className = "gv-msg" + (tipo ? " gv-msg-" + tipo : ""); m.textContent = "";
  var s = document.createElement("span"); s.textContent = txt; m.appendChild(s);
  if (tentar){
    var b = document.createElement("button"); b.type = "button"; b.id = "gvTentar"; b.textContent = "Tentar de novo"; m.appendChild(b);
  }
  mostrar(m, !!txt); gvAnunciar(txt);
}
function gvLimparMensagem(){ mostrar($("gvMsg"), false); $("gvMsg").textContent = ""; }
function gvCorpo(acao, itens, extra){
  var c = {acao: acao, unidades: itens.map(function(i){ return {u: i.u, versao: i.versao}; })};
  Object.keys(extra || {}).forEach(function(k){ c[k] = extra[k]; });
  return c;
}
function gvPoderDesfazer(acao, r){
  return (acao === "pronta" || acao === "iniciar") && pode("governanca.atualizar") && r.resultados.some(function(x){ return x.resultado === "ok"; });
}
function gvMostrarDesfazer(acao, r, itens){
  var feitas = r.resultados.filter(function(x){ return x.resultado === "ok"; });
  $("gvToastTxt").textContent = gvResumoResultado(r.resultados, itens.length) + ".";
  $("gvDesfazer").onclick = function(){
    gvEsconderToast();
    var volta = feitas.map(function(x){ return {u: x.u, versao: x.versao}; });
    gv.ocupado = true;
    api("POST", "/api/governanca/acao", {acao: "suja", unidades: volta}).then(function(d){
      gv.ocupado = false;
      gvMensagem(d.ok ? "Desfeito." : (d.dados.erro || "Não foi possível desfazer."), d.ok ? "ok" : "erro");
      gvCarregar();
    }).catch(function(){ gv.ocupado = false; gvMensagem("Sem conexão com o servidor.", "erro"); });
  };
  mostrar($("gvToast"), true);
  clearTimeout(gv.undoTimer); gv.undoTimer = setTimeout(gvEsconderToast, GV_UNDO_MS);
}
function gvEsconderToast(){ clearTimeout(gv.undoTimer); mostrar($("gvToast"), false); }
function gvAposSucesso(acao, r, itens){
  var texto = gvResumoResultado(r.resultados, itens.length);
  itens.forEach(function(i){ delete gv.sel[i.u]; });
  gvMensagem(texto + ".", "ok");
  if (gvPoderDesfazer(acao, r)) gvMostrarDesfazer(acao, r, itens);
}
function gvAposErro(r, tentar){
  var d = r.dados || {};
  if (r.status === 409 && d.conflitos){
    var sel = gvSelecaoSemConflitos(Object.keys(gv.sel), d.conflitos);
    gv.sel = {}; sel.forEach(function(u){ gv.sel[u] = true; });
    gvMensagem("Não foi feito nada. " + d.conflitos.map(gvTextoConflito).join("; ") + ".", "erro", tentar);
  } else gvMensagem(d.erro || "Não foi possível concluir a ação.", "erro", false);
}
function gvEnviar(acao, itens, extra){
  gv.ocupado = true; gvDesenhar();
  var corpo = gvCorpo(acao, itens, extra);
  return api("POST", "/api/governanca/acao", corpo).then(function(r){
    gv.ocupado = false;
    if (r.ok) gvAposSucesso(acao, r.dados, itens);
    else if (r.status === 422 && r.dados.precisa_confirmar_saida && !(extra && extra.confirmou_saida)) return gvPerguntarSaida(acao, itens, extra);
    else gvAposErro(r, true);
    return gvCarregar();
  }).catch(function(){ gv.ocupado = false; gvMensagem("Sem conexão com o servidor.", "erro", true); gvDesenhar(); });
}
function gvPerguntarSaida(acao, itens, extra){
  return gvDialogo({titulo: "O hóspede já saiu?", texto: "Confirme que o hóspede já deixou a unidade para continuar.", ok: "Sim, já saiu", nao: "Ainda não"}).then(function(v){
    gv.ocupado = false;
    if (v) return gvEnviar(acao, itens, Object.assign({}, extra, {confirmou_saida: true}));
    gvDesenhar();
  });
}
function gvNomesCurtos(itens){ return itens.length === 1 ? "o " + gvNomeUnidade(itens[0].u) : itens.length + " unidades"; }
function gvPedir(acao, itens){          // pergunta o que a ação exige e envia
  gvLimparMensagem(); gv.tentar = {acao: acao, us: itens.map(function(i){ return i.u; })};
  if (acao === "suja"){
    var saiu = gvPrecisaConfirmarSaida(itens);
    return gvDialogo(saiu ? {titulo: "O hóspede já saiu?", texto: "Marcar " + gvNomesCurtos(itens) + " como suja.", ok: "Sim, já saiu", nao: "Ainda não"}
      : {titulo: "Marcar como suja?", texto: "Marcar " + gvNomesCurtos(itens) + " como suja?", ok: "Marcar suja"}).then(function(v){
      if (v) gvEnviar("suja", itens, saiu ? {confirmou_saida: true} : {});
    });
  }
  if (acao === "observacao")
    return gvDialogo({titulo: "Observação de " + itens.map(function(i){ return i.u; }).join(", "), campo: {rotulo: "Observação curta (até 140 caracteres)", valor: itens.length === 1 ? itens[0].obs : ""}, ok: "Salvar"}).then(function(v){
      if (v !== null) gvEnviar("observacao", itens, {obs: v});
    });
  if (acao === "manutencao_abrir"){
    $("gvDlgRotulo").dataset.obrigatorio = "1";
    return gvDialogo({titulo: "Manutenção de " + itens[0].u, campo: {rotulo: "Motivo (obrigatório, até 140 caracteres)", valor: ""}, ok: "Abrir manutenção"}).then(function(v){
      $("gvDlgRotulo").dataset.obrigatorio = "";
      if (v) gvEnviar("manutencao_abrir", itens, {motivo: v});
    });
  }
  if (acao === "manutencao_fechar")
    return gvDialogo({titulo: "Encerrar manutenção?", texto: "A unidade " + itens[0].u + " volta a ser usada.", ok: "Encerrar"}).then(function(v){
      if (v) gvEnviar("manutencao_fechar", itens, {});
    });
  if (gvPrecisaConfirmarSaida(itens))
    return gvDialogo({titulo: "O hóspede já saiu?", texto: "Confirme para " + gvNomesCurtos(itens) + ".", ok: "Sim, já saiu", nao: "Ainda não"}).then(function(v){
      if (v) gvEnviar(acao, itens, {confirmou_saida: true});
    });
  return gvEnviar(acao, itens, {});
}
function gvAcao(acao, us){
  if (gv.ocupado || gv.offline) return;
  var itens = us.map(gvItem).filter(Boolean);
  if (itens.length) gvPedir(acao, itens);
}

/* ---------- menu "..." (folha inferior no celular) ---------- */
function gvItensDoMenu(i){
  var p = i.pode || [], m = [], pr = gvBotaoPrincipal(i);
  ["iniciar", "pronta", "suja"].forEach(function(a){
    if (p.indexOf(a) >= 0 && !(pr && pr.acao === a)) m.push([a, a === "pronta" ? "Pronto direto" : GV_ROTULO_ACAO[a]]);
  });
  if (gvPodeAtualizar()) m.push(["observacao", "Observação"]);
  if (p.indexOf("manutencao_abrir") >= 0) m.push(["manutencao_abrir", "Manutenção"]);
  if (p.indexOf("manutencao_fechar") >= 0) m.push(["manutencao_fechar", "Encerrar manutenção"]);
  m.push(["historico", "Histórico"]);
  return m;
}
function gvAbrirMenu(u){
  var i = gvItem(u); if (!i) return;
  gv.menuU = u; $("gvMenuTit").textContent = gvNomeUnidade(u) + " - " + GV_ROTULO[i.situacao];
  var box = $("gvMenuItens"); box.textContent = "";
  gvItensDoMenu(i).forEach(function(x){
    var b = document.createElement("button"); b.type = "button"; b.dataset.menuAcao = x[0]; b.textContent = x[1];
    if (gv.offline && x[0] !== "historico") b.disabled = true;
    box.appendChild(b);
  });
  $("gvMenu").showModal();
  var primeiro = box.querySelector("button:not(:disabled)"); if (primeiro) primeiro.focus();
}
function gvHistorico(u){
  api("GET", "/api/governanca/" + encodeURIComponent(u) + "/eventos").then(function(r){
    var lista = r.ok ? r.dados.map(function(e){
      return e.em.slice(8, 10) + "/" + e.em.slice(5, 7) + " " + e.em.slice(11, 16) + " - " + e.por + " - " + (GV_ROTULO_ACAO[e.acao] || e.acao) + (e.para ? " (" + (GV_ROTULO[e.para] || e.para) + ")" : "");
    }) : [r.dados.erro || "Não foi possível carregar."];
    if (r.ok && !lista.length) lista = ["Nenhum registro."];
    gvDialogo({titulo: "Histórico de " + gvNomeUnidade(u), lista: lista, nao: "Fechar"});
  }).catch(function(){ gvDialogo({titulo: "Histórico", lista: ["Sem conexão com o servidor."], nao: "Fechar"}); });
}
$("gvMenuItens").addEventListener("click", function(ev){
  var b = ev.target.closest("button[data-menu-acao]"); if (!b) return;
  var u = gv.menuU, a = b.dataset.menuAcao;
  $("gvMenu").close();
  if (a === "historico") gvHistorico(u); else gvAcao(a, [u]);
});
$("gvMenuFechar").addEventListener("click", function(){ $("gvMenu").close(); });
$("gvMenu").addEventListener("close", function(){ if (gv.pendente) setTimeout(gvDesenhar, 0); });

/* ---------- seleção, filtros e cliques ---------- */
function gvAlternarSelecao(u, marcar){ if (marcar) gv.sel[u] = true; else delete gv.sel[u]; }
function gvVisiveis(){ return gvSelecionaveis(gvFiltrar(gvItens(), gv.filtros)); }
function gvSelecionarGrupo(nome, marcar){
  gvVisiveis().filter(function(i){ return i.andar === nome; }).forEach(function(i){ gvAlternarSelecao(i.u, marcar); });
}
function gvEntrarModoSel(){ gv.modoSel = true; }
function gvMudou(){ gvDesenhar(); }
$("gvLista").addEventListener("change", function(ev){
  var t = ev.target;
  if (t.classList.contains("gv-sel-in")){ gvAlternarSelecao(t.closest("[data-u]").dataset.u, t.checked); gvMudou(); }
  else if (t.classList.contains("gv-sel-grupo")){ gvSelecionarGrupo(t.dataset.grupo, t.checked); gvMudou(); }
});
$("gvLista").addEventListener("click", function(ev){
  var t = ev.target, b;
  if ((b = t.closest(".gv-principal"))){ gvAcao(b.dataset.acao, [b.dataset.u]); return; }
  if ((b = t.closest(".gv-mais"))){ gvAbrirMenu(b.dataset.mais); return; }
  if ((b = t.closest(".gv-recolher"))){ gv.recolhidos[b.dataset.grupo] = !gv.recolhidos[b.dataset.grupo]; gvSalvarRecolhidos(); gvMudou(); return; }
  if ((b = t.closest(".gv-obs"))){ gvVerObs(b.dataset.obs); return; }
  if (t.closest("#gvLimparVazio")){ gvRestaurarFiltros(); return; }
  var cartao = t.closest(".gv-card[data-u]");
  if (cartao && gv.modoSel && !t.closest("input,button,label")){ var u = cartao.dataset.u, i = gvItem(u); if (i && i.situacao !== "interditada"){ gvAlternarSelecao(u, !gv.sel[u]); gvMudou(); } }
});
function gvVerObs(u){
  var i = gvItem(u); if (!i) return;
  var partes = [];
  if (i.obs) partes.push(i.obs);
  if (i.situacao === "manutencao" && i.manutencao_motivo) partes.push("Manutenção: " + i.manutencao_motivo);
  if (i.obs_reserva) partes.push("Reserva: " + i.obs_reserva);
  gvDialogo({titulo: "Observação de " + gvNomeUnidade(u), texto: partes.join("\n") || "Sem observação.", nao: "Fechar"});
}
/* toque longo no cartão (celular) entra no modo de seleção */
$("gvLista").addEventListener("pointerdown", function(ev){
  var c = ev.target.closest(".gv-card[data-u]");
  if (!c || ev.target.closest("input,button,label") || ev.pointerType === "mouse") return;
  clearTimeout(gv.longo);
  gv.longo = setTimeout(function(){ var i = gvItem(c.dataset.u); if (i && i.situacao !== "interditada"){ gvEntrarModoSel(); gvAlternarSelecao(i.u, true); gvMudou(); } }, 550);
});
["pointerup", "pointermove", "pointercancel", "pointerleave"].forEach(function(e){ $("gvLista").addEventListener(e, function(){ clearTimeout(gv.longo); }); });

function gvRestaurarFiltros(){ gv.filtros = Object.assign({}, GV_FILTRO_VAZIO); gvMudou(); }
function gvAlternarFiltro(chave, valor){ gv.filtros[chave] = gv.filtros[chave] === valor ? GV_FILTRO_VAZIO[chave] : valor; gvMudou(); }
$("gvAndar").addEventListener("change", function(){ gv.filtros.andar = this.value; gvMudou(); });
$("gvSituacao").addEventListener("change", function(){ gv.filtros.situacao = this.value; gvMudou(); });
$("gvBusca").addEventListener("input", function(){ gv.filtros.busca = this.value; gvMudou(); });
$("gvChipSujas").addEventListener("click", function(){ gvAlternarFiltro("situacao", "suja"); });
$("gvChipArrumacao").addEventListener("click", function(){ gvAlternarFiltro("situacao", "em_arrumacao"); });
$("gvChipChegam").addEventListener("click", function(){ gvAlternarFiltro("chegada", true); });
$("gvChipSaem").addEventListener("click", function(){ gvAlternarFiltro("saida", true); });
$("gvRestaurar").addEventListener("click", gvRestaurarFiltros);
$("gvSelecionar").addEventListener("click", function(){ gv.modoSel = !gv.modoSel; if (!gv.modoSel) gv.sel = {}; gvMudou(); });
$("gvTodos").addEventListener("click", function(){
  var vis = gvVisiveis(), todos = vis.every(function(i){ return gv.sel[i.u]; });
  vis.forEach(function(i){ gvAlternarSelecao(i.u, !todos); }); gvMudou();
});
$("gvTotais").addEventListener("click", function(ev){
  var b = ev.target.closest("button[data-total]"); if (!b) return;
  var k = b.dataset.total;
  if (k === "saida") gvAlternarFiltro("saida", true);
  else if (k === "chegada") gvAlternarFiltro("chegada", true);
  else gvAlternarFiltro("situacao", k);
});
$("gvBarra").addEventListener("click", function(ev){
  var b = ev.target.closest("button"); if (!b) return;
  if (b.id === "gvLimparSel"){ gv.sel = {}; gvMudou(); return; }
  if (b.dataset.massa) gvAcao(b.dataset.massa, Object.keys(gv.sel));
});
$("gvMsg").addEventListener("click", function(ev){
  if (!ev.target.closest("#gvTentar") || !gv.tentar) return;
  gvCarregar().then(function(){ gvAcao(gv.tentar.acao, gv.tentar.us.filter(function(u){ return gvItem(u); })); });
});
$("gvTentarRede").addEventListener("click", gvCarregar);
$("gvFecharToast").addEventListener("click", gvEsconderToast);
$("gvFolha").addEventListener("click", function(){ document.querySelector('nav button[data-aba="camareiras"]').click(); });

/* ---------- impressão A4: lista de arrumação (hoje ou amanhã) ---------- */
function gvLinhaImpressao(i){
  var saida = i.saida_hoje ? "Out " + i.saida_hoje.hora : "", ent = i.chegada_hoje ? "In " + i.chegada_hoje.hora + " (" + gvPessoas(i.chegada_hoje.pessoas) + ")" : "";
  var obs = [i.obs, i.manutencao_motivo, i.obs_reserva ? "Reserva: " + i.obs_reserva : ""].filter(Boolean).join(" - ");
  var tag = (i.troca_hoje ? '<b class="gvi-troca">TROCA HOJE</b> ' : "") + (i.atrasada ? '<b>ATRASADA</b> ' : "");
  var sit = esc(GV_ROTULO[i.situacao]) + (gvTextoDias(i).length ? '<br><small>' + esc(gvTextoDias(i).join("; ")) + '</small>' : "");
  return '<tr class="' + (i.troca_hoje ? "gvi-linha-troca" : "") + '"><td class="gvi-u">' + esc(i.u) + '</td><td>' + tag + sit + '</td><td>' + esc(saida) + '</td><td>' + esc(ent) +
    '</td><td>' + esc(obs) + '</td><td class="gvi-caixas">&#9744; Iniciada &#9744; Pronta</td></tr>';
}
function gvHtmlImpressao(d){
  var ordem = gvOrdenarImpressao(d.unidades, UNIDADES), atual = 0;
  var h = '<h2>Lista de arrumação - ' + esc(gvDataBR(d.dia)) + '</h2><p class="gvi-sub">Pousada Boa Esperança - emitida em ' + esc(gvDataBR(d.hoje)) + ' às ' + esc(d.agora) + '</p>';
  h += '<table class="gvi-tabela"><thead><tr><th>Unidade</th><th>Situação</th><th>Saída</th><th>Entrada</th><th>Observação</th><th>Feito</th></tr></thead><tbody>';
  ordem.forEach(function(i){
    var c = gvCategoriaImpressao(i);
    if (c !== atual){ atual = c; h += '<tr class="gvi-grupo"><th colspan="6">' + esc(GV_TITULO_CATEGORIA[c]) + '</th></tr>'; }
    h += gvLinhaImpressao(i);
  });
  return h + '</tbody></table>';
}
function gvPrepararImpressao(d){ $("gvImpressao").innerHTML = gvHtmlImpressao(d); }
function gvImprimir(amanha){
  var dia = amanha ? cdSomaDias(gv.dados.hoje, 1) : gv.dados.hoje;
  api("GET", "/api/governanca?dia=" + encodeURIComponent(dia)).then(function(r){
    if (!r.ok){ gvMensagem(r.dados.erro || "Não foi possível preparar a impressão.", "erro"); return; }
    gvPrepararImpressao(r.dados);
    document.body.classList.add("imp-governanca"); window.print();
    document.body.classList.remove("imp-governanca");
  }).catch(function(){ gvMensagem("Sem conexão com o servidor.", "erro"); });
}
window.addEventListener("afterprint", function(){ document.body.classList.remove("imp-governanca"); });
$("gvImprimirHoje").addEventListener("click", function(){ gvImprimir(false); });
$("gvImprimirAmanha").addEventListener("click", function(){ gvImprimir(true); });

/* ---------- início ---------- */
function gvAbrirAba(){ gvIniciarUmaVez(); gvCarregar(); }
function gvIniciarUmaVez(){ if (!gv.aberto){ gv.aberto = true; gvLerRecolhidos(); gvLigarPolling(); gvDesenhar(); } }
document.querySelector('nav button[data-aba="governanca"]').addEventListener("click", gvAbrirAba);
