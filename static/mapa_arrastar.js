"use strict";
/* Arrastar no mapa de reservas (mouse e caneta; no toque o toque simples abre a reserva e a rolagem continua normal).
 *   mover   : arrastar a barra para outra linha (unidade) e/ou outro dia (mantém o nº de noites)
 *   esq/dir : arrastar a alça da esquerda (entrada) ou da direita (saída)
 *   criar   : arrastar numa célula vazia da mesma linha, do dia de entrada até o dia de saída
 * Usa as funções e variáveis de app.js (reservas, pode, api, aviso, abrirForm, desenhar, carregar...).
 * O formulário continua sendo a alternativa completa (teclado) para tudo isto. O servidor revalida tudo. */

var LIMIAR_ARRASTE = 5;          // px: abaixo disso é um clique, que abre a reserva como sempre
var gesto = null;                // gesto em andamento (ou null)
var ignorarCliqueAte = 0;        // o clique que o navegador gera ao soltar depois de arrastar é descartado

/* ---------- geometria do mapa (lida do que o desenharMapa gravou) ---------- */
function geometriaMapa(){
  var m = $("mapa"), cab = m.querySelector(".linha.cab .celulas");
  return {d0: m.dataset.inicio, n: +m.dataset.dias, w: +m.dataset.w, esq: cab.getBoundingClientRect().left};
}
function indiceDoDia(x){      // 0..n-1, preso às bordas
  var G = geometriaMapa();
  return Math.max(0, Math.min(G.n - 1, Math.floor((x - G.esq) / G.w)));
}
function linhaSobY(y){
  var linhas = $("mapa").querySelectorAll(".linha[data-apto]");
  for (var k = 0; k < linhas.length; k++){
    var r = linhas[k].getBoundingClientRect();
    if (y >= r.top && y < r.bottom) return linhas[k];
  }
  return null;
}
function dentroDoMapa(ev){
  var r = document.querySelector(".mapa-wrap").getBoundingClientRect();
  return ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom;
}

/* ---------- o que o gesto produz ---------- */
/* Novo {a, i, f} para a posição do ponteiro (ou null se não há destino). */
function calcularAlvo(g, ev){
  var G = geometriaMapa(), delta = indiceDoDia(ev.clientX) - g.idx0, r = g.r;
  if (g.modo === "criar"){
    var d1 = somaDias(G.d0, g.idx0), d2 = somaDias(G.d0, indiceDoDia(ev.clientX));
    return d1 === d2 ? null : {a: g.apto, i: d1 < d2 ? d1 : d2, f: d1 < d2 ? d2 : d1};
  }
  if (g.modo === "esq") return {a: r.a, i: minimoISO(somaDias(r.i, delta), somaDias(r.f, -1)), f: r.f};
  if (g.modo === "dir") return {a: r.a, i: r.i, f: maximoISO(somaDias(r.f, delta), somaDias(r.i, 1))};
  var linha = linhaSobY(ev.clientY);
  return linha ? {a: linha.dataset.apto, i: somaDias(r.i, delta), f: somaDias(r.f, delta)} : null;
}
function minimoISO(a, b){ return a < b ? a : b; }
function maximoISO(a, b){ return a > b ? a : b; }
function descreverAlvo(a){ return a.a + " · " + br(a.i) + " → " + br(a.f); }

/* Motivo de não poder (texto) ou "" se o destino está livre. A palavra final é a do servidor. */
function motivoInvalido(g, alvo){
  if (OCUPADAS[alvo.a]) return "A unidade " + alvo.a + " está ocupada e não aceita reservas.";
  if (difDias(alvo.i, alvo.f) > 365) return "Estadia longa demais (máximo 365 noites).";
  var c = conflitoCom(alvo.a, alvo.i, alvo.f, g.r ? g.r.id : null);
  return c ? "Conflito: " + c.a + " já reservada por " + c.nome + " (" + br(c.i) + " a " + br(c.f) + ")." : "";
}
function semMudanca(g, alvo){
  return g.modo !== "criar" && alvo.a === g.r.a && alvo.i === g.r.i && alvo.f === g.r.f;
}

/* ---------- prévia (barra fantasma) ---------- */
function mostrarPrevia(g, alvo){
  if (!g.fantasma){
    g.fantasma = document.createElement("div");
    g.fantasma.className = "fantasma";
    g.fantasma.setAttribute("aria-label", "Prévia da reserva");
    g.rotulo = document.createElement("span");          // texto curto numa etiqueta acima da barra (a barra pode ser estreita)
    g.rotulo.className = "rotulo-fantasma";
    g.fantasma.appendChild(g.rotulo);
  }
  var linha = alvo && $("mapa").querySelector('.linha[data-apto="' + CSS.escape(alvo.a) + '"] .celulas');
  var G = geometriaMapa(), pos = alvo && posicaoBarra(alvo.i, alvo.f, G.d0, G.n, G.w);
  if (!linha || pos.larg <= 0){ g.fantasma.remove(); return; }
  linha.appendChild(g.fantasma);
  g.fantasma.style.left = pos.esq + "px"; g.fantasma.style.width = pos.larg + "px";
  g.rotulo.textContent = descreverAlvo(alvo);
  g.fantasma.classList.toggle("ruim", !!g.motivo);
  g.fantasma.title = g.motivo || "Solte para confirmar";
}
function atualizarPrevia(ev){
  var g = gesto;
  g.alvo = calcularAlvo(g, ev);
  g.motivo = g.alvo ? motivoInvalido(g, g.alvo) : "";
  mostrarPrevia(g, g.alvo);
}

/* ---------- ciclo do gesto ---------- */
function modoDoGesto(ev){
  var barra = ev.target.closest(".barra-res");
  if (barra){
    if (!pode("reservas.editar")) return null;
    var r = reservaPorId(barra.dataset.id), alca = ev.target.closest(".alca");
    if (!r) return null;
    return {modo: alca ? (alca.dataset.lado === "e" ? "esq" : "dir") : "mover", r: r, barra: barra};
  }
  var cel = ev.target.closest(".d[data-apto]");
  if (cel && pode("reservas.criar") && !OCUPADAS[cel.dataset.apto]) return {modo: "criar", apto: cel.dataset.apto};
  return null;
}
function iniciarGesto(ev){
  if (gesto || ev.button !== 0 || ev.pointerType === "touch") return;   // toque: só clique e rolagem
  var g = modoDoGesto(ev);
  if (!g) return;
  g.pid = ev.pointerId; g.x0 = ev.clientX; g.y0 = ev.clientY; g.idx0 = indiceDoDia(ev.clientX); g.ativo = false;
  gesto = g;
  document.addEventListener("pointermove", aoMover);
  document.addEventListener("pointerup", aoSoltar);
  document.addEventListener("pointercancel", cancelarGesto);
  document.addEventListener("keydown", aoTeclar);
}
function ativarGesto(ev){
  var g = gesto, m = $("mapa");
  g.ativo = true; arrastando = true;
  m.classList.add("gesto", g.modo === "criar" ? "gesto-criar" : (g.modo === "mover" ? "gesto" : "gesto-alca"));
  if (g.barra) g.barra.classList.add("em-arraste");
  try { m.setPointerCapture(g.pid); } catch (e) { /* sem captura: os eventos seguem no document */ }
  if (window.getSelection) window.getSelection().removeAllRanges();
}
function aoMover(ev){
  var g = gesto;
  if (!g || g.salvando || ev.pointerId !== g.pid) return;
  if (!g.ativo){
    var passou = g.modo === "criar" ? indiceDoDia(ev.clientX) !== g.idx0 : Math.hypot(ev.clientX - g.x0, ev.clientY - g.y0) >= LIMIAR_ARRASTE;
    if (!passou) return;
    ativarGesto(ev);
  }
  atualizarPrevia(ev);
}
function suprimirCliqueSeguinte(){ ignorarCliqueAte = Date.now() + 150; }
function encerrarGesto(){
  var g = gesto, m = $("mapa");
  document.removeEventListener("pointermove", aoMover);
  document.removeEventListener("pointerup", aoSoltar);
  document.removeEventListener("pointercancel", cancelarGesto);
  document.removeEventListener("keydown", aoTeclar);
  if (g){
    if (g.fantasma) g.fantasma.remove();
    if (g.barra) g.barra.classList.remove("em-arraste");
    try { m.releasePointerCapture(g.pid); } catch (e) { /* já liberado */ }
  }
  m.classList.remove("gesto", "gesto-criar", "gesto-alca");
  gesto = null; arrastando = false;
  if (redesenhoPendente){ redesenhoPendente = false; desenhar(); }     // o polling esperou até aqui
}
function cancelarGesto(){
  if (!gesto || gesto.salvando) return;
  var ativo = gesto.ativo;
  encerrarGesto();
  if (ativo){      // o botão ainda pode estar apertado: o clique de quando soltar não deve abrir a reserva
    document.addEventListener("pointerup", suprimirCliqueSeguinte, {once: true});
  }
}
function aoTeclar(ev){
  if (ev.key === "Escape" && gesto && !gesto.salvando){ ev.preventDefault(); cancelarGesto(); }
}
function aoSoltar(ev){
  var g = gesto;
  if (!g || g.salvando || ev.pointerId !== g.pid) return;
  if (!g.ativo){ encerrarGesto(); return; }                 // foi só um clique: o clique normal faz o resto
  suprimirCliqueSeguinte();
  atualizarPrevia(ev);
  var alvo = g.alvo;
  if (!dentroDoMapa(ev) || !alvo || semMudanca(g, alvo)){ encerrarGesto(); return; }   // fora do mapa ou sem efeito: cancela
  if (g.motivo){ aviso(g.motivo); encerrarGesto(); return; }
  if (g.modo === "criar"){ encerrarGesto(); abrirForm(null, alvo); return; }
  enviarMovimento(g, alvo);
}
function enviarMovimento(g, alvo){
  g.salvando = true;                                         // a prévia fica até o servidor responder
  g.fantasma.classList.add("salvando");
  api("POST", "/api/reservas/" + g.r.id + "/mover", {versao: g.r.versao, a: alvo.a, i: alvo.i, f: alvo.f}).then(function(r){
    aviso(r.ok ? "Reserva movida para " + descreverAlvo(alvo) : (r.dados.erro || "Não foi possível mover a reserva."));
    return carregar();                                       // desenha o resultado real (ou desfaz a prévia)
  }).catch(function(){ aviso("Sem conexão com o servidor."); }).then(encerrarGesto);
}

/* ---------- ligação com o mapa ---------- */
$("mapa").addEventListener("pointerdown", iniciarGesto);
$("mapa").addEventListener("click", function(ev){
  if (Date.now() < ignorarCliqueAte){ ignorarCliqueAte = 0; ev.stopImmediatePropagation(); ev.preventDefault(); }
}, true);
