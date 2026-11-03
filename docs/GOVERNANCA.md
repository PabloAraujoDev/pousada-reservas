# Governança - decisões do clube pendentes e valores padrão adotados

O módulo "Governança" (tela de trabalho das camareiras) foi entregue com padrões sensatos. Cada valor abaixo é uma constante
em `pousada/config.py` (`GOV_*`) ou em `pousada/governanca.py` (`PAPEIS_ACAO`): trocar não exige mexer em mais nada.

| Decisão | Padrão adotado | Onde mudar |
|---|---|---|
| Troca de enxoval (hospedado sem arrumação há N dias) | 7 dias | `GOV_DIAS_TROCA_ENXOVAL` |
| Unidade vaga e pronta há M dias (selo "pronta há N dias") | 14 dias (não vira suja sozinha) | `GOV_DIAS_VAGA` |
| Janela para a camareira desfazer a PRÓPRIA marcação ("pronto" ou "iniciar") | 15 minutos | `GOV_JANELA_DESFAZER_MIN` |
| Hora da "troca atrasada" (chegada hoje e ainda não pronta) | 13:00 | `GOV_HORA_TROCA_ATRASADA` |
| Saída fixa (a unidade vira "suja" sozinha a partir daqui) | 12:00 | `GOV_HORA_SAIDA` |
| Entrada fixa (só exibição) | 14:00 | `GOV_HORA_ENTRADA` |
| Quem é a governanta | perfil `atendente` (sem perfil novo) | `PERMISSOES` em `permissoes.py` |
| Recepção | só marca "suja" e "pronta" e escreve observação | `PAPEIS_ACAO` em `governanca.py` |
| Camareira abre manutenção | não (escreve na observação; a governanta decide) | `governanca.manutencao` |
| Camareira vê o `grupo` da reserva | não (o servidor não envia) | `rotas_governanca._item` |
| Diretoria e consulta | só visualizam (sem ação) | `PERMISSOES` |

## Decisões que ainda cabem ao clube

1. Valores de N (enxoval) e M (vaga há muito tempo) definitivos.
2. Criar o perfil `governanta` (governança sem acesso a reservas) ou manter o `atendente`.
3. A recepção pode marcar "pronta" ou só "suja"/"hóspede saiu"?
4. A camareira pode abrir manutenção? Janela de desfazer e hora da troca atrasada.
5. A camareira pode ver o grupo/nome de grupo da reserva?
6. A suja automática deve ser às 12:00 fixas ou usar o horário real de saída quando houver?
7. Quem pode imprimir a lista de amanhã.
8. **Retenção dos eventos** da Governança (hoje sem prazo; veja `PRIVACIDADE.md`, seção 2.1).

## Como funciona (resumo)

- Situação **derivada** das reservas ativas (hospedada, saída, chegada, troca) é recalculada a cada consulta; a situação **registrada**
  pela equipe (suja, em arrumação, pronta, manutenção, observação) fica em `governanca_unidade`.
- A unidade com saída fica "suja" sozinha às 12:00, a não ser que alguém tenha arrumado depois ou confirmado a saída.
- Ações valem para uma ou várias unidades, em uma transação (tudo ou nada). Repetir a mesma ação é inofensivo ("já estava assim").
  Se outra pessoa mudou a unidade antes, a resposta é 409 dizendo quem mudou e quando.
- A 104 (interditada) recusa qualquer ação.
- O servidor deve usar o fuso America/Sao_Paulo: as regras de 12:00 e 13:00 usam a hora do servidor, nunca a do navegador.

## Fora da v1

Vistoria da supervisora, controle de enxoval e amenities, ordem de serviço de manutenção, interdição por período e gancho no
"mover reserva" (marcar a unidade antiga como suja) ficam para uma próxima versão.
