"use strict";
/* Governança - lógica PURA (sem tela, sem rede): agrupar, filtrar, contar, escolher ações em massa, ordenar a
 * impressão e montar textos. Roda no navegador (carregada antes de governanca.js) e em node
 * (tests/js/governanca_logica.js). Os dados já chegam filtrados pelo servidor para o perfil de quem está logado. */

var GV_GRUPOS = ["Térreo", "2º andar", "3º andar", "Chalés"];
var GV_ROTULO = {suja: "Suja", em_arrumacao: "Em arrumação", pronta: "Pronta", hospedada: "Hospedada",
  aguardando_saida: "Aguardando saída", manutencao: "Manutenção", interditada: "Interditada"};
var GV_ROTULO_ACAO = {iniciar: "Iniciar", pronta: "Pronto", suja: "Marcar suja", observacao: "Observação",
  manutencao_abrir: "Manutenção", manutencao_fechar: "Encerrar manutenção"};
var GV_ACOES_EM_MASSA = ["iniciar", "pronta", "suja"];
var GV_FILTRO_VAZIO = {andar: "", situacao: "", chegada: false, saida: false, busca: ""};

function gvNorm(s){ return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim(); }

function gvAgrupar(itens){          // [{nome, itens}] na ordem fixa dos andares; grupo vazio não aparece
  return GV_GRUPOS.map(function(nome){
    return {nome: nome, itens: itens.filter(function(i){ return i.andar === nome; })};
  }).filter(function(g){ return g.itens.length > 0; });
}
function gvFiltroAtivo(f){
  return !!(f.andar || f.situacao || f.chegada || f.saida || gvNorm(f.busca));
}
function gvCorresponde(i, f){
  if (f.andar && i.andar !== f.andar) return false;
  if (f.situacao && i.situacao !== f.situacao) return false;
  if (f.chegada && !i.chegada_hoje) return false;
  if (f.saida && !i.saida_hoje) return false;
  var b = gvNorm(f.busca);
  return !b || gvNorm(i.u).indexOf(b) >= 0;
}
function gvFiltrar(itens, f){ return itens.filter(function(i){ return gvCorresponde(i, f); }); }

function gvContagens(itens){        // contagens do cabeçalho do grupo (a 104 interditada não entra em nenhuma)
  var c = {saida: 0, suja: 0, em_arrumacao: 0, pronta: 0};
  itens.forEach(function(i){
    if (i.saida_hoje) c.saida++;
    if (c[i.situacao] !== undefined) c[i.situacao]++;
  });
  return c;
}
function gvTextoContagens(c){
  return "Saída " + c.saida + " | Suja " + c.suja + " | Em arrumação " + c.em_arrumacao + " | Pronta " + c.pronta;
}

/* Ações em massa: só as que valem para TODAS as unidades selecionadas (interseção das listas `pode` do servidor). */
function gvAcoesComuns(itens){
  if (!itens.length) return [];
  return GV_ACOES_EM_MASSA.filter(function(a){
    return itens.every(function(i){ return (i.pode || []).indexOf(a) >= 0; });
  });
}
function gvPrecisaConfirmarSaida(itens){ return itens.some(function(i){ return i.situacao === "aguardando_saida"; }); }
function gvMotivoSemAcao(itens){
  if (!itens.length) return "";
  var sem = itens.filter(function(i){ return !(i.pode && i.pode.length); });
  if (sem.length) return "Sem ação disponível para " + sem.map(function(i){ return i.u; }).join(", ") + ".";
  return "Não há uma ação que sirva para todas as selecionadas. Escolha unidades na mesma situação.";
}
function gvSelecionaveis(itens){ return itens.filter(function(i){ return i.situacao !== "interditada"; }); }

/* Assinatura dos dados: só redesenha a lista quando ela muda (o polling de 8 s não pisca nem tira o foco). */
function gvAssinatura(dados){
  return JSON.stringify([dados.hoje, dados.dia, dados.totais, dados.unidades]);
}
function gvMudancas(antes, depois){  // unidades cuja situação mudou entre duas listas (para o aviso por voz)
  var mapa = {};
  (antes || []).forEach(function(i){ mapa[i.u] = i.situacao; });
  return (depois || []).filter(function(i){ return mapa[i.u] !== undefined && mapa[i.u] !== i.situacao; })
    .map(function(i){ return {u: i.u, de: mapa[i.u], para: i.situacao}; });
}

/* Textos */
function gvNomeUnidade(u){ return /^Chal/.test(u) ? u : "Apartamento " + u; }
function gvPessoas(n){ return n + (n === 1 ? " pessoa" : " pessoas"); }
function gvPessoasDoCartao(i){
  if (i.pessoas) return gvPessoas(i.pessoas);
  if (i.chegada_hoje && i.chegada_hoje.pessoas) return gvPessoas(i.chegada_hoje.pessoas);
  return "";
}
function gvTextoDias(i){            // o texto mostra só o que vale
  var t = [];
  if (i.alerta_enxoval) t.push("Troca de enxoval (" + i.dias_sem_arrumacao + " dias)");
  else if (i.dias_sem_arrumacao && (i.situacao === "suja" || i.situacao === "hospedada"))
    t.push("Há " + i.dias_sem_arrumacao + (i.dias_sem_arrumacao === 1 ? " dia" : " dias") + " sem arrumação");
  if (i.pronta_ha_dias != null) t.push("Pronta há " + i.pronta_ha_dias + " dias");
  return t;
}
function gvSelos(i){                // selos de texto do cartão: [{txt, tipo}]
  var s = [];
  if (i.chegada_hoje) s.push({txt: "In " + i.chegada_hoje.hora, tipo: "in"});
  if (i.saida_hoje) s.push({txt: "Out " + i.saida_hoje.hora, tipo: "out"});
  if (i.troca_hoje) s.push({txt: "TROCA HOJE", tipo: "troca"});
  if (i.atrasada) s.push({txt: "ATRASADA", tipo: "atrasada"});
  return s;
}
function gvAria(i){
  var p = [gvNomeUnidade(i.u), (GV_ROTULO[i.situacao] || i.situacao).toLowerCase()];
  if (i.saida_hoje) p.push("saída " + i.saida_hoje.hora);
  if (i.chegada_hoje) p.push("chegada " + i.chegada_hoje.hora);
  if (i.troca_hoje) p.push("troca hoje");
  if (i.atrasada) p.push("atrasada");
  var pes = gvPessoasDoCartao(i); if (pes) p.push(pes);
  gvTextoDias(i).forEach(function(t){ p.push(t.toLowerCase()); });
  if (gvPodeEntrar(i)) p.push("pode entrar");
  return p.join(", ");
}
function gvPodeEntrar(i){ return i.situacao === "pronta" && !!i.chegada_hoje; }

/* Resposta de uma ação */
function gvResumoResultado(resultados, total){
  var ok = resultados.filter(function(r){ return r.resultado === "ok"; }).length, ja = resultados.length - ok;
  var t = ok + " de " + total + " atualizada" + (total === 1 ? "" : "s");
  return ja ? t + " (" + ja + " já estava" + (ja === 1 ? "" : "m") + " assim)" : t;
}
function gvTextoConflito(c){
  var quem = c.por ? c.por : "outra pessoa", quando = c.em ? " às " + c.em : "";
  return c.u + ": agora está " + (GV_ROTULO[c.situacao_atual] || c.situacao_atual).toLowerCase() + " (" + quem + quando + ")";
}
function gvSelecaoSemConflitos(selecao, conflitos){   // selecao: lista de unidades; tira as que deram conflito
  var fora = {};
  (conflitos || []).forEach(function(c){ fora[c.u] = true; });
  return selecao.filter(function(u){ return !fora[u]; });
}

/* Impressão: trocas, saídas, chegadas, hospedadas com alerta de enxoval, demais. */
function gvCategoriaImpressao(i){
  if (i.troca_hoje) return 1;
  if (i.saida_hoje) return 2;
  if (i.chegada_hoje) return 3;
  if (i.alerta_enxoval) return 4;
  return 5;
}
var GV_TITULO_CATEGORIA = {1: "Trocas (saída e entrada no mesmo dia)", 2: "Saídas", 3: "Chegadas", 4: "Hospedadas com troca de enxoval", 5: "Demais unidades"};
function gvOrdenarImpressao(itens, ordemUnidades){
  var pos = {};
  ordemUnidades.forEach(function(u, k){ pos[u] = k; });
  return itens.filter(function(i){ return i.situacao !== "interditada"; }).sort(function(a, b){
    return gvCategoriaImpressao(a) - gvCategoriaImpressao(b) || (b.atrasada ? 1 : 0) - (a.atrasada ? 1 : 0) || pos[a.u] - pos[b.u];
  });
}

if (typeof module !== "undefined" && module.exports){
  module.exports = {gvNorm: gvNorm, gvAgrupar: gvAgrupar, gvFiltroAtivo: gvFiltroAtivo, gvCorresponde: gvCorresponde, gvFiltrar: gvFiltrar,
    gvContagens: gvContagens, gvTextoContagens: gvTextoContagens, gvAcoesComuns: gvAcoesComuns, gvPrecisaConfirmarSaida: gvPrecisaConfirmarSaida,
    gvMotivoSemAcao: gvMotivoSemAcao, gvSelecionaveis: gvSelecionaveis, gvAssinatura: gvAssinatura, gvMudancas: gvMudancas,
    gvNomeUnidade: gvNomeUnidade, gvPessoasDoCartao: gvPessoasDoCartao, gvTextoDias: gvTextoDias, gvSelos: gvSelos, gvAria: gvAria,
    gvPodeEntrar: gvPodeEntrar, gvResumoResultado: gvResumoResultado, gvTextoConflito: gvTextoConflito,
    gvSelecaoSemConflitos: gvSelecaoSemConflitos, gvCategoriaImpressao: gvCategoriaImpressao, gvOrdenarImpressao: gvOrdenarImpressao,
    GV_FILTRO_VAZIO: GV_FILTRO_VAZIO, GV_ROTULO: GV_ROTULO};
}
