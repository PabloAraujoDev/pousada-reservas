"use strict";
/* Notas (anotações com autor e data): lógica pura, testada em node (tests/js/notas_logica.js).
 * Aqui não há DOM nem rede. O texto das notas nunca é montado em HTML: quem desenha usa textContent (notas_painel.js). */

var NT_MAX = 300, NT_MOTIVO_MIN = 3, NT_MOTIVO_MAX = 140;

/* "2026-10-29 09:05:00" -> "29/10/2026 09:05" */
function ntDataHora(em){
  var m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(String(em || ""));
  return m ? m[3] + "/" + m[2] + "/" + m[1] + " " + m[4] + ":" + m[5] : String(em || "");
}
/* "Adicionado por X em dd/mm/aaaa hh:mm · Modificado por Y em ..." (a segunda parte só existe se a nota foi corrigida). */
function ntMeta(n){
  var t = "Adicionado por " + n.por + " em " + ntDataHora(n.em);
  if (n.modificado_por) t += " · Modificado por " + n.modificado_por + " em " + ntDataHora(n.modificado_em);
  return t;
}
/* Abas do painel de observações. p = {reserva: há reserva, gov: pode ver a arrumação, apto: pode ler as notas do apartamento}. */
function ntAbas(p){
  var a = [];
  if (p.reserva) a.push({id: "reserva", rotulo: "Reserva"});
  if (p.gov) a.push({id: "arrumacao", rotulo: "Arrumação"});
  if (p.apto) a.push({id: "apartamento", rotulo: "Apartamento"});
  return a;
}
/* Linhas da aba Arrumação (g = item de /api/governanca ou null). Só leitura: quem escreve é a tela da Governança. */
function ntTextoArrumacao(g){
  if (!g) return ["Sem informações da arrumação."];
  var t = [];
  if (g.obs) t.push("Observação: " + g.obs);
  if (g.manutencao_motivo) t.push("Manutenção: " + g.manutencao_motivo);
  if (!t.length) t.push("Nenhuma observação da arrumação.");
  if (g.atualizado_em) t.push("Última atualização às " + g.atualizado_em + (g.atualizado_por ? " por " + g.atualizado_por : "") + ".");
  return t;
}
/* Confere o texto antes de enviar. Devolve {texto} ou {erro}. (O servidor confere tudo de novo.) */
function ntConferirTexto(v){
  var t = String(v == null ? "" : v).trim();
  if (!t) return {erro: "Escreva a nota."};
  if (t.length > NT_MAX) return {erro: "Nota grande demais (máximo " + NT_MAX + " caracteres)."};
  return {texto: t};
}
function ntConferirMotivo(v){
  var t = String(v == null ? "" : v).trim();
  if (t.length < NT_MOTIVO_MIN) return {erro: "Explique o motivo (pelo menos " + NT_MOTIVO_MIN + " letras)."};
  if (t.length > NT_MOTIVO_MAX) return {erro: "Motivo grande demais (máximo " + NT_MOTIVO_MAX + " caracteres)."};
  return {motivo: t};
}
function ntContador(v){ return String(v || "").length + "/" + NT_MAX; }
/* Mensagem para o balcão a partir do status HTTP e do texto do servidor (409 = outra pessoa mexeu: recarregar). */
function ntMensagemErro(status, texto){
  if (status === 403) return texto || "Seu perfil não pode alterar notas.";
  if (status === 404) return "Esta nota ou reserva não foi encontrada. Feche e abra de novo.";
  return texto || "Não foi possível concluir. Tente de novo.";
}
function ntNovaChave(){
  var c = typeof crypto !== "undefined" ? crypto : null;
  if (c && c.randomUUID) return c.randomUUID();
  var b = new Uint8Array(16);
  if (c && c.getRandomValues) c.getRandomValues(b); else for (var i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  return Array.prototype.map.call(b, function(x){ return (x < 16 ? "0" : "") + x.toString(16); }).join("");
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {ntDataHora: ntDataHora, ntMeta: ntMeta, ntAbas: ntAbas, ntTextoArrumacao: ntTextoArrumacao, ntConferirTexto: ntConferirTexto,
    ntConferirMotivo: ntConferirMotivo, ntContador: ntContador, ntMensagemErro: ntMensagemErro, ntNovaChave: ntNovaChave};
}
