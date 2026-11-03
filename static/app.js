"use strict";
var UNIDADES = ["101","102","103","104","201","202","203","204","205","206","207","208",
  "301","302","303","304","305","306","307","308","Chalé A","Chalé B","Chalé C","Chalé D","Chalé E"];
var OCUPADAS = {"104": true};
var PAGAMENTOS = {pago:"Pago", parcial:"Parcial", pousada:"Paga na pousada", gratis:"Grátis", pendente:"Pendente", conflito:"Conflito"};
var COR_LEGENDA = ["pago","parcial","pousada","gratis","pendente","conflito"];
var SEM = ["dom","seg","ter","qua","qui","sex","sáb"];

var reservas = [];
var editando = null;          // reserva em edição (objeto) ou null
var inicioMapa = hojeISO();
var inicioFolha = segunda(hojeISO());
var arrastando = false;       // há um arraste no mapa em andamento (mapa_arrastar.js): o redesenho espera
var redesenhoPendente = false;
var orientacao = "paisagem";  // papel da impressão e do PDF: "paisagem" ou "retrato"

/* ---------- utilidades ---------- */
function esc(s){
  return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
  });
}
function semAcento(s){ return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
function iso(d){ return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0"); }
function parse(s){ var p = s.split("-"); return new Date(+p[0], +p[1]-1, +p[2], 12); }
function hojeISO(){ return iso(new Date()); }
function somaDias(s, n){ var d = parse(s); d.setDate(d.getDate()+n); return iso(d); }
function difDias(a, b){ return Math.round((parse(b) - parse(a)) / 86400000); }
function segunda(s){ var d = parse(s); var w = (d.getDay()+6) % 7; return somaDias(s, -w); }
function br(s){ var p = s.split("-"); return p[2] + "/" + p[1]; }
function dataReal(s){ // valida data real AAAA-MM-DD
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s || "")) return false;
  return iso(parse(s)) === s;
}
function aviso(msg){
  var t = document.getElementById("toast");
  t.textContent = msg; t.style.display = "block";
  clearTimeout(aviso.t); aviso.t = setTimeout(function(){ t.style.display = "none"; }, 3500);
}
function $(id){ return document.getElementById(id); }

/* ---------- Tipo de hóspede e valor da diária (dinheiro sempre em centavos inteiros) ---------- */
var TIPOS = {socio: "Sócio do clube", convidado: "Convidado"};
var MAX_DIARIA_CENTAVOS = 100000000;
/* "123,45" -> 12345. Vazio -> null. Inválido (letras, negativo, ponto decimal, grande demais) -> undefined. Sem float. */
function reaisParaCentavos(texto){
  var t = String(texto == null ? "" : texto).trim();
  if (t === "") return null;
  var m = /^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/.exec(t);
  if (!m) return undefined;
  var inteiro = m[1].replace(/\./g, "");
  if (inteiro.length > 9) return undefined;
  var centavos = parseInt(inteiro, 10) * 100 + parseInt((m[2] || "").padEnd(2, "0") || "0", 10);
  return centavos <= MAX_DIARIA_CENTAVOS ? centavos : undefined;
}
/* 12345 -> "123,45" (para o campo) ; com milhar = true -> "1.234,56" (para textos) */
function centavosParaReais(c, milhar){
  var inteiro = String(Math.floor(c / 100)), cent = String(c % 100).padStart(2, "0");
  if (milhar) inteiro = inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return inteiro + "," + cent;
}

/* ---------- API ---------- */
var sessao = {csrf: "", usuario: null, permissoes: []};
function pode(cap){ return sessao.permissoes.indexOf(cap) >= 0; }
function irParaLogin(){ window.location.replace("/login"); }
function cabecalhos(json){
  var h = {"X-CSRF-Token": sessao.csrf};
  if (json) h["Content-Type"] = "application/json";
  return h;
}
function lerResposta(r){
  if (r.status === 401){ irParaLogin(); }
  return r.json().catch(function(){ return {}; }).then(function(j){ return {ok: r.ok, status: r.status, dados: j}; });
}
function api(metodo, url, corpo){
  var muda = metodo !== "GET";
  var opc = {method: metodo, credentials: "same-origin", headers: muda ? cabecalhos(true) : {}};
  if (muda) opc.body = JSON.stringify(corpo === undefined ? {} : corpo);
  return fetch(url, opc).then(lerResposta);
}
function enviarArquivo(url, formData){
  return fetch(url, {method: "POST", credentials: "same-origin", headers: cabecalhos(false), body: formData}).then(lerResposta);
}
function faixa(mostrar){ $("faixaAviso").hidden = !mostrar; }
function carregar(){
  return api("GET", "/api/reservas").then(function(r){
    if (r.ok){ reservas = r.dados; faixa(false); desenhar(); }
    else faixa(true);
  }).catch(function(){ faixa(true); });
}

/* ---------- cálculos ---------- */
function totais(dia){
  var o = {entradas:0, saidas:0, noite:0, cafe:0, livres:0, ocupadas:0};
  reservas.forEach(function(r){
    if (r.i === dia) o.entradas++;
    if (r.f === dia) o.saidas++;
    if (r.i <= dia && dia < r.f){ o.noite += r.n; o.ocupadas++; }
    if (r.i < dia && dia <= r.f) o.cafe += r.n;
  });
  var reservaveis = UNIDADES.filter(function(u){ return !OCUPADAS[u]; }).length;
  o.livres = Math.max(0, reservaveis - o.ocupadas);
  return o;
}
function idsEmConflito(){
  var ids = {};
  for (var x = 0; x < reservas.length; x++) for (var y = x+1; y < reservas.length; y++){
    var a = reservas[x], b = reservas[y];
    if (a.a === b.a && a.i < b.f && b.i < a.f){ ids[a.id] = true; ids[b.id] = true; }
  }
  return ids;
}
function conflitoCom(apto, i, f, ignorarId){
  for (var k = 0; k < reservas.length; k++){
    var r = reservas[k];
    if (r.a === apto && r.id !== ignorarId && r.i < f && i < r.f) return r;
  }
  return null;
}

/* ---------- Mapa ---------- */
/* Posição (em px, dentro da linha) de uma barra de meio-dia a meio-dia; larg <= 0 = fora da janela mostrada. */
function posicaoBarra(i, f, d0, n, w){
  var ini = Math.max(difDias(d0, i) + 0.5, 0), fim = Math.min(difDias(d0, f) + 0.5, n);
  return {esq: ini * w, larg: (fim - ini) * w};
}
function htmlBarra(r, cls, d0, n, w){
  var pos = posicaoBarra(r.i, r.f, d0, n, w), editavel = pode("reservas.editar");
  var tooltip = (r.grupo ? "Grupo: " + r.grupo + " - " : "") + r.nome + (TIPOS[r.tipo] ? " (" + TIPOS[r.tipo] + ")" : "") + " - " + r.n +
    " pessoa(s) - " + br(r.i) + " a " + br(r.f);
  return '<button type="button" class="barra-res ' + esc(cls) + '" data-id="' + esc(r.id) + '" data-esq="' + pos.esq + '" data-larg="' + pos.larg +
    '" title="' + esc(tooltip) + '">' +
    (editavel ? '<span class="alca alca-e" data-lado="e" title="Arraste para alterar a entrada" aria-label="Alterar a entrada"></span>' : '') +
    esc(r.grupo || r.nome) + ' (' + esc(r.n) + ')' +
    (editavel ? '<span class="alca alca-s" data-lado="s" title="Arraste para alterar a saída" aria-label="Alterar a saída"></span>' : '') + '</button>';
}
/* Linha dos meses acima dos dias: um bloco por mês, com a largura dos dias que ele ocupa (a largura é aplicada pelo JS, sem style inline). */
var MESES_NOME = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"];
function htmlMeses(dias, w){
  var h = "", k = 0;
  while (k < dias.length){
    var mes = dias[k].slice(0, 7), j = k;
    while (j < dias.length && dias[j].slice(0, 7) === mes) j++;
    h += '<div class="mes-seg" data-larg="' + esc((j - k) * w) + '">' + esc(MESES_NOME[+mes.slice(5) - 1] + " " + mes.slice(0, 4)) + '</div>';
    k = j;
  }
  return h;
}
/* Largura de cada dia: o mínimo de sempre, mas os dias se alargam para ocupar a largura livre da tela (nomes mais legíveis). */
var LARGURA_MIN_DIA = {7: 56, 14: 42, 28: 34}, LARGURA_MAX_DIA = 120, LARGURA_ROTULO = 102;
function larguraDoDia(n){
  var livre = $("mapa").parentNode.clientWidth - LARGURA_ROTULO;        // 0 se a aba está escondida: cai no mínimo
  return Math.max(LARGURA_MIN_DIA[n] || 42, Math.min(Math.floor(livre / n), LARGURA_MAX_DIA));
}
/* O mapa é montado em partes pequenas: meses, dias, disponibilidade, uma linha por unidade e os totais do rodapé. */
function classeDoDia(d, hoje){ var wd = parse(d).getDay(); return (wd === 0 || wd === 6 ? " fds" : "") + (d === hoje ? " hoje" : ""); }
function htmlLinhaDias(dias, hoje){
  var h = '<div class="linha cab"><div class="lab">Unidade</div><div class="celulas">';
  dias.forEach(function(d){
    h += '<div class="d' + classeDoDia(d, hoje) + '">' + SEM[parse(d).getDay()] + '<b>' + esc(d.slice(8)) + '</b></div>';
  });
  return h + '</div></div>';
}
/* Apartamentos livres por noite, com número e cor, logo abaixo do cabeçalho dos dias. */
function htmlLinhaDisponibilidade(dias, hoje){
  var h = '<div class="linha disp"><div class="lab" title="Apartamentos livres na noite de cada dia">Disponibilidade</div><div class="celulas">';
  dias.forEach(function(d){
    var livres = cdLivresNoite(reservas, d, UNIDADES, OCUPADAS);
    h += '<div class="d disp-' + esc(cdFaixaDisp(livres)) + classeDoDia(d, hoje) + '" title="' + esc(livres + " apartamento(s) livre(s) na noite de " + br(d)) + '"><b>' + esc(livres) + '</b></div>';
  });
  return h + '</div></div>';
}
function htmlLinhaUnidade(u, dias, w, hoje, conflitos){
  var ocup = !!OCUPADAS[u], fim = somaDias(dias[0], dias.length);
  var h = '<div class="linha' + (ocup ? " ocup" : "") + '" data-apto="' + esc(u) + '"><div class="lab">' + esc(u) + '</div><div class="celulas">';
  dias.forEach(function(d){
    h += '<div class="d' + classeDoDia(d, hoje) + '" data-apto="' + esc(u) + '" data-dia="' + esc(d) + '"></div>';
  });
  if (ocup) h += '<div class="rotulo-ocup">OCUPADO</div>';
  reservas.forEach(function(r){
    if (r.a !== u || r.f <= dias[0] || r.i >= fim) return;
    h += htmlBarra(r, conflitos[r.id] ? "conflito" : r.p, dias[0], dias.length, w);
  });
  return h + '</div></div>';
}
/* Totais do rodapé. Os apartamentos livres NÃO se repetem aqui: já estão na linha Disponibilidade, lá em cima. */
function htmlRodapeMapa(dias, hoje){
  var h = "";
  [["Entradas","entradas"],["Saídas","saidas"],["Hóspedes na noite","noite"],["Café da manhã","cafe"]].forEach(function(par){
    h += '<div class="linha rod"><div class="lab">' + esc(par[0]) + '</div><div class="celulas">';
    dias.forEach(function(d){ h += '<div class="d' + classeDoDia(d, hoje) + '">' + esc(totais(d)[par[1]]) + '</div>'; });
    h += '</div></div>';
  });
  return h;
}
/* Larguras e posições são aplicadas pelo JS (a política de segurança bloqueia style inline). */
function posicionarMapa(m){
  m.querySelectorAll(".mes-seg").forEach(function(b){ b.style.width = b.dataset.larg + "px"; });
  m.querySelectorAll(".barra-res").forEach(function(b){ b.style.left = b.dataset.esq + "px"; b.style.width = b.dataset.larg + "px"; });
}
function desenharMapa(){
  var n = +$("mSemanas").value, w = larguraDoDia(n), hoje = hojeISO(), conf = idsEmConflito();
  var dias = []; for (var k = 0; k < n; k++) dias.push(somaDias(inicioMapa, k));
  var h = '<div class="linha mes"><div class="lab"></div><div class="celulas">' + htmlMeses(dias, w) + '</div></div>';
  h += htmlLinhaDias(dias, hoje) + htmlLinhaDisponibilidade(dias, hoje);
  UNIDADES.forEach(function(u){ h += htmlLinhaUnidade(u, dias, w, hoje, conf); });
  h += htmlRodapeMapa(dias, hoje);
  var m = $("mapa");
  m.style.setProperty("--w", w + "px");
  m.dataset.inicio = dias[0]; m.dataset.dias = n; m.dataset.w = w;      // a geometria que o arraste usa (mapa_arrastar.js)
  m.classList.toggle("pode-mover", pode("reservas.editar"));
  m.classList.toggle("pode-criar", pode("reservas.criar"));
  m.innerHTML = h;
  posicionarMapa(m);
  $("mData").value = inicioMapa;
  $("btnImportar").style.display = (pode("importar") && !reservas.length) ? "inline-block" : "none";
}

/* ---------- Folha ---------- */
function nomesLista(lista){
  return lista.length ? lista.map(function(r){ return esc(r.a) + " - " + esc(r.nome) + " (" + esc(r.n) + ")"; }).join("<br>") : '<span class="suave">-</span>';
}
function desenharFolha(){
  var h = "<thead><tr><th>Dia</th><th>Entradas</th><th>Saídas</th><th>Na noite</th><th>Café</th><th>Livres</th></tr></thead><tbody>";
  for (var k = 0; k < 7; k++){
    var d = somaDias(inicioFolha, k), t = totais(d);
    var ent = reservas.filter(function(r){ return r.i === d; });
    var sai = reservas.filter(function(r){ return r.f === d; });
    h += "<tr><td><b>" + esc(SEM[parse(d).getDay()]) + " " + esc(br(d)) + "</b></td><td>" + nomesLista(ent) + "</td><td>" + nomesLista(sai) +
      "</td><td>" + esc(t.noite) + "</td><td>" + esc(t.cafe) + "</td><td>" + esc(t.livres) + "</td></tr>";
  }
  $("tabFolha").innerHTML = h + "</tbody>";
  $("fCsv").href = "/api/export.csv?inicio=" + encodeURIComponent(inicioFolha) + "&dias=7";
  atualizarLinkPdf();
  $("folhaCab").textContent = "Folha da semana - " + br(inicioFolha) + " a " + br(somaDias(inicioFolha, 6));
}
function atualizarLinkPdf(){
  $("fPdf").href = "/api/folha.pdf?inicio=" + encodeURIComponent(inicioFolha) + "&orientacao=" + orientacao;
}

/* Papel: a escolha vale para a impressão direta (classe no body) e para o PDF; fica guardada neste navegador. */
function aplicarOrientacao(){
  document.body.classList.toggle("orient-retrato", orientacao === "retrato");
  document.querySelectorAll(".sel-orientacao").forEach(function(s){ s.value = orientacao; });
  atualizarLinkPdf();
}
try { if (localStorage.getItem("orientacao") === "retrato") orientacao = "retrato"; } catch (e) { /* sem armazenamento: usa paisagem */ }
document.querySelectorAll(".sel-orientacao").forEach(function(s){
  s.addEventListener("change", function(){
    orientacao = s.value === "retrato" ? "retrato" : "paisagem";
    try { localStorage.setItem("orientacao", orientacao); } catch (e) { /* ignora */ }
    aplicarOrientacao();
  });
});
aplicarOrientacao();
/* Imprimir direto: a classe no body faz o estilo de impressão mostrar só a folha (e não as camareiras). */
$("fImprimir").addEventListener("click", function(){
  document.body.classList.add("imp-folha");
  window.print();
  document.body.classList.remove("imp-folha");
});
window.addEventListener("afterprint", function(){ document.body.classList.remove("imp-folha"); });

/* ---------- Busca ---------- */
function desenharBusca(){
  var q = semAcento($("busca").value.trim());
  var achados = reservas.filter(function(r){
    return !q || semAcento([r.nome, r.grupo, r.a, r.extras, r.o, r.p, r.i, r.f].join(" ")).indexOf(q) >= 0;
  }).sort(function(a, b){ return a.i < b.i ? -1 : (a.i > b.i ? 1 : 0); });
  var h = achados.map(function(r){
    return '<div class="item-busca" data-id="' + esc(r.id) + '"><div><b>' + esc(r.nome) + '</b> <span class="suave">' + esc(r.a) + ' - ' + esc(r.n) +
      ' pessoa(s)' + (TIPOS[r.tipo] ? ' - ' + esc(TIPOS[r.tipo]) : '') + (r.grupo ? ' - Grupo: ' + esc(r.grupo) : '') + '</span><br><span class="suave">' + esc(r.extras) + ' ' + esc(r.o) + '</span></div><div>' + esc(br(r.i)) + ' &rarr; ' + esc(br(r.f)) +
      ' <span class="pilula ' + esc(r.p) + '">' + esc(PAGAMENTOS[r.p] || r.p) + '</span></div></div>';
  }).join("");
  $("resultados").innerHTML = h || '<p class="suave">Nenhuma reserva encontrada.</p>';
}

/* Tudo o que muda o desenho do mapa, da folha e da busca. Se for igual ao da última vez, não há o que refazer. */
function assinaturaTela(){
  return [JSON.stringify(reservas), inicioMapa, $("mSemanas").value, larguraDoDia(+$("mSemanas").value), inicioFolha, hojeISO(), $("busca").value].join("|");
}
var telaDesenhada = "";       // assinatura do que está na tela agora
function focoDaBarra(){       // id da barra do mapa que está com o foco do teclado (ou null)
  var a = document.activeElement;
  return a && a.classList && a.classList.contains("barra-res") ? a.dataset.id : null;
}
function devolverFocoBarra(id){
  var b = id ? $("mapa").querySelector('.barra-res[data-id="' + id + '"]') : null;
  if (b) b.focus();
}
function algumDialogoAberto(){ return document.querySelector("dialog[open]") !== null; }   // qualquer diálogo (formulário, conta, informações, notas...) pausa o redesenho e o polling
function desenhar(){
  if (algumDialogoAberto()) return; // não redesenha com diálogo aberto
  if (arrastando){ redesenhoPendente = true; return; }   // nem no meio de um arraste (o mapa é refeito quando soltar)
  var assinatura = assinaturaTela();
  if (assinatura === telaDesenhada) return;     // o polling de 8 s não mudou nada: não refaz (e não tira o foco do teclado)
  var foco = focoDaBarra();
  desenharMapa(); desenharFolha(); desenharBusca();
  telaDesenhada = assinatura;
  devolverFocoBarra(foco);
}

/* ---------- Formulário ---------- */
function mostrar(el, sim){ el.classList.toggle("oculto", !sim); }
function painelForm(nome){
  document.querySelectorAll("#abasForm button").forEach(function(x){ x.classList.toggle("ativo", x.dataset.painel === nome); });
  mostrar($("painel-dados"), nome === "dados");
  mostrar($("painel-historico"), nome === "historico");
  if (nome === "historico") carregarHistForm();
}
/* A diária não vem na lista: ao abrir uma reserva existente ela é buscada no detalhe (só quem tem valores.ver recebe). */
var diariaPronta = false;       // o campo reflete o valor do servidor (ou é reserva nova): só então a diária é enviada ao salvar
function prepararDiaria(r){
  var ver = pode("valores.ver"), editar = pode("valores.editar");
  mostrar($("blocoDiaria"), ver);
  $("fdiaria").value = ""; $("fdiaria").disabled = true; diariaPronta = false;
  atualizarTotalDiaria();
  if (!ver) return;
  if (!r){ diariaPronta = true; $("fdiaria").disabled = !editar; return; }
  $("fdiaria").value = "carregando…";
  api("GET", "/api/reservas/" + r.id).then(function(x){
    if (editando !== r) return;                     // o formulário já foi fechado ou trocado
    if (!x.ok){ $("fdiaria").value = ""; return; }  // falhou: campo vazio e desabilitado, e a diária NÃO é enviada (não apaga o que existe)
    var c = x.dados.diaria_centavos;
    $("fdiaria").value = c == null ? "" : centavosParaReais(c);
    $("fdiaria").disabled = !editar; diariaPronta = true;
    atualizarTotalDiaria(); validarAoVivo();
  }).catch(function(){ if (editando === r) $("fdiaria").value = ""; });
}
function atualizarTotalDiaria(){
  var c = reaisParaCentavos($("fdiaria").value), noites = difDias($("fi").value, $("ff").value), t = $("fdiariaTotal");
  var ok = c != null && c !== undefined && dataReal($("fi").value) && dataReal($("ff").value) && noites >= 1;
  t.textContent = ok ? noites + (noites === 1 ? " diária" : " diárias") + " x R$ " + centavosParaReais(c, true) + " = R$ " + centavosParaReais(c * noites, true) : "";
}
function abrirForm(r, padrao){
  editando = r || null;
  $("fa").innerHTML = UNIDADES.map(function(u){
    return '<option value="' + esc(u) + '"' + (OCUPADAS[u] ? " disabled" : "") + '>' + esc(u) + (OCUPADAS[u] ? " (OCUPADO)" : "") + '</option>';
  }).join("");
  var base = r || padrao || {};
  var hoje = hojeISO();
  $("fa").value = base.a || "101";
  $("fnome").value = base.nome || "";
  $("fn").value = base.n || 2;
  $("fi").value = base.i || hoje;
  $("ff").value = base.f || somaDias(base.i || hoje, 1);
  $("fp").value = base.p || "pendente";
  $("fextras").value = base.extras || "";
  $("fgrupo").value = base.grupo || "";
  $("ftipo").value = base.tipo || "";
  $("fo").value = base.o || "";
  $("dlgTitulo").textContent = r ? "Editar reserva" : "Nova reserva";
  // o que este perfil pode mexer (o servidor confere de novo; aqui é só para não oferecer o que será negado)
  var tudo = pode(r ? "reservas.editar" : "reservas.criar"), pagamento = tudo || (!!r && pode("reservas.editar_pagamento"));
  ["fa","fn","fnome","fi","ff","fgrupo","fextras","ftipo"].forEach(function(id){ $(id).disabled = !tudo; });
  prepararDiaria(r);
  $("fp").disabled = !pagamento; $("fo").disabled = !pagamento;
  mostrar($("btnSalvar"), pagamento);
  mostrar($("btnExcluir"), !!r && pode("reservas.cancelar"));
  mostrar($("abaHistForm"), !!r && (pode("historico.reserva") || pode("historico.completo")));
  mostrar($("blocoCancelar"), false); mostrar($("acoesForm"), true);
  $("fmotivo").value = "";
  painelForm("dados");
  validarAoVivo();
  document.dispatchEvent(new Event("pousada:form-aberto"));   // static/cartao.js reavalia o aviso de cartão
  $("dlg").showModal();
  if (tudo) $("fnome").focus();
}
function fecharForm(){ $("dlg").close(); editando = null; desenhar(); }

function lerForm(){
  return {a: $("fa").value, nome: $("fnome").value.trim(), n: parseInt($("fn").value, 10), i: $("fi").value, f: $("ff").value,
    p: $("fp").value, extras: $("fextras").value.trim(), o: $("fo").value.trim(), grupo: $("fgrupo").value.trim(), tipo: $("ftipo").value};
}
/* O que vai ao servidor: a diária só entra se o campo é editável e já mostra o valor do servidor (senão a ausência a preserva). */
function corpoReserva(){
  var d = lerForm();
  if (pode("valores.editar") && diariaPronta) d.diaria_centavos = reaisParaCentavos($("fdiaria").value);
  return d;
}
function validarAoVivo(){
  var d = lerForm(), av = $("aviso"), msg = "", ok = true;
  if (!d.nome){ msg = "Informe o nome do hóspede."; ok = false; }
  else if (!(d.n >= 1)){ msg = "Informe o número de pessoas."; ok = false; }
  else if (!dataReal(d.i) || !dataReal(d.f)){ msg = "Informe datas válidas."; ok = false; }
  else if (d.f <= d.i){ msg = "A saída deve ser depois da entrada."; ok = false; }
  else if (!$("fdiaria").disabled && reaisParaCentavos($("fdiaria").value) === undefined){
    msg = "Valor da diária inválido (use números e vírgula, ex.: 123,45)."; ok = false;
  }
  else {
    var c = conflitoCom(d.a, d.i, d.f, editando ? editando.id : null);
    if (c){ msg = "Conflito: " + c.a + " já reservada por " + c.nome + " (" + br(c.i) + " a " + br(c.f) + ")."; ok = false; }
  }
  if (ok){ av.className = "aviso ok"; av.textContent = "Unidade disponível nesse período."; }
  else { av.className = "aviso erro"; av.textContent = msg; }
  $("btnSalvar").disabled = !ok;
  return ok;
}
function salvar(ev){
  ev.preventDefault();
  if (!validarAoVivo()) return;
  var d = corpoReserva(), req;
  $("btnSalvar").disabled = true;            // evita duplo clique
  if (editando && !pode("reservas.editar")) d = {p: d.p, o: d.o};      // recepção: só pagamento e observações
  if (editando){ d.versao = editando.versao; req = api("PUT", "/api/reservas/" + editando.id, d); }
  else req = api("POST", "/api/reservas", d);
  req.then(function(r){
    if (r.ok){ aviso("Reserva salva."); fecharForm(); carregar(); }
    else {
      $("aviso").className = "aviso erro"; $("aviso").textContent = r.dados.erro || "Não foi possível salvar.";
      $("btnSalvar").disabled = false;
      if (r.status === 409) api("GET", "/api/reservas").then(function(x){ if (x.ok) reservas = x.dados; });
    }
  }).catch(function(){ $("aviso").className = "aviso erro"; $("aviso").textContent = "Sem conexão com o servidor."; $("btnSalvar").disabled = false; });
}
function pedirCancelamento(){
  mostrar($("blocoCancelar"), true); mostrar($("acoesForm"), false); $("fmotivo").focus();
}
function desistirCancelamento(){ mostrar($("blocoCancelar"), false); mostrar($("acoesForm"), true); }
function confirmarCancelamento(){
  var motivo = $("fmotivo").value.trim();
  if (!motivo){ $("aviso").className = "aviso erro"; $("aviso").textContent = "Informe o motivo do cancelamento."; $("fmotivo").focus(); return; }
  $("btnConfirmarCancelar").disabled = true;
  api("DELETE", "/api/reservas/" + editando.id, {versao: editando.versao, motivo: motivo}).then(function(r){
    $("btnConfirmarCancelar").disabled = false;
    if (r.ok){ aviso("Reserva cancelada."); fecharForm(); carregar(); }
    else { $("aviso").className = "aviso erro"; $("aviso").textContent = r.dados.erro || "Não foi possível cancelar."; }
  }).catch(function(){ $("btnConfirmarCancelar").disabled = false; $("aviso").className = "aviso erro"; $("aviso").textContent = "Sem conexão com o servidor."; });
}

/* ---------- Histórico (aba do formulário e tela do administrador) ---------- */
var ROTULO_ACAO = {criar:"Criou", alterar:"Alterou", cancelar:"Cancelou", reativar:"Reativou", mover:"Moveu", excluir:"Excluiu definitivamente",
  importar:"Importou", desfazer:"Desfez importação", backup:"Backup", login_ok:"Entrou no sistema", login_falha:"Tentativa de login falhou",
  usuario_criado:"Criou usuário", usuario_ativo:"Ativou/desativou usuário", usuario_senha:"Trocou senha", usuario_editado:"Alterou usuário",
  despesa_lancada:"Lançou despesa", despesa_estornada:"Estornou despesa", nota_adicionada:"Adicionou nota", nota_corrigida:"Corrigiu nota",
  nota_ocultada:"Ocultou nota", manutencao_abrir:"Abriu manutenção", manutencao_fechar:"Encerrou manutenção", governanca_correcao:"Desfez o pronto de outra pessoa",
  hospedes_alterados:"Alterou os hóspedes", checkin:"Registrou o check-in", checkin_revertido:"Reverteu o check-in", conta_liberada:"Liberou o apartamento (conta aberta)",
  conta_reaberta:"Desfez a liberação do apartamento", placa_alterada:"Alterou a placa do veículo",
  pagamento_recebido:"Recebeu pagamento", pagamento_estornado:"Estornou pagamento", despesas_transferidas:"Transferiu despesas para outro apartamento",
  despesas_recebidas:"Recebeu despesas transferidas", diaria_zerada:"Zerou a diária", conta_fechada:"Fechou a conta", conta_reaberta_fechamento:"Reabriu a conta fechada"};
var ROTULO_CAMPO = {categoria:"categoria", itens:"itens", situacao:"situação", tipo:"hóspede", diaria:"valor da diária", a:"unidade", i:"entrada", f:"saída", n:"pessoas", p:"pagamento", nome:"nome", status:"situação", estado:"hospedagem", placa:"placa", motivo:"motivo", forma:"forma de pagamento"};
var ORDEM_CAMPO = ["a", "i", "f", "n", "p", "tipo", "diaria", "nome", "status"];    // a ordem em que o histórico conta a mudança
function dataBR(s){ return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s.slice(8) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : s; }
function valorDoHistorico(campo, v){          // datas em dia/mês/ano e pagamento por extenso, como no resto do sistema
  if (campo === "i" || campo === "f") return dataBR(v);
  if (campo === "estado") return {pendente: "check-in pendente", efetuado: "check-in efetuado", conta_aberta: "conta aberta"}[v] || v;
  return campo === "p" ? (PAGAMENTOS[v] || v) : v;
}
function descreverMudanca(antes, depois){
  var chaves = {}, partes = [];
  Object.keys(antes || {}).concat(Object.keys(depois || {})).forEach(function(k){ chaves[k] = true; });
  Object.keys(chaves).sort(function(x, y){ return (ORDEM_CAMPO.indexOf(x) + 1 || 99) - (ORDEM_CAMPO.indexOf(y) + 1 || 99); }).forEach(function(k){
    var rot = ROTULO_CAMPO[k] || k, a = antes ? antes[k] : undefined, d = depois ? depois[k] : undefined;
    if (k === "nome") partes.push("nome alterado");
    else if (k === "tipo") partes.push(rot + ": " + (TIPOS[a] || "não informado") + " → " + (TIPOS[d] || "não informado"));
    else if (a !== undefined && d !== undefined) partes.push(rot + ": " + valorDoHistorico(k, a) + " → " + valorDoHistorico(k, d));
    else partes.push(rot + ": " + valorDoHistorico(k, d !== undefined ? d : a));
  });
  return partes.join("; ");
}
function dataHora(s){ return String(s || "").replace("T", " ").slice(8, 10) + "/" + String(s || "").slice(5, 7) + " " + String(s || "").slice(11, 16); }
function carregarHistForm(){
  var t = $("tabHistForm");
  if (!editando){ t.innerHTML = ""; return; }
  t.innerHTML = '<tbody><tr><td class="suave">Carregando...</td></tr></tbody>';
  api("GET", "/api/reservas/" + editando.id + "/historico").then(function(r){
    if (!r.ok){ t.innerHTML = '<tbody><tr><td>' + esc(r.dados.erro || "Não foi possível carregar.") + '</td></tr></tbody>'; return; }
    var h = '<thead><tr><th>Quando</th><th>Quem</th><th>O quê</th></tr></thead><tbody>';
    r.dados.forEach(function(x){
      h += '<tr><td>' + esc(dataHora(x.em)) + '</td><td>' + esc(x.usuario_login) + '</td><td><b>' + esc(ROTULO_ACAO[x.acao] || x.acao) + '</b> ' +
        esc(descreverMudanca(x.antes, x.depois)) + '</td></tr>';
    });
    t.innerHTML = h + (r.dados.length ? '' : '<tr><td colspan="3" class="suave">Sem registros.</td></tr>') + '</tbody>';
  }).catch(function(){ t.innerHTML = '<tbody><tr><td>Sem conexão com o servidor.</td></tr></tbody>'; });
}
function carregarHistorico(){
  var t = $("tabHistorico");
  api("GET", "/api/historico?limite=200").then(function(r){
    if (!r.ok){ t.innerHTML = '<tbody><tr><td>' + esc(r.dados.erro || "Não foi possível carregar.") + '</td></tr></tbody>'; return; }
    var completo = pode("historico.completo");
    var h = '<thead><tr><th>Quando</th><th>Quem</th><th>O quê</th><th>Item</th>' + (completo ? '<th>Detalhes</th><th>IP</th>' : '') + '</tr></thead><tbody>';
    r.dados.forEach(function(x){
      h += '<tr><td>' + esc(dataHora(x.em)) + '</td><td>' + esc(x.usuario_login) + '</td><td>' + esc(ROTULO_ACAO[x.acao] || x.acao) + '</td><td>' +
        esc(x.entidade) + (x.entidade_id ? ' #' + esc(x.entidade_id) : '') + '</td>' +
        (completo ? '<td>' + esc(descreverMudanca(x.antes, x.depois)) + '</td><td>' + esc(x.ip) + '</td>' : '') + '</tr>';
    });
    t.innerHTML = h + '</tbody>';
  }).catch(function(){ t.innerHTML = '<tbody><tr><td>Sem conexão com o servidor.</td></tr></tbody>'; });
}

/* ---------- Canceladas ---------- */
function carregarCanceladas(){
  var t = $("tabCanceladas");
  api("GET", "/api/reservas?canceladas=1").then(function(r){
    if (!r.ok){ t.innerHTML = '<tbody><tr><td>' + esc(r.dados.erro || "Não foi possível carregar.") + '</td></tr></tbody>'; return; }
    var h = '<thead><tr><th>Hóspede</th><th>Unidade</th><th>Período</th><th>Motivo</th><th>Cancelada por</th><th></th></tr></thead><tbody>';
    r.dados.forEach(function(x){
      h += '<tr><td><button type="button" class="link-reserva" data-abrir="' + esc(x.id) + '" aria-label="Abrir o resumo da reserva de ' + esc(x.nome) + '">' + esc(x.nome) + '</button></td><td>' + esc(x.a) + '</td><td>' + esc(br(x.i)) + ' a ' + esc(br(x.f)) + '</td><td>' + esc(x.motivo_cancelamento) +
        '</td><td>' + esc(x.cancelado_por) + ' em ' + esc(dataHora(x.cancelado_em)) + '</td><td class="acoes">' +
        (pode("reservas.reativar") ? '<button type="button" data-acao="reativar" data-id="' + esc(x.id) + '" data-versao="' + esc(x.versao) + '">Reativar</button>' : '') +
        (pode("reservas.excluir_definitivo") ? '<button type="button" class="perigo" data-acao="excluir" data-id="' + esc(x.id) + '" data-versao="' + esc(x.versao) + '">Excluir definitivamente</button>' : '') +
        '</td></tr>';
    });
    t.innerHTML = h + (r.dados.length ? '' : '<tr><td colspan="6" class="suave">Nenhuma reserva cancelada.</td></tr>') + '</tbody>';
  }).catch(function(){ t.innerHTML = '<tbody><tr><td>Sem conexão com o servidor.</td></tr></tbody>'; });
}
$("tabCanceladas").addEventListener("click", function(ev){
  var ab = ev.target.closest("[data-abrir]");
  if (ab){ abrirReserva({id: +ab.dataset.abrir}); return; }          // o Resumo busca o resto no servidor (reserva cancelada: modo leitura)
  var b = ev.target.closest("button[data-acao]"); if (!b) return;
  var corpo = {versao: +b.dataset.versao};
  if (b.dataset.acao === "excluir"){
    if (!b.dataset.pronto){ b.dataset.pronto = "1"; b.textContent = "Clique de novo para apagar"; b.classList.add("confirmar"); return; }
    api("POST", "/api/reservas/" + b.dataset.id + "/excluir-definitivo", corpo).then(function(r){
      aviso(r.ok ? "Reserva excluída definitivamente." : (r.dados.erro || "Não foi possível excluir.")); carregarCanceladas();
    });
    return;
  }
  b.disabled = true;
  api("POST", "/api/reservas/" + b.dataset.id + "/reativar", corpo).then(function(r){
    aviso(r.ok ? "Reserva reativada." : (r.dados.erro || "Não foi possível reativar."));
    carregarCanceladas(); carregar();
  });
});

function reservaPorId(id){ for (var k = 0; k < reservas.length; k++) if (String(reservas[k].id) === String(id)) return reservas[k]; return null; }

/* ---------- Eventos ---------- */
document.querySelectorAll("nav button[data-aba]").forEach(function(b){
  b.addEventListener("click", function(){
    document.querySelectorAll("nav button[data-aba]").forEach(function(x){ x.classList.toggle("ativo", x === b); });
    document.querySelectorAll(".aba").forEach(function(s){ s.classList.toggle("ativa", s.id === "aba-" + b.dataset.aba); });
    if (telaDesenhada) desenhar();      // o mapa se ajusta à largura agora visível
  });
});
$("btnNova").addEventListener("click", function(){ abrirForm(null, {i: inicioMapa}); });
$("mAnt").addEventListener("click", function(){ inicioMapa = somaDias(inicioMapa, -(+$("mSemanas").value)); desenhar(); });
$("mProx").addEventListener("click", function(){ inicioMapa = somaDias(inicioMapa, +$("mSemanas").value); desenhar(); });
$("mHoje").addEventListener("click", function(){ inicioMapa = hojeISO(); desenhar(); });
$("mData").addEventListener("change", function(){ if (dataReal(this.value)){ inicioMapa = this.value; desenhar(); } });
$("mSemanas").addEventListener("change", desenhar);
var redimensionarTimer = null;
window.addEventListener("resize", function(){ clearTimeout(redimensionarTimer); redimensionarTimer = setTimeout(desenhar, 150); });
$("fAnt").addEventListener("click", function(){ inicioFolha = somaDias(inicioFolha, -7); desenhar(); });
$("fProx").addEventListener("click", function(){ inicioFolha = somaDias(inicioFolha, 7); desenhar(); });
$("fHoje").addEventListener("click", function(){ inicioFolha = segunda(hojeISO()); desenhar(); });
$("busca").addEventListener("input", desenharBusca);
$("mapa").addEventListener("click", function(ev){
  var barra = ev.target.closest(".barra-res");
  if (barra){ var r = reservaPorId(barra.dataset.id); if (r) abrirReserva(r); return; }
  var cel = ev.target.closest(".d[data-apto]");
  if (cel && pode("reservas.criar") && !OCUPADAS[cel.dataset.apto]) abrirForm(null, {a: cel.dataset.apto, i: cel.dataset.dia});
});
$("resultados").addEventListener("click", function(ev){
  var it = ev.target.closest(".item-busca"); if (!it) return;
  var r = reservaPorId(it.dataset.id); if (r) abrirReserva(r);
});
$("btnImportar").addEventListener("click", function(){
  api("POST", "/api/importar").then(function(r){
    aviso(r.ok ? r.dados.importadas + " reservas de exemplo importadas." : (r.dados.erro || "Falha na importação."));
    carregar();
  });
});
["fa","fn","fnome","fi","ff","fdiaria"].forEach(function(id){
  $(id).addEventListener("input", function(){ validarAoVivo(); atualizarTotalDiaria(); });
  $(id).addEventListener("change", function(){ validarAoVivo(); atualizarTotalDiaria(); });
});
$("fi").addEventListener("change", function(){ if (dataReal($("fi").value) && $("ff").value <= $("fi").value) $("ff").value = somaDias($("fi").value, 1); validarAoVivo(); atualizarTotalDiaria(); });
$("form").addEventListener("submit", salvar);
$("btnCancelar").addEventListener("click", fecharForm);
$("btnExcluir").addEventListener("click", pedirCancelamento);
$("btnDesistirCancelar").addEventListener("click", desistirCancelamento);
$("btnConfirmarCancelar").addEventListener("click", confirmarCancelamento);
$("btnFecharHist").addEventListener("click", fecharForm);
document.querySelectorAll("#abasForm button").forEach(function(b){ b.addEventListener("click", function(){ painelForm(b.dataset.painel); }); });
document.querySelector('nav button[data-aba="canceladas"]').addEventListener("click", carregarCanceladas);
document.querySelector('nav button[data-aba="historico"]').addEventListener("click", carregarHistorico);
$("btnBackupAgora").addEventListener("click", function(){
  $("btnBackupAgora").disabled = true;
  api("POST", "/api/backup").then(function(r){
    $("btnBackupAgora").disabled = false;
    aviso(r.ok ? "Backup feito: " + r.dados.arquivo + " (em " + r.dados.pasta + ")" : (r.dados.erro || "Não foi possível fazer o backup."));
  }).catch(function(){ $("btnBackupAgora").disabled = false; aviso("Sem conexão com o servidor."); });
});
$("dlg").addEventListener("cancel", function(){ editando = null; setTimeout(desenhar, 0); });

$("legenda").innerHTML = COR_LEGENDA.map(function(c){
  return '<span><i class="cor-' + c + '"></i>' + esc(PAGAMENTOS[c]) + '</span>';
}).join("");


/* ---------- Camareiras ---------- */
var camSeq = 0;
function dataLonga(s){ return SEM[parse(s).getDay()] + " " + s.slice(8) + "/" + s.slice(5,7) + "/" + s.slice(0,4); }
function iniciarCam(){
  if (!$("cInicio").value){ $("cInicio").value = hojeISO(); $("cFim").value = somaDias(hojeISO(), 6); }
  carregarCam();
}
function carregarCam(){
  var i = $("cInicio").value, f = $("cFim").value;
  if (!dataReal(i) || !dataReal(f) || f < i){
    $("camCab").textContent = ""; $("camLista").innerHTML = '<p class="aviso erro">Informe um período válido (a data final não pode ser antes da inicial).</p>'; return;
  }
  var q = "?inicio=" + encodeURIComponent(i) + "&fim=" + encodeURIComponent(f) +
    ($("cEstadias").checked ? "&estadias=1" : "") + ($("cNomes").checked ? "&nomes=1" : "");
  var minha = ++camSeq;
  api("GET", "/api/camareiras" + q).then(function(r){
    if (minha !== camSeq) return;
    if (!r.ok){ $("camLista").innerHTML = '<p class="aviso erro">' + esc(r.dados.erro || "Não foi possível carregar.") + '</p>'; return; }
    desenharCam(r.dados);
  }).catch(function(){ $("camLista").innerHTML = '<p class="aviso erro">Sem conexão com o servidor.</p>'; });
}
/* Densidade da impressão: quanto mais linhas, mais colunas e letra menor (o CSS usa den-1/2/3). */
var camDensidade = "den-1";
function escolherDensidade(d){
  var linhas = 0;
  d.dias.forEach(function(dia){ linhas += Math.max(1, dia.unidades.length) + 2; });
  return linhas <= 20 ? "den-1" : (linhas <= 45 ? "den-2" : "den-3");
}
function aplicarClasseCam(){
  $("camLista").className = camDensidade + ($("cPagina").checked ? " cam-pagina" : "");
}
function desenharCam(d){
  $("camCab").textContent = "Camareiras - " + dataLonga(d.inicio) + " até " + dataLonga(d.fim) + (d.estadias ? " (com estadias)" : "");
  camDensidade = escolherDensidade(d);
  aplicarClasseCam();
  var h = "";
  d.dias.forEach(function(dia){
    h += '<section class="cam-dia"><h2>' + esc(dataLonga(dia.data)) + '<small>' + esc(dia.total_saidas) + ' saída(s) · ' + esc(dia.total_entradas) + ' entrada(s)</small></h2>';
    if (!dia.unidades.length) h += '<p class="suave">Sem movimento.</p>';
    h += '<div class="cam-un-lista">';
    dia.unidades.forEach(function(u){
      h += '<div class="cam-un' + (u.saida_e_entrada ? " duplo" : "") + '"><div><input type="checkbox" class="feito" aria-label="Feito: ' + esc(u.a) + '"><span class="cam-rotulo-feito">feito</span></div>' +
        '<div class="cam-apto">' + esc(u.a) + '</div><div class="cam-mov">';
      if (u.saida_e_entrada) h += '<div class="cam-alerta">' + (dia.data === hojeISO() ? "SAÍDA + ENTRADA HOJE" : "SAÍDA + ENTRADA NO MESMO DIA") + '</div>';
      [["saida","SAÍDA"],["entrada","ENTRADA"],["estadia","ESTADIA"]].forEach(function(t){
        var m = u[t[0]]; if (!m) return;
        var partes = [];
        if (m.nome) partes.push(esc(m.nome));
        if (m.grupo) partes.push("Grupo: " + esc(m.grupo));
        if (m.extras && m.extras.length) partes.push("Extras: " + m.extras.map(esc).join(", "));
        if (m.obs) partes.push("Obs.: " + esc(m.obs));
        h += '<div class="mov"><span class="tag ' + t[0] + '">' + t[1] + '</span><b>' + esc(m.n) + ' pessoa(s)</b>' +
          (partes.length ? ' <span class="suave">- ' + partes.join(" - ") + '</span>' : '') + '</div>';
      });
      h += '</div></div>';
    });
    h += '</div></section>';
  });
  $("camLista").innerHTML = h;
}
$("cInicio").addEventListener("change", carregarCam);
$("cFim").addEventListener("change", carregarCam);
["cEstadias","cNomes"].forEach(function(id){ $(id).addEventListener("change", carregarCam); });
$("cPagina").addEventListener("change", aplicarClasseCam);
$("cHoje").addEventListener("click", function(){ $("cInicio").value = hojeISO(); $("cFim").value = hojeISO(); carregarCam(); });
$("cAmanha").addEventListener("click", function(){ var a = somaDias(hojeISO(), 1); $("cInicio").value = a; $("cFim").value = a; carregarCam(); });
$("cSemana").addEventListener("click", function(){ $("cInicio").value = hojeISO(); $("cFim").value = somaDias(hojeISO(), 6); carregarCam(); });
$("cImprimir").addEventListener("click", function(){ window.print(); });
document.querySelector('nav button[data-aba="camareiras"]').addEventListener("click", iniciarCam);

/* ---------- Importar lista (Excel) ---------- */
var imp = {arquivo: null, previa: null, linhas: [], lote: null, gravado: false, sha256: ""};
var ROTULO_ST = {ok: "Pronta", aviso: "Aviso", erro: "Erro", ignorada: "Ignorada"};
var desfazerTimer = null;

function impMsg(txt, tipo){ var e = $("impMsg"); e.className = "aviso " + (tipo || ""); e.textContent = txt; }
function nomeAba(t){ return String(t || "").trim().split(/\s+/).slice(-1)[0]; }
function impPrevia(abas){
  if (!imp.arquivo) return;
  var fd = new FormData(); fd.append("arquivo", imp.arquivo);
  if (abas) abas.forEach(function(a){ fd.append("abas", a); });
  if ($("impPassadas").checked) fd.append("incluir_passadas", "1");
  impMsg("Lendo a planilha...", "");
  $("impPrevia").disabled = true;
  enviarArquivo("/api/importar/previa", fd).then(function(r){
    $("impPrevia").disabled = false;
    if (!r.ok){ impMsg(r.dados.erro || "Não foi possível ler o arquivo.", "erro"); return; }
    imp.previa = r.dados; imp.lote = null; imp.gravado = false; imp.sha256 = r.dados.sha256 || "";
    imp.linhas = r.dados.linhas.map(function(l){
      l.st = l.status; l.mt = l.motivo; l.incluir = (l.status === "ok" || l.status === "aviso"); l.editada = false; return l;
    });
    var antes = r.dados.importado_antes;
    if (antes) impMsg("Atenção: este mesmo arquivo já foi importado em " + dataHora(antes.criado) + " por " + antes.usuario +
      " (importação nº " + antes.lote_id + "). Importar de novo não duplica nada. Confira a tabela.", "erro");
    else impMsg("Planilha lida. Confira a tabela e clique em Importar.", "ok");
    $("impDesfazer").style.display = "none";
    desenharImp();
  }).catch(function(){ $("impPrevia").disabled = false; impMsg("Sem conexão com o servidor.", "erro"); });
}
function conflitoLote(apto, l){
  for (var k = 0; k < imp.linhas.length; k++){
    var m = imp.linhas[k];
    if (m !== l && m.incluir && (m.st === "ok" || m.st === "aviso") && m.apto === apto && m.entrada < l.saida && l.entrada < m.saida) return m;
  }
  return null;
}
function livresPara(l){
  var datas = dataReal(l.entrada) && dataReal(l.saida) && l.saida > l.entrada;
  return UNIDADES.filter(function(u){
    if (OCUPADAS[u]) return false;
    if (!datas) return true;
    return !conflitoCom(u, l.entrada, l.saida, null) && !conflitoLote(u, {entrada: l.entrada, saida: l.saida});
  });
}
function reavaliar(l){
  var m = "";
  if (!l.apto || UNIDADES.indexOf(l.apto) < 0 || OCUPADAS[l.apto]) m = "Escolha um apto válido.";
  else if (!dataReal(l.entrada) || !dataReal(l.saida)) m = "Informe datas válidas.";
  else if (l.saida <= l.entrada) m = "A saída deve ser depois da entrada.";
  else {
    var c = conflitoCom(l.apto, l.entrada, l.saida, null);
    if (c) m = "Conflito com reserva já cadastrada de " + c.nome + " (" + br(c.i) + " a " + br(c.f) + ").";
    else { var o = conflitoLote(l.apto, l); if (o) m = "Conflito com a linha " + o.linha + " desta planilha (" + o.hospede + ")."; }
  }
  if (m){ l.st = "erro"; l.mt = m; l.incluir = false; }
  else { l.st = (l.avisos && l.avisos.length) ? "aviso" : "ok"; l.mt = (l.avisos || []).join("; ") || "Corrigida: pronta para importar."; l.incluir = true; }
}
function classeSt(st){ return st === "ignorada" ? "ign" : st; }
function linhaImp(l, k){
  var editavel = l.status === "erro";
  var cls = classeSt(l.st);
  var h = '<tr data-k="' + k + '" class="imp-' + cls + '">';
  h += '<td><input type="checkbox" class="impInc"' + (l.incluir ? " checked" : "") + (l.st === "erro" || l.st === "ignorada" ? " disabled" : "") + ' aria-label="Importar esta linha"></td>';
  h += '<td><span class="sem ' + cls + '"></span> ' + esc(ROTULO_ST[l.st]) + '</td>';
  h += '<td>' + esc(nomeAba(l.aba)) + ' / ' + esc(l.linha) + '</td>';
  h += '<td><b>' + esc(l.hospede) + '</b>' + (l.grupo && l.grupo !== l.hospede ? '<br><span class="suave">Grupo: ' + esc(l.grupo) + '</span>' : '') +
    (l.extras.length ? '<br><span class="suave">+ ' + esc(l.extras.length) + ' acompanhante(s)</span>' : '') + '</td>';
  h += '<td>' + esc(l.n) + '</td>';
  if (editavel){
    var livres = livresPara(l), ops = '<option value="">(escolha)</option>';
    if (l.apto && livres.indexOf(l.apto) < 0) ops += '<option value="' + esc(l.apto) + '" selected>' + esc(l.apto) + ' (ocupado)</option>';
    livres.forEach(function(u){ ops += '<option value="' + esc(u) + '"' + (u === l.apto ? " selected" : "") + '>' + esc(u) + '</option>'; });
    h += '<td><select class="impApto" aria-label="Apto">' + ops + '</select></td>';
    h += '<td><input type="date" class="impI" value="' + esc(l.entrada || "") + '" aria-label="Entrada"></td>';
    h += '<td><input type="date" class="impF" value="' + esc(l.saida || "") + '" aria-label="Saída"></td>';
  } else {
    h += '<td>' + esc(l.apto) + '</td><td>' + esc(l.entrada ? br(l.entrada) : "") + '</td><td>' + esc(l.saida ? br(l.saida) : "") + '</td>';
  }
  h += '<td><span class="pilula ' + esc(l.pagamento) + '" title="' + esc(l.texto_pagamento) + '">' + esc(PAGAMENTOS[l.pagamento] || l.pagamento) + '</span></td>';
  h += '<td>' + esc(l.mt) + '</td></tr>';
  return h;
}
function contarImp(){
  var c = {ok: 0, aviso: 0, erro: 0, ignorada: 0, marcadas: 0};
  imp.linhas.forEach(function(l){ c[l.st]++; if (l.incluir && (l.st === "ok" || l.st === "aviso")) c.marcadas++; });
  return c;
}
function desenharContImp(){
  var c = contarImp(), esp = imp.previa ? imp.previa.pedidos.filter(function(p){ return !p.ja_importado; }).length : 0;
  $("impConts").innerHTML = [["Prontas", c.ok, "ok"], ["Avisos", c.aviso, "aviso"], ["Erros", c.erro, "erro"], ["Ignoradas", c.ignorada, "ign"], ["Lista de espera", esp, ""]].map(function(x){
    return '<span class="cont">' + (x[2] ? '<span class="sem ' + x[2] + '"></span> ' : '') + esc(x[0]) + '<b>' + esc(x[1]) + '</b></span>';
  }).join("");
  var chk = $("impEsperaSalvar");
  $("impGravar").textContent = "Importar " + c.marcadas + " reserva" + (c.marcadas === 1 ? "" : "s");
  $("impGravar").disabled = imp.gravado || (c.marcadas === 0 && !(chk && chk.checked && esp > 0));
}
function desenharImp(){
  if (!imp.previa) return;
  $("impAbas").innerHTML = '<span class="suave">Abas:</span> ' + imp.previa.abas.map(function(a){
    return '<label class="rotulo-inline"><input type="checkbox" class="impAba" data-titulo="' + esc(a.titulo) + '"' + (a.selecionada ? " checked" : "") + '> ' + esc(nomeAba(a.titulo)) + '</label>';
  }).join(" ");
  var ver = $("impVerIgn").checked;
  var h = '<thead><tr><th>Importar</th><th>Situação</th><th>Aba / linha</th><th>Hóspede</th><th>Pessoas</th><th>Apto</th><th>Entrada</th><th>Saída</th><th>Pagamento</th><th>Observação</th></tr></thead><tbody>';
  imp.linhas.forEach(function(l, k){ if (l.st !== "ignorada" || ver) h += linhaImp(l, k); });
  $("impTab").innerHTML = h + '</tbody>';
  var ped = imp.previa.pedidos;
  var he = "";
  if (ped.length){
    he = '<h3 class="sub">Lista de espera (' + esc(ped.length) + ')</h3><label class="rotulo-inline"><input type="checkbox" id="impEsperaSalvar" checked> Guardar estes pedidos na lista de espera (não entram no mapa)</label><div class="espaco-cima">' +
      ped.map(function(p){
        return '<div class="espera-item">' + (p.ja_importado ? '<span class="suave">(já guardado) </span>' : '') + '<b>' + esc(p.nome) + '</b>' + (p.pessoas ? ' - ' + esc(p.pessoas) + ' pessoa(s)' : '') +
          (p.entrada ? ' - ' + esc(br(p.entrada)) + ' a ' + esc(br(p.saida)) : ' - <span class="suave">sem data reconhecida</span>') + '</div>';
      }).join("") + '</div>';
  }
  $("impEspera").innerHTML = he;
  var chk = $("impEsperaSalvar"); if (chk) chk.addEventListener("change", desenharContImp);
  desenharContImp();
}
function substituirLinhaImp(k){
  var tr = $("impTab").querySelector('tr[data-k="' + k + '"]');
  if (tr){ var t = document.createElement("tbody"); t.innerHTML = linhaImp(imp.linhas[k], k); tr.parentNode.replaceChild(t.firstChild, tr); }
  desenharContImp();
}
function gravarImp(){
  var linhas = imp.linhas.filter(function(l){ return l.incluir && (l.st === "ok" || l.st === "aviso"); }).map(function(l){
    return {aba: l.aba, linha: l.linha, a: l.apto, nome: l.hospede, extras: l.extras.join("\n"), n: l.n, i: l.entrada, f: l.saida,
      p: l.pagamento, o: l.texto_pagamento, grupo: l.grupo};
  });
  var chk = $("impEsperaSalvar");
  var pedidos = (chk && chk.checked) ? imp.previa.pedidos.filter(function(p){ return !p.ja_importado; }) : [];
  $("impGravar").disabled = true; impMsg("Importando...", "");
  api("POST", "/api/importar/confirmar", {arquivo: imp.arquivo ? imp.arquivo.name : "", linhas: linhas, pedidos: pedidos, sha256: imp.sha256 || ""}).then(function(r){
    if (r.ok){
      imp.lote = r.dados.lote_id; imp.gravado = true;
      impMsg(r.dados.criadas + " reserva(s) importada(s), " + r.dados.ignoradas + " ignorada(s) (já existiam), " + r.dados.pedidos_criados + " pedido(s) na lista de espera.", "ok");
      $("impDesfazer").style.display = "inline-block"; resetarDesfazer();
      desenharContImp(); carregar();
    } else {
      var det = (r.dados.problemas || []).slice(0, 5).map(function(p){ return (p.aba ? nomeAba(p.aba) + " linha " + p.linha + ": " : "") + p.motivo; }).join(" | ");
      impMsg((r.dados.erro || "Não foi possível importar.") + (det ? " " + det : ""), "erro");
      desenharContImp(); carregar();
    }
  }).catch(function(){ impMsg("Sem conexão com o servidor.", "erro"); desenharContImp(); });
}
function resetarDesfazer(){ var b = $("impDesfazer"); b.textContent = "Desfazer importação"; b.classList.remove("confirmar"); b.dataset.pronto = ""; clearTimeout(desfazerTimer); }
function desfazerImp(){
  var b = $("impDesfazer");
  if (!b.dataset.pronto){ b.dataset.pronto = "1"; b.textContent = "Clique de novo para confirmar"; b.classList.add("confirmar"); desfazerTimer = setTimeout(resetarDesfazer, 4000); return; }
  api("POST", "/api/importar/desfazer/" + imp.lote).then(function(r){
    if (r.ok){
      impMsg(r.dados.removidas + " reserva(s) removida(s) desta importação.", "ok");
      b.style.display = "none"; imp.lote = null; imp.gravado = false; carregar();
      impPrevia(selecionadasImp());
    } else { impMsg(r.dados.erro || "Não foi possível desfazer.", "erro"); resetarDesfazer(); }
  });
}
function selecionadasImp(){
  var r = []; document.querySelectorAll("#impAbas .impAba").forEach(function(c){ if (c.checked) r.push(c.dataset.titulo); });
  return r;
}
$("btnImpLista").addEventListener("click", function(){ $("dlgImp").showModal(); });
$("impFechar").addEventListener("click", function(){ $("dlgImp").close(); carregar(); });
$("impArq").addEventListener("change", function(){
  imp.arquivo = this.files && this.files[0] ? this.files[0] : null;
  $("impPrevia").disabled = !imp.arquivo;
  if (!imp.arquivo) return;
  if (!/\.xlsx$/i.test(imp.arquivo.name)){ impMsg("Só são aceitos arquivos .xlsx (Excel).", "erro"); imp.arquivo = null; $("impPrevia").disabled = true; return; }
  if (imp.arquivo.size > 5 * 1024 * 1024){ impMsg("Arquivo grande demais (máximo 5 MB).", "erro"); imp.arquivo = null; $("impPrevia").disabled = true; return; }
  imp.previa = null;
  impPrevia(null);
});
$("impPrevia").addEventListener("click", function(){
  if (imp.previa){
    var abas = selecionadasImp();
    if (!abas.length){ impMsg("Marque pelo menos uma aba.", "erro"); return; }
    impPrevia(abas);
  } else impPrevia(null);
});
$("impPassadas").addEventListener("change", function(){ if (imp.previa) impPrevia(selecionadasImp()); });
$("impVerIgn").addEventListener("change", desenharImp);
$("impGravar").addEventListener("click", gravarImp);
$("impDesfazer").addEventListener("click", desfazerImp);
$("impTab").addEventListener("change", function(ev){
  var tr = ev.target.closest("tr[data-k]"); if (!tr) return;
  var k = +tr.dataset.k, l = imp.linhas[k], t = ev.target;
  if (t.classList.contains("impInc")){ l.incluir = t.checked; desenharContImp(); return; }
  if (t.classList.contains("impApto")) l.apto = t.value;
  else if (t.classList.contains("impI")) l.entrada = t.value;
  else if (t.classList.contains("impF")) l.saida = t.value;
  else return;
  l.editada = true; reavaliar(l); substituirLinhaImp(k);
});

/* ---------- Usuários (administrador) ---------- */
var PERFIS = [
  ["admin", "Administrador", "Tudo: usuários, backup, importação, histórico completo e exclusão definitiva."],
  ["atendente", "Atendente", "Cria, edita (inclusive arrastando no mapa), cancela e reativa reservas. Vê e informa o valor da diária. Vê canceladas, folha, camareiras e o histórico de cada reserva."],
  ["recepcao", "Recepção", "Vê as reservas (inclusive o valor da diária) e a folha da semana. Altera só pagamento e observações."],
  ["camareira", "Camareira", "Abre direto na Governança (arrumação) e na aba Camareiras, sem nomes, pagamento nem telefone."],
  ["diretoria", "Diretoria", "Só consulta: reservas (inclusive o valor da diária), folha, exportação completa e o resumo do histórico."],
  ["consulta", "Consulta (só ver e imprimir)", "Vê o mapa, a folha da semana e as camareiras, e imprime. Não altera nada, não exporta, não vê valores nem histórico."]
];
var usuarios = [];
var usuModo = "novo", usuAlvo = null;
function rotuloPerfil(p){ for (var k = 0; k < PERFIS.length; k++) if (PERFIS[k][0] === p) return PERFIS[k][1]; return p; }
function descPerfil(p){ for (var k = 0; k < PERFIS.length; k++) if (PERFIS[k][0] === p) return PERFIS[k][2]; return ""; }
$("listaPerfis").innerHTML = PERFIS.map(function(p){ return '<li><b>' + esc(p[1]) + ':</b> ' + esc(p[2]) + '</li>'; }).join("");
$("uPapel").innerHTML = PERFIS.map(function(p){ return '<option value="' + esc(p[0]) + '">' + esc(p[1]) + '</option>'; }).join("");

function gerarSenha(){          // 12 caracteres sem letras parecidas (0/O, 1/l/I), em grupos de 4: fácil de ditar
  var letras = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789", s = "";
  while (s.length < 12){
    var b = new Uint8Array(32); window.crypto.getRandomValues(b);
    for (var k = 0; k < b.length && s.length < 12; k++) if (b[k] < 216) s += letras.charAt(b[k] % letras.length);   // 216 = 4 x 54: sem viés
  }
  return s.slice(0, 4) + "-" + s.slice(4, 8) + "-" + s.slice(8);
}
function carregarUsuarios(){
  var t = $("tabUsuarios");
  api("GET", "/api/usuarios").then(function(r){
    if (!r.ok){ t.innerHTML = '<tbody><tr><td>' + esc(r.dados.erro || "Não foi possível carregar.") + '</td></tr></tbody>'; return; }
    usuarios = r.dados;
    var eu = sessao.usuario ? sessao.usuario.id : null;
    var h = '<thead><tr><th>Login</th><th>Nome</th><th>Perfil</th><th>Situação</th><th>Último acesso</th><th></th></tr></thead><tbody>';
    usuarios.forEach(function(u){
      var minha = u.id === eu;
      h += '<tr' + (u.ativo ? '' : ' class="inativo"') + '><td>' + esc(u.login) + (minha ? ' <span class="suave">(você)</span>' : '') + '</td><td>' + esc(u.nome) +
        '</td><td>' + esc(rotuloPerfil(u.papel)) + '</td><td><span class="sit ' + (u.ativo ? 'sit-ativo' : 'sit-inativo') + '">' + (u.ativo ? 'Ativo' : 'Desativado') + '</span>' +
        (u.trocar_senha ? ' <span class="suave">(senha provisória)</span>' : '') + '</td><td>' + esc(u.ultimo_login ? dataHora(u.ultimo_login) : "nunca entrou") +
        '</td><td class="acoes"><button type="button" data-acao="editar" data-id="' + esc(u.id) + '">Editar</button>' +
        (minha ? '' : '<button type="button" data-acao="senha" data-id="' + esc(u.id) + '">Redefinir senha</button>' +
          '<button type="button" class="' + (u.ativo ? 'perigo' : '') + '" data-acao="ativo" data-id="' + esc(u.id) + '">' + (u.ativo ? 'Desativar' : 'Ativar') + '</button>') +
        '</td></tr>';
    });
    t.innerHTML = h + '</tbody>';
  }).catch(function(){ t.innerHTML = '<tbody><tr><td>Sem conexão com o servidor.</td></tr></tbody>'; });
}
function usuMsg(txt, tipo){ var a = $("uAviso"); a.className = "aviso" + (tipo ? " " + tipo : ""); a.textContent = txt; }
function abrirUsuario(modo, u){
  usuModo = modo; usuAlvo = u || null;
  $("uTitulo").textContent = modo === "novo" ? "Novo usuário" : (modo === "editar" ? "Editar usuário" : "Redefinir senha de " + u.login);
  $("uCampoLogin").classList.toggle("oculto", modo !== "novo");
  $("uCampoNome").classList.toggle("oculto", modo === "senha");
  $("uCampoPapel").classList.toggle("oculto", modo === "senha");
  $("uDica").classList.toggle("oculto", modo === "senha");
  $("uCampoSenha").classList.toggle("oculto", modo === "editar");
  $("uLogin").value = ""; $("uNome").value = u ? u.nome : ""; $("uPapel").value = u ? u.papel : "atendente";
  $("uSenha").value = modo === "editar" ? "" : gerarSenha();
  $("uPapel").disabled = !!(u && sessao.usuario && u.id === sessao.usuario.id);    // ninguém muda o próprio perfil
  $("uSalvar").classList.remove("oculto"); $("uSalvar").disabled = false; usuMsg("", "");
  mostrarDicaPerfil();
  $("dlgUsu").showModal();
}
function mostrarDicaPerfil(){ $("uDica").textContent = descPerfil($("uPapel").value); }
function salvarUsuario(ev){
  ev.preventDefault();
  var p;
  if (usuModo === "novo") p = api("POST", "/api/usuarios", {login: $("uLogin").value.trim(), nome: $("uNome").value, papel: $("uPapel").value, senha: $("uSenha").value});
  else if (usuModo === "editar") p = api("POST", "/api/usuarios/" + usuAlvo.id, {nome: $("uNome").value, papel: $("uPapel").value});
  else p = api("POST", "/api/usuarios/" + usuAlvo.id + "/senha", {senha: $("uSenha").value});
  $("uSalvar").disabled = true;
  p.then(function(r){
    if (!r.ok){ $("uSalvar").disabled = false; usuMsg(r.dados.erro || "Não foi possível salvar.", "erro"); return; }
    if (usuModo === "editar"){ aviso("Usuário atualizado."); $("dlgUsu").close(); carregarUsuarios(); return; }
    // Senha provisória: fica na tela até fechar (não é mostrada de novo depois).
    $("uSalvar").classList.add("oculto");
    usuMsg((usuModo === "novo" ? "Usuário criado. " : "Senha redefinida. ") + "Anote a senha provisória acima e entregue à pessoa: ela não será mostrada de novo.", "ok");
    carregarUsuarios();
  }).catch(function(){ $("uSalvar").disabled = false; usuMsg("Sem conexão com o servidor.", "erro"); });
}
$("uNovo").addEventListener("click", function(){ abrirUsuario("novo", null); });
$("uGerar").addEventListener("click", function(){ $("uSenha").value = gerarSenha(); });
$("uPapel").addEventListener("change", mostrarDicaPerfil);
$("formUsu").addEventListener("submit", salvarUsuario);
$("uFechar").addEventListener("click", function(){ $("dlgUsu").close(); });
$("tabUsuarios").addEventListener("click", function(ev){
  var b = ev.target.closest("button[data-acao]"); if (!b) return;
  var u = null; usuarios.forEach(function(x){ if (String(x.id) === b.dataset.id) u = x; });
  if (!u) return;
  if (b.dataset.acao === "editar") { abrirUsuario("editar", u); return; }
  if (b.dataset.acao === "senha") { abrirUsuario("senha", u); return; }
  if (u.ativo && !b.dataset.pronto){ b.dataset.pronto = "1"; b.textContent = "Clique de novo para desativar"; b.classList.add("confirmar"); return; }
  b.disabled = true;
  api("POST", "/api/usuarios/" + u.id + "/ativo", {ativo: !u.ativo}).then(function(r){
    aviso(r.ok ? (u.ativo ? "Usuário desativado." : "Usuário ativado.") : (r.dados.erro || "Não foi possível alterar."));
    carregarUsuarios();
  });
});
document.querySelector('nav button[data-aba="usuarios"]').addEventListener("click", carregarUsuarios);

$("btnSair").addEventListener("click", function(){
  api("POST", "/api/logout").then(irParaLogin);
});

/* ---------- Início: confere o login e o perfil antes de mostrar qualquer dado ---------- */
function aplicarPermissoes(){
  document.querySelectorAll("[data-cap]").forEach(function(el){
    mostrar(el, el.dataset.cap.split(",").some(pode));
  });
  if (!pode("reservas.ver")) $("cNomes").parentNode.classList.add("oculto");   // camareira nunca vê nomes
}
/* Troca de senha: obrigatória no primeiro acesso (não dá para fechar) ou voluntária (botão "Trocar minha senha"). */
var senhaObrigatoria = false;
$("dlgSenha").addEventListener("cancel", function(ev){ if (senhaObrigatoria) ev.preventDefault(); });
$("formSenha").addEventListener("submit", function(ev){
  ev.preventDefault();
  api("POST", "/api/senha", {atual: $("senhaAtual").value, nova: $("senhaNova").value}).then(function(r){
    if (r.ok){ window.location.reload(); return; }       // a sessão é renovada: recarrega para pegar o token novo
    $("avisoSenha").className = "aviso erro"; $("avisoSenha").textContent = r.dados.erro || "Não foi possível trocar a senha.";
  }).catch(function(){ $("avisoSenha").className = "aviso erro"; $("avisoSenha").textContent = "Sem conexão com o servidor."; });
});
function abrirSenha(obrigatoria){
  senhaObrigatoria = obrigatoria;
  $("senhaAtual").value = ""; $("senhaNova").value = ""; $("avisoSenha").textContent = "";
  $("btnSenhaFechar").classList.toggle("oculto", obrigatoria);
  $("dlgSenha").showModal();
}
function pedirNovaSenha(){ abrirSenha(true); }
$("btnMinhaSenha").addEventListener("click", function(){ abrirSenha(false); });
$("btnSenhaFechar").addEventListener("click", function(){ $("dlgSenha").close(); });
// Só começa depois de TODOS os scripts carregarem (DOMContentLoaded): sem isso, a resposta da sessão podia chegar antes de preferencias.js e quebrar a carga.
document.addEventListener("DOMContentLoaded", function(){ fetch("/api/sessao", {credentials: "same-origin"}).then(function(r){ return r.json(); }).then(function(s){
  if (!s.autenticado){ irParaLogin(); return; }
  sessao.csrf = s.csrf; sessao.usuario = s.usuario; sessao.permissoes = s.permissoes || [];
  $("quem").textContent = s.usuario.nome;
  if (s.usuario.trocar_senha){ pedirNovaSenha(); return; }
  aplicarPermissoes();
  aplicarPreferencias(s.preferencias);        // preferencias.js: esconde menus (só estética) e abre na aba escolhida
  $("mSemanas").value = semanasDasPrefs();
  irParaAbaDeEntrada();
  if (pode("reservas.ver")){
    carregar();
    setInterval(function(){ if (!algumDialogoAberto()) carregar(); }, 8000);
  }
}).catch(function(){ faixa(true); }); });
