# Análise de Requisitos — Sistema de Reservas da Pousada Boa Esperança

Cliente: Clube dos Oficiais da PM MG (BH) — Pousada Boa Esperança (25 unidades)
Responsável pela distribuição das reservas: Pablo
Versão: 0.1 (rascunho para validação do clube)  ·  Data: 27/10/2026

> **Como ler este documento.** Itens marcados **[DECISÃO DO CLUBE]** não podem ser definidos pelo desenvolvedor.
> Itens marcados **[CONFIRMAR]** têm uma sugestão de mercado, mas precisam de resposta do clube.
> As recomendações legais (FNRH, LGPD) vieram de consultoria sem acesso a fontes oficiais atualizadas: **validar com assessoria jurídica**.

---

## 1. Objetivo

Substituir as planilhas mensais por um sistema único em que a atendente informa apartamento, entrada e saída; o sistema impede conflitos, organiza por semana e gera as folhas de distribuição e de café da manhã. Além disso: importar as reservas futuras já existentes em Excel, manter um cadastro de hóspedes e fazer o check-in digital com assinatura.

## 2. Situação atual (problemas)

- Uma planilha por mês, reservas empilhadas por apartamento; difícil ver datas livres.
- Reservas que viram o mês são digitadas duas vezes; há datas inválidas (31/11) e duplicatas.
- Pagamento em texto livre; gratuidades sem trilha de autorização.
- Folha semanal e contagem do café feitas à mão; pedidos sem apartamento ficam soltos no fim.
- Check-in 100% manual: ficha do Word impressa e preenchida à mão.

## 3. Usuários e permissões

| Perfil | Pode | Não pode |
|---|---|---|
| Administrador (Pablo) | Tudo: usuários, importação, backup, ver histórico completo, excluir | — |
| Atendente | Criar/editar reservas, registrar pagamentos, criar grupos, solicitar gratuidade | Excluir definitivamente, importar, ver histórico completo, alterar tarifas |
| Recepção | Check-in/out, assinatura, cadastro de hóspedes, pagamento no balcão | Relatórios financeiros, tarifas |
| Camareira | Ver lista de unidades do dia, marcar "pronto" | Ver valores e dados pessoais |
| Diretoria | Ler relatórios, aprovar gratuidades/descontos | Editar reservas |

Regra transversal: toda alteração de valor, pagamento, gratuidade ou cancelamento grava quem, quando e antes/depois. **[CONFIRMAR]** a matriz com o clube; quem aprova desconto e em qual limite é **[DECISÃO DO CLUBE]**.

## 4. Requisitos funcionais

### RF1 — Mapa de reservas (já existe no MVP; evoluir)
- Grade unidades × dias (1, 2, 4 semanas e mensal); hoje destacado; fim de semana/feriado em tom diferente.
- Criar reserva por clique (futuro: clique-e-arraste); barra do meio do dia de entrada ao meio do dia de saída.
- Conflito validado no servidor; saída e entrada no mesmo dia permitidas; apto 104 bloqueado.
- Cores por pagamento, com ícone/texto além da cor (acessibilidade).
- Bloqueio de unidade (manutenção, uso institucional) com motivo e período.
- Filtros (andar, tipo, livre no período, busca por nome); impressão A4 paisagem com fallback para preto e branco.

### RF2 — Importar lista (Excel)
Fluxo: **enviar arquivo → pré-visualizar (nada gravado) → corrigir problemas → confirmar**.
- Aceitar .xlsx (e .csv); uma aba por mês; mês/ano de referência inferido do nome da aba, editável.
- Pré-visualização com semáforo por linha (ok / aviso / erro) e contadores no topo.
- Categorias de problema: data inválida, apto inexistente (sugerir o mais parecido), sem apto (vira pedido a alocar), conflito (mostrar as duas reservas e permitir trocar de apto), duplicata, virada de mês (fundir em uma só), pagamento não reconhecido (importa como "a confirmar" preservando o texto original).
- Regras de leitura: "dd/mm A dd/mm" tolerante a variações; saída anterior à entrada tenta ano+1; linha sem apto logo abaixo de uma reserva = acompanhante; linha "19 aptos e 2 chalés" = grupo a alocar, nunca alocado sozinho.
- **Idempotente**: reimportar o mesmo arquivo cria 0 reservas. Reserva já existente e alterada: o sistema mostra a diferença e pergunta; nunca sobrescreve algo editado à mão sem confirmação. Reserva que sumiu da planilha não é cancelada.
- Importação em uma transação (tudo ou nada), com lote identificado e botão "Desfazer importação".
- Relatório de erros baixável.

### RF3 — Cadastro de hóspedes
- Base reutilizável entre estadias; busca por CPF, nome (sem acento) ou telefone.
- CPF validado (dígito verificador); estrangeiros por documento + país. Duplicata só **sugerida** ("possível cadastro existente"), nunca fundida automaticamente; mesclagem manual com auditoria.
- Vínculo com o clube (sócio, dependente, convidado, outro): campo opcional, só se for regra de tarifa/convênio **[DECISÃO DO CLUBE]**.
- Coletar o mínimo necessário (ver RNF de privacidade).

### RF4 — Check-in digital com assinatura
- Fluxo híbrido recomendado: (a) pré-check-in por link no WhatsApp (token aleatório, uso único, com validade) para o hóspede preencher/atualizar dados; (b) conferência e assinatura no balcão, em tablet, com a recepção validando o documento original.
- Hóspede recorrente: recepção busca, o hóspede confere os dados já cadastrados e assina.
- Assinatura desenhada na tela (dedo/caneta); rejeitar traço vazio.
- Prova gravada: imagem da assinatura, data/hora, usuário da recepção, versão do termo exibido, cópia imutável dos dados confirmados e sua impressão digital (hash). Ficha assinada não é editável; correção gera nova versão.
- Menores constam na ficha do responsável; menor sem os pais exige autorização (registrar e arquivar).
- Impressão da ficha em PDF a partir da cópia assinada, em A4, parecida com o modelo atual do Word, com "2ª via" nas reimpressões.
- **Pendência crítica:** confirmar se o clube precisa registrar a FNRH no sistema oficial do Ministério do Turismo (FNRH Digital / Cadastur). Se sim, o check-in do sistema será registro de apoio ou precisará de integração. **[DECISÃO DO CLUBE + jurídico]**

### RF5 — Reservas, grupos e pedidos
- Reserva de vários apartamentos de uma vez (turma) com nome do grupo; editar/cancelar o grupo inteiro com confirmação.
- Pedidos sem apartamento (lista de espera) com sugestão de unidades livres e alocação em dois cliques.
- Cancelamento lógico (nunca apagar): motivo, quem, quando. Pré-reserva com prazo de validade **[CONFIRMAR]**.
- Check-in/check-out com status da unidade (sujo, limpo, vistoriado, bloqueado).

### RF6 — Pagamentos e gratuidades
- Pagamento estruturado: valor total, valor pago, forma, data, quem recebeu, recibo; status calculado (pendente, parcial, quitado, isento).
- Gratuidade só salva com motivo e autorizador; relatório mensal para a diretoria.
- Tarifas, sinal e cancelamento: **[DECISÃO DO CLUBE]** (ver seção 7). O sistema deve guardar o valor de tabela na reserva para que mudar a tarifa não altere reservas antigas.

### RF7 — Folhas e relatórios
- Folha da semana (PDF/Excel): apto, hóspedes, qtd, entrada, saída, pagamento, observações, e bloco do café da manhã por faixa (adultos, crianças 5–17, bebês 0–4).
- Painel "Hoje": chegadas, saídas, hospedados, saldos a receber, unidades a limpar.
- Mapa de limpeza do dia com saída+entrada no mesmo dia em destaque; folha do café com restrições alimentares (alergia grave em destaque).
- Relatório mensal: ocupação (total e paga), diária média, previsto × recebido, gratuidades, cancelamentos.

## 5. Requisitos não funcionais

- **Segurança:** login individual (sem senha compartilhada), sessão por cookie assinado, cabeçalhos de segurança, escape de HTML, sistema só na rede local (não expor a porta na internet).
- **Privacidade (LGPD):** coletar o mínimo; não coletar sem necessidade foto de documento, estado civil, renda, saúde, biometria. Dados de saúde (alergias, acessibilidade) são sensíveis: finalidade clara e acesso restrito. Consentimento separado e revogável para o que não é obrigatório. Banco e backups fora do Git, com disco/pasta protegidos (ex.: BitLocker). Não registrar dados pessoais em logs.
- **Confiabilidade:** todas as escritas em transação; conflito e gravação na mesma transação; edição simultânea detectada por versão; backup automático (30 últimos) e restauração testada; **backup também fora do OneDrive/da máquina**.
- **Desempenho:** mapa de 4 semanas com 2.000 reservas em menos de 1 s.
- **Usabilidade:** poucos cliques para lançar reserva; funciona em celular/tablet (~400 px); contraste e foco visíveis nos temas claro e escuro; interface em português do Brasil.
- **Manutenção:** migrações numeradas que preservam dados; testes automatizados; documentação de regras.

## 6. Etapas de entrega e critérios de aceite

Proposta ajustada ao pedido do clube (importação e check-in digital como prioridades). O cadastro de hóspedes e o check-in nascem **junto** com login, perfis e histórico, por lidarem com dados pessoais.

| Etapa | Conteúdo | Aceite |
|---|---|---|
| 1. Base e importação | Login/perfis, histórico, cancelamento lógico, backup, **importar lista**, mapa evoluído | Importar o mês corrente e os futuros e o mapa conferir com a planilha; reimportar cria 0; nunca duas reservas no mesmo apto/data |
| 2. Hóspedes e check-in digital | Cadastro de hóspedes, pré-check-in por link, assinatura no balcão, ficha em PDF | Hóspede recorrente confere e assina em menos de 1 minuto; ficha assinada não pode ser alterada |
| 3. Pagamentos, gratuidades, grupos | Pagamento estruturado, gratuidade com autorizador, turmas, pedidos a alocar | Toda reserva mostra status e saldo; gratuidade só salva com motivo e autorizador; turma de 8 aptos em um formulário |
| 4. Folhas, relatórios, produção | Folha semanal, café por faixa, limpeza, relatório mensal, servidor de produção, acesso por nome na rede | Folha sai sem edição manual e o café confere com o mapa; o sistema volta sozinho após reiniciar o computador |

Recomendação: **operar em paralelo com a planilha por um mês** antes de desligá-la.

## 7. Decisões e informações que dependem do clube

Sugestões abaixo são o que costuma ser padrão de mercado; **não são decisões** e não serão codificadas até o clube responder.

1. Quem pode se hospedar (sócio, dependente, convidado, outras corporações) e como se comprova o vínculo. Há prioridade/janela por categoria?
2. Tabela de tarifas (tipo de apto × categoria × temporada), política para crianças, café incluso ou não.
3. Sinal (percentual e prazo; hoje "parcial 30%" é regra ou costume?) e prazo para a reserva expirar sem sinal.
4. Política de cancelamento, no-show e remarcação.
5. "Acerta na pousada": para quem é permitido e com qual limite.
6. Gratuidades: lista de beneficiários, cotas por pessoa/ano, quem autoriza, se cobre só diária ou também café e taxas.
7. Regras de grupo: tamanho mínimo, bloqueio de apartamentos, prazo da lista nominal, quem paga.
8. Formas de pagamento aceitas, recibo/nota, desconto em folha.
9. **Definido (27/10/2026):** check-in a partir das 14:00, check-out até 12:00; entrada antecipada permitida se o apartamento já estiver liberado. Ainda em aberto: tolerância de saída tardia e mínimo de diárias em feriados.
10. Quais dados o hóspede deve fornecer, por quanto tempo guardar, política de descarte, **encarregado pela LGPD** e texto do termo de consentimento.
11. Obrigação de registro na FNRH Digital/Cadastur.
12. Relatórios e metas que a diretoria quer, e para quem.
13. Bloqueios institucionais de apartamentos (diretoria, eventos).
14. Quem é o administrador substituto e de quem é a propriedade do sistema e dos dados.

## 8. Perguntas sobre a planilha (para o Pablo e a atendente)

1. Um arquivo por mês é sempre o formato? Há abas por mês? Pode enviar planilhas reais de 3 meses, sem telefones/CPFs se possível?
2. Depois da migração, qual é a fonte da verdade: o sistema ou a planilha?
3. Reservas na virada do mês aparecem nos dois arquivos com as datas completas? Qual vale quando divergem?
4. Como o ano é indicado? Há reservas que cruzam o ano?
5. O que significam os pedidos sem apartamento no fim: lista de espera, pré-reserva ou grupo a alocar?
6. Como se registra um grupo grande ("19 aptos e 2 chalés"): lista dos aptos ou só a quantidade? Quem aloca?
7. Todas as formas de escrever pagamento e o que cada uma significa; há valores?
8. Acompanhantes ficam sempre abaixo, sem apto? Quem conta na coluna "qtd"? Crianças e pets precisam de campo próprio?
9. Cancelamentos, no-show e trocas de apto: como aparecem (riscado, cor, texto)? As cores têm significado?
10. A data de saída é o dia do check-out? Há overbooking consciente? O 104 e bloqueios aparecem na planilha?

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Adoção pela atendente | Envolvê-la no desenho das telas; entrada rápida; treinamento curto; mês em paralelo |
| Migração (texto livre, nomes inconsistentes) | Tela de revisão; dicionário de pagamento editável; começar pelo mês corrente + futuros |
| Dados pessoais (LGPD) | Coleta mínima; perfis; histórico de acesso; retenção definida; backup protegido |
| Registro paralelo à FNRH oficial | Resolver a pendência de RF4 antes de programar o check-in |
| Dependência de uma pessoa | Segundo administrador; documentação; backups testados; exportação para Excel |
| Regra não documentada surgir tarde | Respostas da seção 7 validadas por escrito |
| Banco no OneDrive | Mover banco e backups para fora do OneDrive; cópia externa |
