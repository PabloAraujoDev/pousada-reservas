"use strict";
/* Tela de login: pega o token CSRF em /api/sessao e envia login e senha em JSON. */
(function(){
  var csrf = "";
  var aviso = document.getElementById("aviso");
  var botao = document.getElementById("btnEntrar");

  function mostrar(texto, tipo){ aviso.className = "aviso " + (tipo || ""); aviso.textContent = texto; }

  function iniciar(){
    return fetch("/api/sessao", {credentials: "same-origin"}).then(function(r){ return r.json(); }).then(function(s){
      csrf = s.csrf;
      if (s.autenticado){ window.location.replace("/"); return; }
      if (!s.existe_usuario){
        mostrar("Ainda não há nenhum usuário. No computador da pousada, execute: python app.py criar-admin", "erro");
        botao.disabled = true;
      }
    }).catch(function(){ mostrar("Sem conexão com o servidor.", "erro"); });
  }

  document.getElementById("formLogin").addEventListener("submit", function(ev){
    ev.preventDefault();
    botao.disabled = true; mostrar("Entrando...", "");
    fetch("/api/login", {
      method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify({login: document.getElementById("login").value, senha: document.getElementById("senha").value})
    }).then(function(r){
      return r.json().catch(function(){ return {}; }).then(function(j){ return {ok: r.ok, status: r.status, dados: j}; });
    }).then(function(r){
      if (r.ok){ window.location.replace("/"); return; }
      mostrar(r.dados.erro || "Não foi possível entrar.", "erro");
      document.getElementById("senha").value = "";
      if (r.status === 403) return iniciar().then(function(){ botao.disabled = false; });
      botao.disabled = false;
    }).catch(function(){ mostrar("Sem conexão com o servidor.", "erro"); botao.disabled = false; });
  });

  iniciar();
})();
