"use strict";
/* Calendário e faixa de resumo do dia (menus "Calendário" e "Mapa da reserva").
 *
 * Parte 1 (funções puras, sem tela): contam UNIDADES (nunca reservas), usam só datas AAAA-MM-DD (texto) e podem ser
 * testadas em node (tests/js/calendario_logica.js). Parte 2: a tela, que usa de app.js: $, esc, pode, reservas,
 * UNIDADES, OCUPADAS, hojeISO, abrirForm, reservaPorId, desenhar, carregar, mostrar, dataReal.
 *
 * Semântica (o sistema ainda NÃO registra chegada/saída efetiva; tudo vem das datas das reservas):
 *  - reserva = unidade + [entrada, saída); a noite do dia D está ocupada se entrada <= D < saída.
 *  - Check-in a partir das 14h, check-out até as 12h.
 *  - "Agora" só existe para o dia de hoje: ocupa a unidade quem dorme (entrada < D < saída), quem sai hoje e ainda não
 *    passou das 12h, e quem entra hoje e já passou das 14h. Em outro dia, "ocupados" = a noite.
 *  - 24 unidades reserváveis (25 menos a interditada 104). Ocupados + vagos = 24; com interditados = 25.
 *  - Só dados que a lista de reservas já traz para quem pode ver nomes. Nada de dados financeiros, de contato ou anotações internas. */

var CD_ROTULO_PAG = {pago: "Pago", parcial: "Parcial", pousada: "Paga na pousada", gratis: "Grátis", pendente: "Pendente", conflito: "Conflito"};
var CD_ROTULO_TIPO = {socio: "Sócio do clube", convidado: "Convidado"};
var CD_ROTULO_CAT = {ins: "Check-ins", outs: "Check-outs", interditados: "Interditados", ocupados: "Ocupados", vagos: "Vagos"};
var CD_ROTULO_SIT = {chegando: "Chegando 14h", saindo: "Saindo 12h", ocupada: "Ocupado", vaga: "Vaga", interditada: "Interditada"};
var CD_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

/* ---------- Parte 1: lógica pura ---------- */
function cdPad(n){ return String(n).padStart(2, "0"); }
function cdSomaDias(s, n){        // soma dias a AAAA-MM-DD sem fuso (UTC): vira mês e ano certo
  var p = s.split("-"), d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] + n));
  return d.getUTCFullYear() + "-" + cdPad(d.getUTCMonth() + 1) + "-" + cdPad(d.getUTCDate());
}
function cdDiaSemana(s){ var p = s.split("-"); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay(); }   // 0 = domingo
function cdDataBR(s){ var p = s.split("-"); return p[2] + "/" + p[1] + "/" + p[0]; }
function cdNorm(s){ return String(s == null ? "" : s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
function cdRotuloMes(s){ var p = s.split("-"); return CD_MESES[+p[1] - 1] + " " + p[0]; }
function cdMes(s){ return s.slice(0, 7); }
function cdSomaMeses(s, n){       // primeiro dia do mês, n meses depois
  var p = s.split("-"), d = new Date(Date.UTC(+p[0], +p[1] - 1 + n, 1));
  return d.getUTCFullYear() + "-" + cdPad(d.getUTCMonth() + 1) + "-01";
}
function cdDiasDoMes(s){          // 42 dias (6 semanas, domingo primeiro) que cobrem o mês de s
  var primeiro = cdMes(s) + "-01", ini = cdSomaDias(primeiro, -cdDiaSemana(primeiro)), r = [];
  for (var k = 0; k < 42; k++) r.push(cdSomaDias(ini, k));
  return r;
}
function cdPct(parte, total){     // "29,2%": uma casa, vírgula, sem divisão por zero
  if (!(total > 0)) return "0%";
  var v = Math.round(Math.min(parte / total, 1) * 1000) / 10;
  return String(v).replace(".", ",") + "%";
}
function cdFracao(parte, total){ return total > 0 ? Math.max(0, Math.min(parte / total, 1)) : 0; }
function cdArco(frac, r){         // rosca: comprimento do arco e da circunferência (stroke-dasharray)
  var circ = 2 * Math.PI * r, f = Math.max(0, Math.min(frac, 1)), dash = f * circ;
  if (f > 0 && dash < 1.5) dash = 1.5;      // fatia pequena continua visível
  return {circ: Math.round(circ * 100) / 100, dash: Math.round(dash * 100) / 100};
}
function cdOcupaAgora(r, dia, hoje, hora){    // esta reserva ocupa a unidade "agora" (hoje) ou na noite (outros dias)?
  if (dia !== hoje) return r.i <= dia && dia < r.f;
  return (r.i < dia && dia < r.f) || (r.f === dia && hora < 12) || (r.i === dia && hora >= 14);
}
/* Estado de cada unidade no dia: interditada | vaga | ocupada | chegando | saindo | troca (sai e entra no mesmo dia). */
function cdEstados(reservas, dia, unidades, ocupadas, hoje, hora){
  var porApto = {};
  reservas.forEach(function(r){ (porApto[r.a] = porApto[r.a] || []).push(r); });
  return unidades.map(function(u){
    var e = {a: u, estado: "vaga", noite: null, saindo: null, chegando: false, agora: null};
    if (ocupadas[u]){ e.estado = "interditada"; return e; }
    (porApto[u] || []).forEach(function(r){
      if (r.i <= dia && dia < r.f && !e.noite) e.noite = r;
      if (r.f === dia && !e.saindo) e.saindo = r;
      if (!e.agora && cdOcupaAgora(r, dia, hoje, hora)) e.agora = r;
    });
    e.chegando = !!e.noite && e.noite.i === dia;
    if (e.noite) e.estado = e.chegando ? (e.saindo ? "troca" : "chegando") : "ocupada";
    else if (e.saindo) e.estado = "saindo";
    return e;
  });
}
function cdSoma(lista, f){ var t = 0; lista.forEach(function(x){ t += f(x); }); return t; }
/* Indicadores do dia (tudo em unidades). hoje = AAAA-MM-DD local; hora = 0..23 local. */
function cdIndicadores(reservas, dia, unidades, ocupadas, hoje, hora){
  var est = cdEstados(reservas, dia, unidades, ocupadas, hoje, hora), ehHoje = dia === hoje;
  var reservaveis = unidades.filter(function(u){ return !ocupadas[u]; }).length;
  var ins = est.filter(function(e){ return e.chegando; });
  var outs = est.filter(function(e){ return !!e.saindo; });
  var agora = est.filter(function(e){ return !!e.agora; });
  var noite = est.filter(function(e){ return !!e.noite; });
  var interd = est.filter(function(e){ return e.estado === "interditada"; });
  var avisos = [];
  reservas.forEach(function(r){ if (ocupadas[r.a] && r.i <= dia && dia <= r.f) avisos.push("Reserva em unidade interditada: " + r.a); });
  return {
    dia: dia, ehHoje: ehHoje, reservaveis: reservaveis, total: unidades.length, est: est, avisos: avisos,
    ins: ins.length, pessoasIns: cdSoma(ins, function(e){ return e.noite.n; }),
    outs: outs.length, pessoasOuts: cdSoma(outs, function(e){ return e.saindo.n; }),
    interditados: interd.length,
    ocupados: agora.length, pessoasOcupados: cdSoma(agora, function(e){ return e.agora.n; }),
    vagos: reservaveis - agora.length,
    momentanea: ehHoje ? {unidades: agora.length, pessoas: cdSoma(agora, function(e){ return e.agora.n; }), pct: cdPct(agora.length, reservaveis)} : null,
    prevista: {unidades: noite.length, pessoas: cdSoma(noite, function(e){ return e.noite.n; }), pct: cdPct(noite.length, reservaveis)},
    fracoes: {ins: cdFracao(ins.length, reservaveis), outs: cdFracao(outs.length, reservaveis), interditados: cdFracao(interd.length, unidades.length),
      ocupados: cdFracao(agora.length, reservaveis), vagos: cdFracao(reservaveis - agora.length, reservaveis)}
  };
}
function cdLivresNoite(reservas, dia, unidades, ocupadas){      // apartamentos livres na noite do dia (para o calendário e o mapa)
  var usadas = {}, reservaveis = unidades.filter(function(u){ return !ocupadas[u]; });
  reservas.forEach(function(r){ if (!ocupadas[r.a] && r.i <= dia && dia < r.f) usadas[r.a] = true; });
  return reservaveis.filter(function(u){ return !usadas[u]; }).length;
}
function cdFaixaDisp(n){        // faixa de cor da disponibilidade (a cor nunca vai sozinha: o número é sempre escrito)
  return n <= 0 ? "zero" : (n <= 4 ? "baixa" : (n <= 11 ? "media" : "alta"));
}
function cdSituacao(e, r){      // texto de situação de uma reserva em uma unidade no dia
  if (e.estado === "troca") return r === e.saindo ? "saindo" : "chegando";
  return r === e.noite && e.chegando ? "chegando" : (r === e.saindo ? "saindo" : "ocupada");
}
function cdLinha(e, r, bloco){ return {tipo: "reserva", r: r, a: e.a, situacao: cdSituacao(e, r), troca: e.estado === "troca", bloco: bloco || null}; }
function cdLinhasBase(est, categoria){      // linhas do dia antes da pesquisa
  var l = [];
  if (categoria === "ins") est.forEach(function(e){ if (e.chegando) l.push(cdLinha(e, e.noite)); });
  else if (categoria === "outs") est.forEach(function(e){ if (e.saindo) l.push(cdLinha(e, e.saindo)); });
  else if (categoria === "ocupados") est.forEach(function(e){ if (e.agora) l.push(cdLinha(e, e.agora)); });
  else if (categoria === "vagos") est.forEach(function(e){ if (e.estado !== "interditada" && !e.agora) l.push({tipo: "vaga", r: null, a: e.a, situacao: "vaga", saindo: e.saindo, troca: false, bloco: null}); });
  else if (categoria === "interditados") est.forEach(function(e){ if (e.estado === "interditada") l.push({tipo: "interditada", r: null, a: e.a, situacao: "interditada", troca: false, bloco: null}); });
  else {                                    // visão padrão: chegadas, saídas e quem fica, em blocos
    est.forEach(function(e){ if (e.chegando) l.push(cdLinha(e, e.noite, "ins")); });
    est.forEach(function(e){ if (e.saindo) l.push(cdLinha(e, e.saindo, "outs")); });
    est.forEach(function(e){ if (e.estado === "ocupada") l.push(cdLinha(e, e.noite, "ocup")); });
  }
  return l;
}
function cdRotuloBloco(bloco, ehHoje){       // título do bloco da tabela: "hoje" só quando o dia escolhido é hoje
  var quando = ehHoje ? "hoje" : "neste dia";
  return {ins: "Chegam " + quando, outs: "Saem " + quando, ocup: "Ocupados (ficam)"}[bloco];
}
function cdTextoBusca(l){
  var r = l.r, t = [l.a, CD_ROTULO_SIT[l.situacao]];
  if (r) t.push(r.nome, r.grupo, r.id, CD_ROTULO_TIPO[r.tipo], CD_ROTULO_PAG[r.p], l.troca ? "troca" : "");
  return cdNorm(t.join(" "));
}
/* Linhas do dia: categoria (ou null) e pesquisa (várias palavras = E, sem acento). Devolve também o total antes da pesquisa. */
function cdFiltrar(est, categoria, busca){
  var base = cdLinhasBase(est, categoria), palavras = cdNorm(busca).split(/\s+/).filter(Boolean);
  var linhas = palavras.length ? base.filter(function(l){
    var t = cdTextoBusca(l); return palavras.every(function(p){ return t.indexOf(p) >= 0; });
  }) : base;
  return {linhas: linhas, total: base.length};
}
function cdReservasDoDia(est){ return est.filter(function(e){ return e.noite || e.saindo; }).reduce(function(t, e){ return t + (e.noite ? 1 : 0) + (e.saindo ? 1 : 0); }, 0); }
function cdContarEstados(est){ var c = {}; est.forEach(function(e){ c[e.estado] = (c[e.estado] || 0) + 1; }); return c; }

/* ---------- Parte 2: a tela ---------- */
var CD_ICONES = {     // desenhos simples (24x24), só texto fixo
  chegando: "M10 17l5-5-5-5v3H3v4h7v3zM19 3h-8v2h8v14h-8v2h8a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z",
  saindo: "M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5-5-5zM4 5h8V3H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h8v-2H4V5z",
  troca: "M6.99 11L3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z",
  ocupada: "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z",
  vaga: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  interditada: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zM4 12c0-4.42 3.58-8 8-8 1.85 0 3.55.63 4.9 1.69L5.69 16.9A7.902 7.902 0 0 1 4 12zm8 8c-1.85 0-3.55-.63-4.9-1.69L18.31 7.1A7.902 7.902 0 0 1 20 12c0 4.42-3.58 8-8 8z"
};
var CD_ROTULO_ESTADO = {chegando: "Chegando", saindo: "Saindo", troca: "Troca hoje", ocupada: "Ocupada", vaga: "Vaga", interditada: "Interditada"};
var CD_ORDEM_ESTADOS = ["chegando", "saindo", "troca", "ocupada", "vaga", "interditada"];
var CD_DICA_ESTADO = {
  chegando: "Chega neste dia (check-in a partir das 14h).",
  saindo: "Sai neste dia (check-out até as 12h) e não entra ninguém: livre depois do meio-dia.",
  troca: "Um hóspede sai (até 12h) e outro entra (a partir das 14h) no mesmo dia.",
  ocupada: "Hóspede dormindo na unidade, sem entrada nem saída neste dia.",
  vaga: "Sem hóspede na noite deste dia.",
  interditada: "Unidade que não aceita reserva (fora de venda)."
};

var cdDia = null;             // dia escolhido no Calendário (null = acompanha "hoje")
var cdMesRef = null;          // primeiro dia do mês mostrado no calendário (null = mês do dia escolhido)
var cdCategoria = null;       // cartão-filtro ativo
var cdBusca = "";
var cdModo = "lista";
var mrDia = null;             // dia do resumo no mapa (null = hoje)
var cdCarregado = false;
var cdUltima = {};            // assinatura do que está na tela, por área: se nada mudou, não redesenha (sem piscar)

function cdHoje(){ return hojeISO(); }
function cdHora(){ return new Date().getHours(); }
function cdDiaAtual(){ return cdDia || cdHoje(); }
function cdMesAtual(){ return cdMesRef || (cdMes(cdDiaAtual()) + "-01"); }
function cdDiaPassado(dia){ return dia < cdHoje(); }
function cdAssinaturaDados(){
  return JSON.stringify(reservas.map(function(r){ return [r.id, r.a, r.nome, r.n, r.i, r.f, r.p, r.grupo, r.tipo, r.versao]; })) + odAssinaturaNotas();   // + só booleanos de observação
}

/* Rosca em SVG: círculo de fundo + círculo do arco (stroke-dasharray). Cores pelas classes; o número no centro. */
function cdHtmlRosca(frac, n, rotulo){
  var a = cdArco(frac, 38), h = "";
  h += '<svg class="cd-rosca" viewBox="0 0 100 100" role="img" aria-label="' + esc(rotulo) + '">';
  h += '<circle class="cd-trilha" cx="50" cy="50" r="38" fill="none" stroke-width="14"/>';
  h += '<circle class="cd-arco" cx="50" cy="50" r="38" fill="none" stroke-width="14" stroke-dasharray="' + esc(a.dash) + ' ' + esc(a.circ) + '" transform="rotate(-90 50 50)"/>';
  h += '<text class="cd-num" x="50" y="50" text-anchor="middle" dominant-baseline="central">' + esc(n) + '</text></svg>';
  return h;
}
function cdHtmlCartao(cat, titulo, ind, n, extra, rotulo, dica, ativo, comFiltro){
  var h = '<button type="button" class="cd-cartao cd-cat-' + esc(cat) + (ativo ? " cd-sel" : "") + '" data-cat="' + esc(cat) + '" data-foco="' + esc("cat:" + cat) + '"';
  h += (comFiltro ? ' aria-pressed="' + (ativo ? "true" : "false") + '"' : '') + ' title="' + esc(dica) + '">';
  h += '<span class="cd-cartao-tit">' + esc(titulo) + '</span>' + cdHtmlRosca(ind.fracoes[cat], n, rotulo);
  h += '<span class="cd-cartao-sub">' + esc(extra) + '</span></button>';
  return h;
}
function cdTextoPessoas(n){ return n + (n === 1 ? " pessoa" : " pessoas"); }
/* UMA função monta a faixa de resumo (ocupação + cinco roscas) para o Calendário e para o Mapa da reserva. */
function cdHtmlResumo(ind, catAtiva, comFiltro){
  var res = ind.reservaveis, h = "";
  h += '<div class="cd-bloco cd-ocup">';
  h += '<div class="cd-ocup-linha" title="Calculada pelas datas das reservas, com check-in às 14h e check-out às 12h; ainda não há registro de chegada real."><span class="cd-ocup-tit">Ocupação momentânea</span>';
  if (ind.momentanea) h += '<span class="cd-ocup-num">' + esc(ind.momentanea.pct) + '</span><span class="cd-ocup-pess">' + esc(cdTextoPessoas(ind.momentanea.pessoas)) + '</span>';
  else h += '<span class="cd-ocup-num">&mdash;</span><span class="cd-ocup-pess suave">só existe para hoje</span>';
  h += '</div>';
  h += '<div class="cd-ocup-linha" title="Apartamentos com hóspede na noite deste dia, pelas datas das reservas."><span class="cd-ocup-tit">Ocupação prevista (noite)</span>';
  h += '<span class="cd-ocup-num">' + esc(ind.prevista.pct) + '</span><span class="cd-ocup-pess">' + esc(cdTextoPessoas(ind.prevista.pessoas)) + '</span></div></div>';
  h += '<div class="cd-cartoes">';
  h += cdHtmlCartao("ins", "Check-ins", ind, ind.ins, cdTextoPessoas(ind.pessoasIns), "Check-ins: " + ind.ins + " de " + res + " apartamentos",
    "Chegam neste dia, a partir das 14h. A rosca é sobre os " + res + " apartamentos.", catAtiva === "ins", comFiltro);
  h += cdHtmlCartao("outs", "Check-outs", ind, ind.outs, cdTextoPessoas(ind.pessoasOuts), "Check-outs: " + ind.outs + " de " + res + " apartamentos",
    "Saem neste dia, até as 12h. A rosca é sobre os " + res + " apartamentos.", catAtiva === "outs", comFiltro);
  h += cdHtmlCartao("interditados", "Interditados", ind, ind.interditados, "fora de venda", "Interditados: " + ind.interditados + " de " + ind.total + " apartamentos",
    "Unidades que não aceitam reserva. A rosca é sobre as " + ind.total + " unidades.", catAtiva === "interditados", comFiltro);
  h += cdHtmlCartao("ocupados", "Ocupados", ind, ind.ocupados, ind.ehHoje ? "Previstos: " + ind.prevista.unidades : "na noite",
    "Ocupados: " + ind.ocupados + " de " + res + " apartamentos",
    ind.ehHoje ? "Ocupados agora, estimado pelos horários (entra 14h, sai 12h). Previstos = apartamentos ocupados na noite de hoje." : "Apartamentos com hóspede na noite deste dia.",
    catAtiva === "ocupados", comFiltro);
  h += cdHtmlCartao("vagos", "Vagos", ind, ind.vagos, ind.ehHoje ? "sem hóspede agora" : "livres na noite", "Vagos: " + ind.vagos + " de " + res + " apartamentos",
    "Apartamentos sem hóspede " + (ind.ehHoje ? "agora" : "na noite deste dia") + ". Ocupados + vagos = " + res + ".", catAtiva === "vagos", comFiltro);
  return h + '</div>';
}

/* ---------- tabela do dia ---------- */
function cdHtmlIcone(estado){
  return '<svg class="cd-icone" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"><path d="' + esc(CD_ICONES[estado]) + '"/></svg>';
}
/* As linhas e a tabela das listas ficam em operacao_dia.js (odHtmlTabela): a MESMA função serve ao Calendário e ao Mapa. */

/* ---------- mapa de apartamento (grade das 25 unidades) ---------- */
function cdHtmlCartaoApto(e, dia, criar, apagado){
  var h = '<div class="cd-apto cd-est-' + esc(e.estado) + (apagado ? " cd-apagado" : "") + '" data-apto="' + esc(e.a) + '">';
  h += '<div class="cd-apto-topo"><b class="cd-apto-num">' + esc(e.a) + '</b><span class="cd-apto-est" title="' + esc(CD_DICA_ESTADO[e.estado]) + '">' + cdHtmlIcone(e.estado) + esc(CD_ROTULO_ESTADO[e.estado]) + '</span></div>';
  function botao(r, prefixo, hora){
    return '<button type="button" class="cd-hosp" data-id="' + esc(r.id) + '" data-foco="' + esc("apto:" + e.a + ":" + prefixo) + '" title="' + esc(r.nome + " - " + cdTextoPessoas(r.n)) + '">' +
      '<span class="cd-hosp-nome">' + esc(prefixo === "saida" ? "Sai: " + r.nome : r.nome) + '</span><span class="cd-hosp-info">' + esc(cdTextoPessoas(r.n) + hora) + '</span></button>';
  }
  if (e.estado === "interditada") h += '<span class="cd-hosp-txt">Não aceita reserva</span>';
  else if (e.estado === "vaga"){
    if (criar && !cdDiaPassado(dia)) h += '<button type="button" class="cd-hosp cd-hosp-vaga" data-apto="' + esc(e.a) + '" data-foco="' + esc("apto:" + e.a + ":vaga") + '"><span class="cd-hosp-nome">Reservar</span><span class="cd-hosp-info">entrada em ' + esc(cdDataBR(dia)) + '</span></button>';
    else h += '<span class="cd-hosp-txt">Sem hóspede</span>';
  } else {
    if (e.noite) h += botao(e.noite, "noite", e.chegando ? " - entra 14h" : "");
    if (e.saindo) h += botao(e.saindo, "saida", " - sai 12h");
  }
  return h + '</div>';
}
function cdHtmlGrade(est, dia, criar, destaque){
  return est.map(function(e){ return cdHtmlCartaoApto(e, dia, criar, destaque && !destaque[e.a]); }).join("");
}
function cdHtmlLegenda(est){
  var c = cdContarEstados(est);
  return CD_ORDEM_ESTADOS.map(function(s){
    return '<span class="cd-leg cd-est-' + esc(s) + '" title="' + esc(CD_DICA_ESTADO[s]) + '">' + cdHtmlIcone(s) + esc(CD_ROTULO_ESTADO[s]) + ' <b>' + esc(c[s] || 0) + '</b></span>';
  }).join("");
}

/* ---------- calendário mensal ---------- */
function cdHtmlMes(mesRef, selecionado, hoje){
  var h = "", nomes = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"], mes = cdMes(mesRef);
  nomes.forEach(function(n){ h += '<span class="cd-sem" aria-hidden="true">' + esc(n) + '</span>'; });
  cdDiasDoMes(mesRef).forEach(function(d){
    var livres = cdLivresNoite(reservas, d, UNIDADES, OCUPADAS), wd = cdDiaSemana(d);
    var cls = "cd-dia cd-disp-" + cdFaixaDisp(livres) + (wd === 0 || wd === 6 ? " cd-fds" : "") + (d === hoje ? " cd-hoje" : "") + (d === selecionado ? " cd-sel" : "") + (cdMes(d) !== mes ? " cd-fora" : "");
    h += '<button type="button" class="' + esc(cls) + '" data-dia="' + esc(d) + '" data-foco="' + esc("dia:" + d) + '" aria-pressed="' + (d === selecionado ? "true" : "false") + '" aria-label="' +
      esc(cdDataBR(d) + (d === hoje ? " (hoje)" : "") + ": " + livres + (livres === 1 ? " apartamento livre" : " apartamentos livres")) + '">' +
      '<span class="cd-dia-n">' + esc(+d.slice(8)) + '</span><span class="cd-dia-liv"><b>' + esc(livres) + '</b> <span class="cd-liv-txt">livres</span></span></button>';
  });
  return h;
}

/* ---------- desenho (sem piscar: só refaz o que mudou, e devolve o foco) ---------- */
function cdFocoAtual(cont){
  var a = document.activeElement;
  return a && cont.contains(a) && a.dataset ? (a.dataset.foco || null) : null;
}
function cdRestaurarFoco(cont, chave){
  if (!chave) return;
  var el = cont.querySelector('[data-foco="' + chave.replace(/(["\\])/g, "\\$1") + '"]');
  if (el) el.focus();
}
function cdTrocar(cont, html){      // troca o conteúdo mantendo o foco do teclado
  var foco = cdFocoAtual(cont);
  cont.innerHTML = html;
  cdRestaurarFoco(cont, foco);
}
function cdMudou(chave, assinatura){
  if (cdUltima[chave] === assinatura) return false;
  cdUltima[chave] = assinatura;
  return true;
}
function cdPorData(el, dia){ if (document.activeElement !== el && el.value !== dia) el.value = dia; }

function cdDesenharResumoMapa(){
  var dia = mrDia || cdHoje(), hora = cdHora();
  cdPorData($("mrData"), dia);
  if (!cdMudou("mapa", [dia, hora, cdHoje(), mrCategoria, mrBusca, pode("reservas.criar"), cdAssinaturaDados()].join("|"))) return;
  var ind = cdIndicadores(reservas, dia, UNIDADES, OCUPADAS, cdHoje(), hora);
  cdTrocar($("mrResumo"), cdHtmlResumo(ind, mrCategoria, true));
  odDesenharPainelMapa(ind, dia);          // lista embutida (operacao_dia_tela.js)
}
function cdTextoFiltro(){
  var p = [];
  if (cdCategoria) p.push(CD_ROTULO_CAT[cdCategoria]);
  if (cdBusca.trim()) p.push('busca "' + cdBusca.trim() + '"');
  return p.join(" + ");
}
function cdDesenharCalendario(){
  var dia = cdDiaAtual(), hoje = cdHoje(), hora = cdHora(), criar = pode("reservas.criar");
  cdPorData($("cdData"), dia);
  var assin = [dia, hoje, hora, cdCategoria, cdBusca, cdModo, cdMesRef, criar, cdAssinaturaDados()].join("|");
  if (!cdMudou("calendario", assin)) return;
  var ind = cdIndicadores(reservas, dia, UNIDADES, OCUPADAS, hoje, hora), mesRef = cdMesAtual();
  $("cdMesTitulo").textContent = cdRotuloMes(mesRef);
  cdTrocar($("cdMes"), cdHtmlMes(mesRef, dia, hoje));
  cdTrocar($("cdResumo"), cdHtmlResumo(ind, cdCategoria, true));
  var f = cdFiltrar(ind.est, cdCategoria, cdBusca), lista = cdModo === "lista";
  cdTrocar($("cdTabela"), odHtmlTabela(f.linhas, dia, cdCategoria, odContexto(criar, odVazio(cdCategoria, cdBusca), "Reservas do dia", dia)));
  odCabecalhoCalendario(cdCategoria, dia, f.linhas);
  var destaque = null;
  if (cdCategoria || cdBusca.trim()){ destaque = {}; f.linhas.forEach(function(l){ destaque[l.a] = true; }); }
  cdTrocar($("cdGrade"), cdHtmlGrade(ind.est, dia, criar, destaque));
  $("cdLegenda").innerHTML = cdHtmlLegenda(ind.est);
  mostrar($("cdListaWrap"), lista); mostrar($("cdGrade"), !lista);
  $("cdModoLista").setAttribute("aria-pressed", lista ? "true" : "false");
  $("cdModoGrade").setAttribute("aria-pressed", lista ? "false" : "true");
  $("cdContagem").textContent = cdCategoria === null
    ? "Mostrando " + f.linhas.length + " de " + f.total + " linhas do dia (" + cdReservasDoDia(ind.est) + " reservas)" + (cdBusca.trim() ? " - filtro: " + cdTextoFiltro() : "")
    : "Mostrando " + f.linhas.length + " de " + f.total + " (" + cdTextoFiltro() + ")";
  mostrar($("cdLimpar"), !!(cdCategoria || cdBusca.trim()));
  $("cdAvisos").textContent = ind.avisos.join(" | ");
  $("cdCabImp").textContent = "Mapa da reserva - " + cdDataBR(dia);
  $("cdSubImp").textContent = "Pousada Boa Esperança - chegadas " + ind.ins + " (" + ind.pessoasIns + " pessoas), saídas " + ind.outs + ", ocupados na noite " +
    ind.prevista.unidades + " (" + ind.prevista.pessoas + " pessoas), vagas na noite " + (ind.reservaveis - ind.prevista.unidades) +
    (cdTextoFiltro() ? ". Filtro: " + cdTextoFiltro() : "");
}
function cdDesenharTudo(){
  if (!cdCarregado) return;
  cdDesenharResumoMapa();
  cdDesenharCalendario();
  cdGovAnotar();
}

/* ---------- eventos ---------- */
function cdIrParaDia(d){ if (dataReal(d)){ cdDia = d; cdMesRef = null; cdDesenharTudo(); } }
function cdAbrirReservaDe(el, dia){      // dia: o dia da lista (no Mapa é o dia do resumo; no Calendário, o dia escolhido)
  var b = el.closest("[data-id], [data-apto]");
  if (!b) return;
  if (b.dataset.id){ var r = reservaPorId(b.dataset.id); if (r) abrirReserva(r); }
  else if (pode("reservas.criar") && !OCUPADAS[b.dataset.apto] && (dia || cdDiaAtual()) >= cdHoje()) abrirForm(null, {a: b.dataset.apto, i: dia || cdDiaAtual()});
}
function cdImprimir(){
  document.body.classList.add("imp-calendario");
  window.print();
  document.body.classList.remove("imp-calendario");
}
function cdVerNoCalendario(cat){       // clique em um indicador do Mapa da reserva: abre o Calendário naquele dia e filtro
  var b = document.querySelector('nav button[data-aba="calendario"]');
  if (!b || b.classList.contains("oculto") || b.classList.contains("oculto-pref")) return;
  cdDia = mrDia; cdCategoria = cat; cdMesRef = null;
  b.click(); cdDesenharTudo();
}
function cdLigarEventos(){
  $("cdMes").addEventListener("click", function(ev){ var b = ev.target.closest("[data-dia]"); if (b) cdIrParaDia(b.dataset.dia); });
  $("cdMesAnt").addEventListener("click", function(){ cdMesRef = cdSomaMeses(cdMesAtual(), -1); cdDesenharTudo(); });
  $("cdMesProx").addEventListener("click", function(){ cdMesRef = cdSomaMeses(cdMesAtual(), 1); cdDesenharTudo(); });
  $("cdMesHoje").addEventListener("click", function(){ cdMesRef = null; cdDia = null; cdDesenharTudo(); });
  $("cdAnt").addEventListener("click", function(){ cdIrParaDia(cdSomaDias(cdDiaAtual(), -1)); });
  $("cdProx").addEventListener("click", function(){ cdIrParaDia(cdSomaDias(cdDiaAtual(), 1)); });
  $("cdHoje").addEventListener("click", function(){ cdDia = null; cdMesRef = null; cdDesenharTudo(); });
  $("cdData").addEventListener("change", function(){ cdIrParaDia(this.value); });
  $("cdModoLista").addEventListener("click", function(){ cdModo = "lista"; cdDesenharTudo(); });
  $("cdModoGrade").addEventListener("click", function(){ cdModo = "grade"; cdDesenharTudo(); });
  $("cdResumo").addEventListener("click", function(ev){
    var b = ev.target.closest(".cd-cartao"); if (!b) return;
    cdCategoria = cdCategoria === b.dataset.cat ? null : b.dataset.cat; cdDesenharTudo();
  });
  $("cdBusca").addEventListener("input", function(){ cdBusca = this.value; cdDesenharTudo(); });
  $("cdLimpar").addEventListener("click", function(){ cdCategoria = null; cdBusca = ""; $("cdBusca").value = ""; cdDesenharTudo(); });
  $("cdImprimir").addEventListener("click", cdImprimir);
  $("cdTabela").addEventListener("click", function(ev){ if (!odCliqueAcao(ev)) cdAbrirReservaDe(ev.target); });
  $("cdGrade").addEventListener("click", function(ev){ cdAbrirReservaDe(ev.target); });
  window.addEventListener("afterprint", function(){ document.body.classList.remove("imp-calendario"); });
  // faixa de resumo do mapa
  $("mrAnt").addEventListener("click", function(){ mrDia = cdSomaDias(mrDia || cdHoje(), -1); cdDesenharTudo(); });
  $("mrProx").addEventListener("click", function(){ mrDia = cdSomaDias(mrDia || cdHoje(), 1); cdDesenharTudo(); });
  $("mrHoje").addEventListener("click", function(){ mrDia = null; cdDesenharTudo(); });
  $("mrData").addEventListener("change", function(){ if (dataReal(this.value)){ mrDia = this.value; cdDesenharTudo(); } });
}
/* ================= INTEGRAÇÃO COM A GOVERNANÇA (isolada: tudo que o Calendário sabe sobre ela está aqui) =================
 * Só para HOJE e só para quem tem governanca.ver E reservas.ver: ao lado do número da unidade (tabela e mapa de apartamento) aparece
 * "Suja", "Em arrumação" ou "Pronta" (e "Pronta · pode entrar" quando também chega hoje). Os selos são colocados DEPOIS do desenho,
 * por DOM (textContent), sem mexer nas funções que montam a lista do dia e a coluna de ações. Dados: GET /api/governanca (já filtrado). */
var CD_GOV_ROTULO = {suja: "Suja", em_arrumacao: "Em arrumação", pronta: "Pronta"};
var cdGov = {};               // unidade -> {situacao, chegada}
function cdGovSelo(g){        // PURA: dados de uma unidade da governança -> {classe, texto, entrar} ou null (hospedada, manutenção... não têm selo)
  if (!g || !CD_GOV_ROTULO[g.situacao]) return null;
  var entrar = g.situacao === "pronta" && !!g.chegada;
  return {classe: g.situacao, texto: CD_GOV_ROTULO[g.situacao] + (entrar ? " · pode entrar" : ""), entrar: entrar};
}
function cdGovPodeUsar(){ return pode("governanca.ver") && pode("reservas.ver"); }
function cdGovCriarSelo(g){
  var s = cdGovSelo(g), el = document.createElement("span");
  el.className = "cd-gov cd-gov-" + s.classe + (s.entrar ? " cd-gov-entrar" : "");
  el.textContent = s.texto;
  el.title = "Governança: " + s.texto;
  return el;
}
function cdGovAnotar(){       // idempotente: tira os selos antigos e põe os de agora
  document.querySelectorAll(".cd-gov").forEach(function(e){ e.remove(); });
  if (!cdGovPodeUsar() || cdDiaAtual() !== cdHoje()) return;
  document.querySelectorAll("#cdTabela .cd-apto-btn, #mrTabela .cd-apto-btn, #cdGrade .cd-apto .cd-apto-num").forEach(function(el){
    var g = cdGov[el.textContent.trim()];
    if (!cdGovSelo(g)) return;
    if (el.classList.contains("cd-apto-num")) el.parentNode.insertAdjacentElement("afterend", cdGovCriarSelo(g));   // mapa de apartamento: selo numa linha própria
    else el.parentNode.appendChild(cdGovCriarSelo(g));
  });
}
function cdGovAtualizar(){
  if (!cdGovPodeUsar()) return Promise.resolve();
  return api("GET", "/api/governanca").then(function(r){
    if (!r.ok) return;
    var novo = {};
    r.dados.unidades.forEach(function(u){ novo[u.u] = {situacao: u.situacao, chegada: !!u.chegada_hoje, nota: !!(u.obs || u.manutencao_motivo || u.tem_nota_unidade)}; });
    cdGov = novo; cdGovAnotar();
  }).catch(function(){ /* sem conexão: os selos antigos continuam até a próxima tentativa */ });
}

/* Liga a tela ao resto do app sem mexer em app.js: depois de cada redesenho/carga, atualiza as áreas novas. */
function cdIniciar(){
  var desenharOriginal = desenhar, carregarOriginal = carregar;
  desenhar = function(){ desenharOriginal(); if (!algumDialogoAberto()) cdDesenharTudo(); };
  carregar = function(){
    return carregarOriginal().then(function(){
      if ($("faixaAviso").hidden){ cdCarregado = true; cdDesenharTudo(); cdGovAtualizar(); }
    });
  };
  cdLigarEventos();
  setInterval(cdDesenharTudo, 60000);          // vira o dia e as horas 12h/14h sozinho
}

if (typeof document !== "undefined") cdIniciar();
if (typeof module !== "undefined" && module.exports){
  module.exports = {cdSomaDias: cdSomaDias, cdDiasDoMes: cdDiasDoMes, cdSomaMeses: cdSomaMeses, cdPct: cdPct, cdArco: cdArco, cdFracao: cdFracao,
    cdEstados: cdEstados, cdIndicadores: cdIndicadores, cdLivresNoite: cdLivresNoite, cdFaixaDisp: cdFaixaDisp, cdFiltrar: cdFiltrar,
    cdContarEstados: cdContarEstados, CD_ROTULO_PAG: CD_ROTULO_PAG, CD_ROTULO_TIPO: CD_ROTULO_TIPO, CD_ROTULO_SIT: CD_ROTULO_SIT, cdGovSelo: cdGovSelo, cdRotuloBloco: cdRotuloBloco, cdNorm: cdNorm, cdRotuloMes: cdRotuloMes, cdDataBR: cdDataBR};
}
