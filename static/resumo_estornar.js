"use strict";
/* Resumo da conta, etapa 3B: Estornar o selecionado (sempre com motivo) e Transferir para outro apartamento (com busca do destino).
 * Estorno de consumo reaproveita POST /api/despesas/<id>/estorno; de pagamento, POST /api/pagamentos/<id>/estorno; a Diária informada
 * é "zerada" (POST /diaria/zerar), com o mesmo motivo. Transferir usa POST /transferir (uma transação no servidor). Só createElement/textContent. */

function rcMarcados(){ return rcItensDaConta().filter(function(i){ return rc.marcados[i.id]; }); }
/* Painel que exige motivo (texto limpo, sem número de cartão). aoConfirmar(motivo, painel, botao) faz o envio. */
function rcPedirMotivo(titulo, origem, paragrafos, nomeOk, cls, aoConfirmar, destino){
  var campo;
  var tit = rcAbrirPainel(titulo, function(p){
    paragrafos.forEach(function(t){ p.appendChild(ntEl("p", "suave", t)); });
    campo = ntCampoTexto("Motivo (obrigatório)", "", 140, 1); p.appendChild(campo.caixa);
    var bt = rcBotoesPainel(function(){
      var v = rcMotivoConferir(campo.campo.value, typeof ctContemNumeroCartao === "function" ? ctContemNumeroCartao : null);
      if (v.erro){ rcAvisoPainel(p, v.erro); campo.campo.focus(); return; }
      aoConfirmar(v.motivo, p, bt.ok);
    }, nomeOk, cls);
    p.appendChild(bt.caixa);
  }, origem, destino || "rcPainelItens");
  tit.focus();
}
function rcDescItens(itens){
  return itens.map(function(i){ return RC_TIPO_ITEM[i.tipo] + ": " + i.descricao + " (" + dsFormatarReais(i.centavos) + ")"; }).join("; ");
}

/* ---------- Estornar ---------- */
var RC_ORDEM_ESTORNO = {credito: 0, consumo: 1, diaria: 2};      // pagamentos primeiro: o total da conta não pode ficar abaixo do que foi pago
function rcRequisicaoEstorno(i, motivo){
  var id = i.id.slice(1);
  if (i.tipo === "consumo") return ["POST", "/api/despesas/" + id + "/estorno", {motivo: motivo}];
  if (i.tipo === "credito") return ["POST", "/api/pagamentos/" + id + "/estorno", {motivo: motivo}];
  return ["POST", rcUrl("diaria/zerar"), {versao: rc.det.versao, motivo: motivo, chave: dsNovaChave()}];
}
function rcExecutarEstornos(itens, motivo, p, bt){
  var feitos = 0;
  bt.disabled = true;
  function passo(k){
    if (k >= itens.length) return Promise.resolve();
    var q = rcRequisicaoEstorno(itens[k], motivo);
    return api(q[0], q[1], q[2]).then(function(r){ if (!r.ok) throw r; feitos++; return passo(k + 1); });
  }
  passo(0).then(function(){
    rcFecharPainel(false); aviso("Estornado: " + rcPlural(feitos, "item", "itens") + "."); carregar(); rcAtualizar(true);
  }).catch(function(r){
    bt.disabled = false;
    var m = r && r.dados ? rcMensagemErro(r.status, r.dados.erro) : "Sem conexão com o servidor. Confira a conta antes de tentar de novo.";
    if (feitos){ rcFecharPainel(false); aviso("Estornados " + feitos + " antes do erro. " + m); carregar(); rcAtualizar(true); return; }
    rcAvisoPainel(p, m); bt.focus();
  });
}
function rcEstornar(){
  var p = rcPerm(), itens = rcMarcados().sort(function(a, b){ return RC_ORDEM_ESTORNO[a.tipo] - RC_ORDEM_ESTORNO[b.tipo]; });
  if (!itens.length){ aviso("Selecione o que deseja estornar."); return; }
  var nao = itens.some(function(i){ return i.tipo === "credito" ? !p.pagEstornar : i.tipo === "diaria" ? !(p.desEstornar && p.valoresEditar) : !p.desEstornar; });
  if (nao){ aviso("Seu perfil não pode estornar um dos itens selecionados."); return; }
  var tem = itens.some(function(i){ return i.tipo === "diaria"; });
  rcPedirMotivo("Estornar o selecionado", "estornar", ["Serão estornados: " + rcDescItens(itens) + ".",
    "O estorno é uma linha negativa com o motivo; nada é apagado." + (tem ? " A diária informada fica zerada (para voltar, use Alterar estadia)." : "")],
    "Confirmar estorno", "perigo", function(motivo, painel, bt){ rcExecutarEstornos(itens, motivo, painel, bt); });
}

/* ---------- Transferir para outro apartamento ---------- */
function rcDesenharDestinos(ul, itens, escolha, bt){
  ul.textContent = "";
  if (!itens.length) ul.appendChild(ntEl("li", "suave", "Nenhuma hospedagem em andamento encontrada."));
  itens.forEach(function(d){
    var li = ntEl("li", "rc-dest"), lab = ntEl("label", "rc-dest-rot"), rd = ntEl("input");
    rd.type = "radio"; rd.name = "rcDestino"; rd.value = d.id;
    rd.addEventListener("change", function(){ escolha.id = d.id; escolha.apto = d.a; bt.disabled = false; });
    lab.appendChild(rd); lab.appendChild(ntEl("span", "", "Apto " + d.a + " · " + d.nome + " · " + rcDataBR(d.i) + " a " + rcDataBR(d.f) + (d.liberado ? " · liberado" : "")));
    li.appendChild(lab); ul.appendChild(li);
  });
}
function rcTransferir(){
  var itens = rcMarcados();
  if (!itens.length){ aviso("Selecione o que deseja transferir."); return; }
  if (itens.some(function(i){ return i.tipo === "credito"; })){ aviso("Pagamentos não são transferidos: estorne o pagamento, se for o caso."); return; }
  var chave = dsNovaChave(), escolha = {id: null, apto: ""};
  var tit = rcAbrirPainel("Transferir para outro apartamento", function(p){
    p.appendChild(ntEl("p", "suave", "Será transferido: " + rcDescItens(itens) + ". Fica um estorno na origem e um lançamento igual no destino, ligados e com registro."));
    var c = ntEl("div", "campo"), lab = ntEl("label", null, "Buscar por nome do hóspede ou número do quarto"), q = ntEl("input"), ul = ntEl("ul", "rc-dests");
    q.id = "rcDestBusca"; lab.htmlFor = q.id; q.maxLength = 60; q.autocomplete = "off"; ul.setAttribute("aria-label", "Hospedagens de destino");
    var buscar = ntBotao("Buscar", "rc-dest-buscar");
    c.appendChild(lab); c.appendChild(q); c.appendChild(buscar); p.appendChild(c); p.appendChild(ul);
    var bt = rcBotoesPainel(function(){
      rcEnviar("POST", rcUrl("transferir"), {destino_id: escolha.id, itens: itens.map(function(i){ return i.id; }), chave: chave, conta_versao: rc.conta.versao},
        "Transferido para o apartamento " + escolha.apto + ".", p, bt.ok);
    }, "Transferir", "primario");
    bt.ok.disabled = true; p.appendChild(bt.caixa);
    function procurar(){
      escolha.id = null; bt.ok.disabled = true;
      api("GET", rcUrl("destinos") + "?q=" + encodeURIComponent(q.value.trim())).then(function(r){
        if (!r.ok){ rcAvisoPainel(p, rcMensagemErro(r.status, r.dados.erro)); return; }
        rcDesenharDestinos(ul, r.dados.itens, escolha, bt.ok);
      }).catch(function(){ rcAvisoPainel(p, "Sem conexão com o servidor."); });
    }
    buscar.addEventListener("click", procurar);
    q.addEventListener("keydown", function(ev){ if (ev.key === "Enter"){ ev.preventDefault(); procurar(); } });
    procurar();
  }, "transferir", "rcPainelItens");
  tit.focus();
}
