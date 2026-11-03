"use strict";
/* Personalizar o sistema: cada pessoa escolhe quais menus ver, em qual aba abrir e o período do mapa.
 * As preferências ficam no servidor (POST /api/preferencias), por usuário, e valem em qualquer computador.
 *
 * É SÓ ESTÉTICA. Esconder um menu (classe "oculto-pref") não dá nem tira permissão: quem não pode continua
 * levando 403 do servidor, e a classe "oculto" (que vem da permissão, em aplicarPermissoes) nunca é mexida aqui.
 * Usa de app.js: $, esc, api, aviso, pode, desenhar, sessao. Carregado depois de app.js. */

var PREF_PADRAO = {menus_ocultos: [], aba_inicial: null, mapa_semanas: null, resumo_recolhido: null};
var SEMANAS_PADRAO = 14;
var prefs = PREF_PADRAO;

/* ---------- aplicar na tela ---------- */
function menusDoPerfil(){          // botões de menu que o perfil pode ver (têm data-menu e não estão ocultos por permissão)
  return Array.prototype.slice.call(document.querySelectorAll("header [data-menu]:not(.oculto)"));
}
function abaVisivel(b){ return !!b && !b.classList.contains("oculto") && !b.classList.contains("oculto-pref"); }
function primeiraAbaVisivel(){
  var abas = document.querySelectorAll("nav button[data-aba]");
  for (var k = 0; k < abas.length; k++) if (abaVisivel(abas[k])) return abas[k];
  return null;
}
function abaDeEntrada(){           // a aba escolhida para abrir, se ainda puder ser vista; senão, a primeira visível
  var b = prefs.aba_inicial ? document.querySelector('nav button[data-aba="' + prefs.aba_inicial + '"]') : null;
  return abaVisivel(b) ? b : primeiraAbaVisivel();
}
function irParaAbaDeEntrada(){ var b = abaDeEntrada(); if (b) b.click(); }
function semanasDasPrefs(){ return String(prefs.mapa_semanas || SEMANAS_PADRAO); }

function aplicarPreferencias(p){
  prefs = {menus_ocultos: (p && p.menus_ocultos) || [], aba_inicial: (p && p.aba_inicial) || null, mapa_semanas: (p && p.mapa_semanas) || null,
    resumo_recolhido: p && typeof p.resumo_recolhido === "boolean" ? p.resumo_recolhido : null};     // faixa do Resumo da conta (resumo_ligar.js)
  document.querySelectorAll("header [data-menu]").forEach(function(el){
    el.classList.toggle("oculto-pref", prefs.menus_ocultos.indexOf(el.dataset.menu) >= 0);
  });
  var ativo = document.querySelector("nav button[data-aba].ativo");
  if (!abaVisivel(ativo)) irParaAbaDeEntrada();           // a aba aberta foi escondida: vai para a inicial
}

/* ---------- o diálogo ---------- */
var CHAVES_ABA = ["mapa", "calendario", "folha", "buscar", "governanca", "camareiras", "canceladas", "historico", "usuarios"];
function ehAba(menu){ return CHAVES_ABA.indexOf(menu) >= 0; }
function prefMsg(txt){ $("prefAviso").className = "aviso" + (txt ? " erro" : ""); $("prefAviso").textContent = txt; }

function desenharListaMenus(){
  $("prefMenus").innerHTML = menusDoPerfil().map(function(b){
    var m = b.dataset.menu, marcado = prefs.menus_ocultos.indexOf(m) < 0;
    return '<label><input type="checkbox" class="prefMenu" data-menu="' + esc(m) + '"' + (marcado ? " checked" : "") + '> ' +
      esc(b.textContent.trim()) + '</label>';
  }).join("");
}
function menusMarcados(){          // ids dos menus que estão marcados (visíveis) na lista
  return Array.prototype.slice.call(document.querySelectorAll("#prefMenus .prefMenu")).filter(function(c){ return c.checked; })
    .map(function(c){ return c.dataset.menu; });
}
function desenharSeletorAba(){     // "Aba ao abrir": só as abas marcadas, mais "Automática"
  var antes = $("prefAba").value || prefs.aba_inicial || "";
  var marcadas = menusMarcados().filter(ehAba);
  var h = '<option value="">Automática (a primeira visível)</option>';
  menusDoPerfil().forEach(function(b){
    if (ehAba(b.dataset.menu) && marcadas.indexOf(b.dataset.menu) >= 0)
      h += '<option value="' + esc(b.dataset.menu) + '">' + esc(b.textContent.trim()) + '</option>';
  });
  $("prefAba").innerHTML = h;
  $("prefAba").value = marcadas.indexOf(antes) >= 0 ? antes : "";
}
function abrirPersonalizar(){
  desenharListaMenus();
  $("prefAba").innerHTML = "";               // esquece a escolha da abertura anterior
  desenharSeletorAba();
  $("prefSemanas").value = semanasDasPrefs();
  $("prefCampoMapa").classList.toggle("oculto", !pode("reservas.ver"));   // sem mapa, o período não faz sentido
  prefMsg("");
  $("dlgPref").showModal();
  var primeiro = document.querySelector("#prefMenus .prefMenu"); if (primeiro) primeiro.focus();
}

/* ---------- salvar ---------- */
function corpoDoDialogo(){
  var marcados = menusMarcados();
  var ocultos = menusDoPerfil().map(function(b){ return b.dataset.menu; }).filter(function(m){ return marcados.indexOf(m) < 0; });
  prefs.menus_ocultos.forEach(function(m){      // menus que este perfil nem enxerga: a escolha antiga é mantida
    var ehDoPerfil = menusDoPerfil().some(function(b){ return b.dataset.menu === m; });
    if (!ehDoPerfil && ocultos.indexOf(m) < 0) ocultos.push(m);
  });
  return {menus_ocultos: ocultos, aba_inicial: $("prefAba").value || null,
          mapa_semanas: pode("reservas.ver") ? +$("prefSemanas").value : prefs.mapa_semanas};
}
function algumaAbaMarcada(){ return menusMarcados().some(ehAba); }
function enviarPreferencias(corpo, msgOk){
  $("prefSalvar").disabled = true;
  return api("POST", "/api/preferencias", corpo).then(function(r){
    $("prefSalvar").disabled = false;
    if (!r.ok){ prefMsg(r.dados.erro || "Não foi possível salvar."); return; }
    aplicarPreferencias(r.dados);
    $("mSemanas").value = semanasDasPrefs(); desenhar();
    $("dlgPref").close();
    aviso(msgOk);
  }).catch(function(){ $("prefSalvar").disabled = false; prefMsg("Sem conexão com o servidor."); });
}
function salvarPreferencias(ev){
  ev.preventDefault();
  if (!algumaAbaMarcada()){ prefMsg("Deixe pelo menos uma aba visível."); return; }
  enviarPreferencias(corpoDoDialogo(), "Preferências salvas.");
}
function restaurarPreferencias(){
  enviarPreferencias({menus_ocultos: [], aba_inicial: null, mapa_semanas: null}, "Menus restaurados ao padrão.");
}

$("btnPersonalizar").addEventListener("click", abrirPersonalizar);
$("formPref").addEventListener("submit", salvarPreferencias);
$("prefRestaurar").addEventListener("click", restaurarPreferencias);
$("prefFechar").addEventListener("click", function(){ $("dlgPref").close(); });
$("prefMenus").addEventListener("change", function(){ prefMsg(""); desenharSeletorAba(); });
