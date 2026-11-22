"use strict";
/* Importação: parte PURA (sem DOM, sem rede; testada em node) das seções "Atualizações" e "Cancelamentos" da prévia.
 * O servidor decide tudo e revalida ao confirmar; aqui só se monta o HTML (todo texto vindo da planilha passa por icEsc)
 * e o corpo do pedido com o que o administrador deixou marcado. */

var IC_CONF = {alta: "Alta confiança", media: "Média (conferir)", sumiu: "Sumiu da planilha"};

function icEsc(s){
  return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; });
}
function icBr(iso){ return iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) : ""; }
function icMarcadas(canc){
  var m = {};
  ((canc && canc.propostas) || []).forEach(function(p){ if (p.marcada && !p.bloqueio) m[p.id] = true; });
  return m;
}
/* A linha nova só entra se todos os cancelamentos de que ela depende estiverem marcados. */
function icDepsOk(l, canc){
  var m = icMarcadas(canc), d = l.depende_de || [];
  for (var k = 0; k < d.length; k++) if (!m[d[k]]) return false;
  return true;
}
function icDifHtml(difs){
  return (difs || []).map(function(d){
    return '<div class="imp-dif"><b>' + icEsc(d.rotulo) + ':</b> <span class="suave">' + icEsc(d.antes || "(vazio)") + '</span> &rarr; ' + icEsc(d.depois || "(vazio)") + '</div>';
  }).join("");
}
function icCorpo(linhas, canc, arquivo, pedidos, sha256){
  var m = icMarcadas(canc), ok = function(l){ return l.incluir && icDepsOk(l, canc); };
  var dados = function(l){
    return {aba: l.aba, linha: l.linha, nome: l.hospede, extras: l.extras.join("\n"), n: l.n, i: l.entrada, f: l.saida,
      p: l.pagamento, o: l.texto_pagamento, grupo: l.grupo};
  };
  var novas = linhas.filter(function(l){ return ok(l) && (l.st === "ok" || l.st === "aviso"); }).map(function(l){
    var d = dados(l); d.a = l.apto; return d;
  });
  var atual = linhas.filter(function(l){ return ok(l) && l.st === "atualizacao"; }).map(function(l){
    var d = dados(l); d.id = l.atualizacao.id; d.versao = l.atualizacao.versao; d.selo = l.atualizacao.selo; d.selo_em = l.atualizacao.selo_em; return d;
  });
  var cancs = ((canc && canc.propostas) || []).filter(function(p){ return m[p.id]; }).map(function(p){
    return {id: p.id, versao: p.versao, origem: p.origem, aba: p.aba, linha: p.linha, selo: p.selo, selo_em: p.selo_em};
  });
  return {arquivo: arquivo || "", linhas: novas, pedidos: pedidos, sha256: sha256 || "", atualizacoes: atual, cancelamentos: cancs};
}
function icRotuloBotao(n, a, c){
  var p = ["Importar " + n + " reserva" + (n === 1 ? "" : "s")];
  if (a) p.push("atualizar " + a);
  if (c) p.push("cancelar " + c);
  return p.length === 1 ? p[0] : p[0] + ", " + p.slice(1).join(" e ");
}
function icHtml(canc){
  if (!canc) return "";
  var ps = canc.propostas || [], ne = canc.nao_encontradas || [], ni = canc.nao_identificadas || [];
  if (!ps.length && !ne.length && !ni.length) return "";
  var h = '<h3 class="sub">Cancelamentos (' + icEsc(ps.length) + ' no sistema)</h3>';
  h += '<p class="suave">Nada é cancelado sem a sua marca. Alta confiança e "sumiu da planilha" vêm marcadas; as de média confiança, não. Reservas com check-in ou conta com lançamentos ficam bloqueadas.</p>';
  (canc.aviso_massa || []).forEach(function(m){
    h += '<p class="aviso erro" role="alert">Atenção: ' + icEsc(m.sumiram) + ' de ' + icEsc(m.total) + ' reservas de ' + icEsc(m.mes.slice(5, 7) + '/' + m.mes.slice(0, 4)) +
      ' não constam mais na planilha. Parece planilha incompleta ou errada, por isso essas caixas vêm desmarcadas. Confira antes de marcar.</p>';
  });
  if (canc.truncado) h += '<p class="aviso erro" role="alert">A seção CANCELAMENTOS tem linhas demais: só as primeiras 500 foram lidas. Divida a planilha ou importe de novo depois.</p>';
  if (ps.length){
    h += '<div class="tabela-wrap"><table id="impCancTab"><thead><tr><th>Cancelar</th><th>Confiança</th><th>Reserva no sistema</th><th>Linha da planilha</th></tr></thead><tbody>';
    ps.forEach(function(p){
      h += '<tr class="' + (p.bloqueio ? "imp-erro" : "") + '"><td><input type="checkbox" class="impCancChk" data-id="' + icEsc(p.id) + '"' +
        (p.marcada && !p.bloqueio ? " checked" : "") + (p.bloqueio ? " disabled" : "") + ' aria-label="Cancelar a reserva de ' + icEsc(p.nome) + ', ' + icEsc(p.apto) + ', ' + icEsc(icBr(p.entrada)) + ' a ' + icEsc(icBr(p.saida)) + '"></td>' +
        '<td>' + icEsc(IC_CONF[p.confianca] || p.confianca) + '</td>' +
        '<td><b>' + icEsc(p.nome) + '</b><br>' + icEsc(p.apto) + ' &middot; ' + icEsc(icBr(p.entrada)) + ' a ' + icEsc(icBr(p.saida)) + '</td>' +
        '<td>' + (p.linha ? icEsc(p.aba.trim().split(/\s+/).slice(-1)[0]) + ' / ' + icEsc(p.linha) + '<br><span class="suave">' + icEsc(p.texto) + '</span>'
          : '<span class="suave">Não consta mais na planilha</span>') +
        '<br><span class="suave">' + icEsc(p.bloqueio ? "Bloqueada: " + p.bloqueio : p.motivo) + '</span></td></tr>';
    });
    h += '</tbody></table></div>';
  }
  if (ni.length) h += '<h4 class="sub">Linhas não identificadas (' + icEsc(ni.length) + '): só para conferir, nada é cancelado</h4>' + ni.map(function(x){
    return '<div class="espera-item"><span class="suave">linha ' + icEsc(x.linha) + ':</span> ' + icEsc(x.texto) + ' <span class="suave">(' + icEsc(x.motivo) + ')</span></div>';
  }).join("");
  if (ne.length) h += '<h4 class="sub">Não encontradas no sistema (' + icEsc(ne.length) + '): só para conferir</h4>' + ne.map(function(x){
    return '<div class="espera-item"><span class="suave">linha ' + icEsc(x.linha) + ':</span> ' + icEsc(x.unidade) + ' - ' + icEsc(x.hospede) +
      (x.entrada ? ' (' + icEsc(icBr(x.entrada)) + ' a ' + icEsc(icBr(x.saida)) + ')' : '') + '</div>';
  }).join("");
  return h;
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {icEsc: icEsc, icMarcadas: icMarcadas, icDepsOk: icDepsOk, icCorpo: icCorpo, icHtml: icHtml, icDifHtml: icDifHtml,
    icRotuloBotao: icRotuloBotao};
}
