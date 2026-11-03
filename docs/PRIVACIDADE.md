# Privacidade e proteção de dados (LGPD) - Sistema de Reservas da Pousada Boa Esperança

Documento para a diretoria e o encarregado de dados do Clube dos Oficiais da PM MG (o clube é o **controlador**).
Descreve o que o sistema trata e como protege. Os itens marcados **[DECISÃO DO CLUBE]** não foram decididos por quem
construiu o sistema e precisam de definição formal (com assessoria jurídica, se possível).

## 1. Quais dados pessoais o sistema trata hoje

| Dado | De quem | Para quê | Onde aparece |
|---|---|---|---|
| Nome do hóspede, acompanhantes e observações (campo livre) | Hóspedes | Fazer e conferir a reserva | Mapa, folha da semana, busca, histórico (só o resumo) |
| Situação do pagamento (pago, parcial, pendente...) | Hóspedes | Controle financeiro | Mapa e reservas, para quem tem permissão |
| Grupo/turma | Hóspedes | Organizar reservas coletivas | Mapa |
| Tipo de hóspede (sócio do clube ou convidado; opcional) | Hóspedes | Saber a categoria de quem se hospeda | Mapa (dica da barra), busca, formulário e CSV, para quem vê reservas |
| Valor da diária (opcional, guardado em centavos) | Clube | Controle financeiro da reserva | **Só** no formulário da reserva (ao abri-la) e no CSV completo; nunca em listas, mapa, busca, folha (tela, PDF e CSV), camareiras, histórico ou logs |
| Notas da reserva e do apartamento (texto livre curto, com autor e data) | Hóspedes (o que a equipe anotar) | Registrar combinados e avisos do quarto | **Só** na aba Observações (Resumo da conta e diálogo Observações), por perfil; nunca em listas, folha, CSV, histórico ou logs; camareira só a nota do apartamento, saneada |
| Hóspedes da hospedagem (acompanhantes: nome e tipo adulto/criança) e dados pessoais **opcionais** de titular e acompanhantes: documento (CPF, RG ou passaporte), data de nascimento, nacionalidade, profissão, procedência e destino | Hóspedes | Registro do hóspede e ficha de check-in (padrão FNRH) | **Só** no painel Hóspedes do Resumo da conta e na ficha impressa, para quem tem `hospedes.gerir` ou `ficha.imprimir`; diretoria e consulta veem nome, tipo e o documento **mascarado** (só os 2 últimos caracteres); nunca em listas, mapa, busca, folha, CSV, camareiras, governança, histórico ou logs |
| Placa do veículo (opcional) | Hóspedes | Controle de estacionamento e ficha de check-in | Completa só para `veiculo.editar` ou `ficha.imprimir`; os demais veem `ABC****`; nunca em CSV, listas, histórico ou logs |
| Estado da hospedagem: check-in efetivo (quando e por quem) e "apartamento liberado, conta aberta" (quando e por quem) | Funcionários | Controle da operação | Resumo da conta e lista de contas abertas, para quem vê reservas |
| Login, nome e perfil | Funcionários do clube | Controlar quem entra e o que pode fazer | Tela Usuários |
| Endereço IP e horário dos acessos, falhas de login | Funcionários | Segurança e auditoria | Histórico (administrador) e logs do servidor |

O sistema **não exige** CPF, RG, endereço, telefone em campo próprio nem assinatura digital. Desde a etapa 3A existe o cadastro
**opcional** de hóspedes (item 2.4): documento, data de nascimento, nacionalidade, profissão, procedência, destino e placa só são
guardados se a recepção os informar. O check-in digital (FNRH Digital/Cadastur) continua não existindo.
Observações em texto livre podem receber dados que a pessoa digitar (ex.: telefone): oriente a equipe a não registrar dados
sensíveis nesse campo.

## 2. Quem pode ver o quê

- **Camareira:** só unidade, datas e número de pessoas. Nunca vê nome, pagamento ou telefone.
- **Consulta:** só visualiza e imprime. Não exporta nem vê histórico.
- **Recepção:** vê reservas; altera só pagamento e observações. Vê o valor da diária, mas não o altera.
- **Valor da diária:** vê quem tem a permissão `valores.ver` (administrador, atendente, recepção e diretoria); informa/altera quem
  tem `valores.editar` (administrador e atendente). Consulta e camareira nunca recebem o valor (o servidor não envia o campo).
  O histórico registra apenas que a diária foi "alterada", sem o número; mudanças do tipo de hóspede registram antes e depois.
  Reservas importadas da planilha ficam sem tipo e sem valor.
- **Atendente, diretoria e administrador:** conforme a tabela de perfis do sistema (tela Usuários).
- Cada pessoa tem login próprio. Desativar um usuário corta o acesso na hora.

## 2.1 Governança (arrumação das unidades)

Inventário dos dados do módulo Governança (tabelas `governanca_unidade` e `governanca_evento`):

| Dado | Onde fica | Quem vê | Quem altera |
|---|---|---|---|
| Situação da unidade (suja, em arrumação, pronta), hora e login de quem marcou | `governanca_unidade` | todos com `governanca.ver` | camareira, atendente, recepção (restrita), administrador |
| Observação curta (até 140 caracteres) e motivo de manutenção | `governanca_unidade` | todos com `governanca.ver` | quem tem `governanca.atualizar` (manutenção: atendente e administrador) |
| Registro de eventos (quem, quando, ação, de/para, lote, IP) | `governanca_evento` (imutável por gatilho) | quem tem `governanca.ver` (sem IP; a camareira só vê os do dia) | ninguém (só acrescenta) |
| Abrir/fechar manutenção e correções do administrador | `historico` (imutável) | administrador e diretoria (resumo) | ninguém |

- **A camareira não recebe dados do hóspede.** O servidor filtra a resposta: nunca envia nome, número da reserva, grupo, pagamento,
  tipo (sócio/convidado), valor, telefone nem extras. Recebe só situação, horários fixos (entrada 14:00, saída 12:00), número de pessoas,
  dias sem arrumação e a observação da reserva já saneada (trechos com pagamento, valores ou telefone são descartados).
- Quem tem `reservas.ver` (recepção, atendente, diretoria, consulta, administrador) vê também o nome do hóspede e o grupo no cartão.
  Pagamento, valor, tipo e telefone **nunca** aparecem na Governança.
- O texto da observação e do motivo **nunca vai para nenhum log** (nem o de eventos, nem o histórico, nem os logs de acesso): o evento só
  registra que "a observação mudou".
- A lista impressa da arrumação não leva nomes.
- **Retenção dos eventos: [DECISÃO DO CLUBE].** Hoje os eventos são guardados sem prazo (a tabela não permite apagar). Definir por quanto
  tempo manter e, se for o caso, como arquivar.
- Atenção da equipe: a observação é texto livre; não registre dados pessoais ou de saúde nela.

## 2.2 Despesas (conta de consumo da reserva)

- **O que é guardado** (tabelas `despesa_lancamento` e `despesa_conta`, migração 012): categoria, descrição (2 a 80 caracteres), quantidade,
  valor unitário e total em centavos, apartamento da época, data/hora local do servidor, login e IP de quem lançou, motivo do estorno
  (5 a 140 caracteres). Log **imutável** (triggers): nada se edita nem se apaga; o erro se corrige por estorno (nova linha negativa).
- **Quem vê:** só `despesas.ver` (admin, atendente, recepção, diretoria). Consulta e camareira não têm acesso. Lançar: admin, atendente,
  recepção. Estornar: admin e atendente (recepção: decisão do clube pendente).
- **Onde o valor aparece:** somente nas rotas `/api/reservas/<id>/despesas`, `/api/despesas/<id>/estorno` e no extrato impresso. Nunca em
  listas, calendário, mapa, folha, CSV, camareiras, governança, histórico, logs nem mensagens de erro. A lista de reservas traz apenas
  o indicador booleano `tem_despesa` (só para `despesas.ver`). A diária no total da estadia só para quem também tem `valores.ver`.
- **Histórico:** grava `despesa_lancada`/`despesa_estornada` com apenas `{categoria, itens}`; nunca valor, descrição nem motivo.
- **Cartão:** descrição e motivo passam pelo detector de número de cartão (422, sem repetir o texto).
- **Retenção/backup:** o log entra no backup do banco; reservas com lançamentos não podem ser excluídas (cancelar exige saldo zero).

## 2.3 Notas (anotações da reserva e do apartamento) e Resumo da conta

- **Notas** (tabela `nota`, migração 013): texto de 1 a 300 caracteres com autor (login), data/hora do servidor e IP. É um log **imutável**
  (triggers): corrigir grava uma nova linha (o texto anterior continua guardado) e "excluir" apenas **oculta** (com motivo); nada se apaga.
  Duas abas: **Reserva** (vale só para aquela reserva; o campo `o` continua intacto como "Observação padrão") e **Apartamento** (vale para a
  unidade, hoje e no futuro).
- **Quem lê:** `reservas.ver` (admin, atendente, recepção, diretoria, consulta). **Camareira não lê notas de reserva**; da nota do
  apartamento ela recebe só o texto já passado por `observacao_segura` (sem telefone, valor ou pagamento) e **sem o nome do autor**
  (decisão do clube pendente: se a camareira deve ler essa aba; hoje a regra está no servidor e pode ser desligada).
- **Quem escreve:** reserva = admin, atendente, recepção (`notas.escrever`); apartamento = admin e atendente (`notas.escrever_unidade`).
  Corrigir ou ocultar: o autor até 24 horas depois; depois disso (ou qualquer nota) só quem edita reservas (admin e atendente).
  Notas ocultas e textos anteriores: só o administrador (`notas.ver_ocultas`).
- **Onde o texto aparece:** somente nas rotas `/api/reservas/<id>/notas`, `/api/unidades/<unidade>/notas` e `/api/notas/<id>/...`, na aba de
  observações do Resumo da conta e do diálogo Observações. **Nunca** em listas, mapa, calendário, busca, folha, CSV, histórico, logs nem
  mensagens de erro. O histórico grava só `nota_adicionada`/`nota_corrigida`/`nota_ocultada` (sem texto).
- **Cartão:** todo texto de nota e de motivo passa pelo detector de número de cartão (422, sem repetir o texto). O formulário avisa ao digitar.
- **Retenção/backup:** o log entra no backup; reservas com notas não podem ser excluídas definitivamente nem removidas ao desfazer uma
  importação (cancelar é sempre possível). Limites: 100 notas por reserva e por apartamento, 20 correções por nota.
- **Resumo da conta** (tela ao clicar numa reserva): não cria dado novo. Reúne, para quem já pode ver, os dados da reserva, o total da
  estadia (diária x noites + despesas), as notas e a arrumação. **Valores**: a diária só aparece para `valores.ver` e as despesas para
  `despesas.ver`; sem a permissão o item nem existe na tela (o servidor não envia o campo). O total da estadia só existe para quem tem os dois
  acessos e com a diária informada (nunca um total parcial). Consulta vê tudo menos valores e despesas; a camareira nunca abre a tela.
  A **ficha impressa** (A4) leva só o cartão da reserva e os subtotais do perfil: sem observações, notas ou lançamentos.

## 2.4 Hóspedes, ficha FNRH, check-in e conta aberta (etapa 3A do Resumo da conta)

- **O que é guardado** (migração 014): em `hospedagem_hospede`, titular (só os dados extras; o nome continua em `reservas.nome`) e
  acompanhantes (nome, tipo adulto/criança, documento, nascimento, nacionalidade, profissão, procedência, destino). Tudo é **opcional**
  e só existe se informado. Em `reservas`: placa (7 caracteres normalizados), check-in (`checkin_em/por`) e conta aberta
  (`conta_aberta_em/por`). O total de hóspedes não passa do número de pessoas (`n`) da reserva.
- **Quem vê/edita:** `hospedes.gerir` (admin, atendente, recepção) e `ficha.imprimir` (idem) veem tudo; edita a lista só quem tem
  `hospedes.gerir`. **Diretoria e consulta** só veem nome, tipo e documento mascarado (`*********09`). **Camareira** não abre a tela.
  Placa: completa para `veiculo.editar`/`ficha.imprimir`, mascarada (`ABC****`) para os demais.
- **Onde o dado pessoal sai:** apenas em `GET|PUT /api/reservas/<id>/hospedes`, `GET /api/reservas/<id>` (placa), `PUT .../placa` e
  `POST .../ficha`. Nunca em listas, CSV, folha, camareiras, governança, busca, histórico, logs nem mensagens de erro (teste automático
  percorre todas as rotas GET nos 6 papéis).
- **Histórico e log:** o histórico (`historico`) grava só `hospedes_alterados {itens}`, `placa_alterada {placa: "definida|alterada|removida"}`,
  `checkin`, `checkin_revertido`, `conta_liberada`, `conta_reaberta` (sem valor algum). O log imutável `hospedagem_evento` (triggers
  contra alterar/apagar) guarda ação, autor, data/hora, IP e um detalhe curto **sem dado pessoal** (contagens e nomes de campos). Cada
  emissão da ficha FNRH também fica registrada ("ficha"): por isso é um POST.
- **Minimização e eliminação:** remover um acompanhante apaga a linha de verdade; excluir definitivamente a reserva (ou desfazer a
  importação) apaga junto os dados pessoais dos hóspedes (trigger). O log da hospedagem permanece, sem dado pessoal.
- **Cartão e texto:** nome, documento, nacionalidade, profissão, procedência e destino passam pelo detector de número de cartão (422, sem
  repetir o texto). Documento aceita só letras, números, ponto, hífen e barra (3 a 20); nascimento é data real entre 1900 e hoje;
  placa só no formato antigo (ABC-1234) ou Mercosul (ABC1D23).
- **Ficha FNRH impressa:** é montada na tela só na hora de imprimir e o DOM é limpo logo depois. Leva os campos do titular e dos
  acompanhantes (nome, documento, nacionalidade, procedência, destino, data de nascimento, profissão) e da hospedagem (motivo da
  viagem e meio de transporte **sempre em branco**, para preencher à mão; placa se houver). É um **modelo de apoio**: a adequação ao
  modelo oficial da FNRH/Cadastur é **[DECISÃO DO CLUBE]**. Oriente a guardar e descartar as fichas com segurança.
- **Reverter check-in / liberar / desfazer a liberação** (admin, atendente e recepção) exigem motivo (texto livre curto, sem número de cartão), gravado em
  `hospedagem_evento.detalhe` e no histórico (visível ao administrador e a `historico.reserva`). Não escreva dado pessoal sensível no motivo.
- **Pendente [DECISÃO DO CLUBE]:** prazo de guarda dos dados pessoais dos hóspedes (hoje sem prazo), base legal do tratamento de
  documento/nascimento/placa e se os campos passam a ser obrigatórios.

## 2.5 Pagamentos, transferência e eventos da conta (etapa 3B)

- **Dado financeiro:** pagamento (valor, forma, parcelas, bandeira, código de autorização/NSU, referência do Pix, autor, data/hora) só sai para quem
  tem `pagamentos.ver` (admin, atendente, recepção, diretoria); a lista Info só mostra as linhas de pagamento a quem tem essa capacidade. Receber:
  admin, atendente, recepção. Estornar pagamento, transferir despesas e reabrir conta: admin e atendente. Diretoria só vê. Consulta e camareira nada.
- **Cartão:** o sistema **nunca guarda número de cartão (PAN), CVV nem validade**. Só bandeira, modalidade (crédito/débito), parcelas e um código
  curto opcional de autorização/NSU (somente letras e números, até 12) ou, no Pix, uma referência (até 32). Esses campos e os motivos passam pelo
  detector de cartão e são recusados (422, sem repetir o texto) se parecerem um número; o formulário nem tem campo para o número.
- **Histórico e logs:** `historico` grava só `pagamento_recebido`/`pagamento_estornado` ({forma, itens: 1}), `despesas_transferidas`/`despesas_recebidas`,
  `diaria_zerada`, `conta_fechada`, `conta_reaberta_fechamento`: **nunca valor, motivo, NSU nem referência**. Os motivos de estorno, transferência,
  zerar a diária e reabrir ficam em `pagamento`, `despesa_lancamento` e `conta_evento` (imutáveis por trigger), visíveis só a quem pode ver a conta.
  Exceção deliberada: o motivo de reverter check-in, liberar e desfazer a liberação (seção 2.4) vai ao histórico para a auditoria do administrador.
- **Eliminação:** reserva com pagamento, transferência ou lançamento não pode ser excluída (cancela-se, depois de estornar os pagamentos); o valor da
  diária zerada é guardado em `conta_evento` para rastro. Prazo de guarda dos registros financeiros: **[DECISÃO DO CLUBE]** (obrigação fiscal/contábil).

## 3. Medidas de proteção em vigor

- Acesso só com login e senha (senhas guardadas como hash, nunca em texto), bloqueio contra tentativas repetidas e sessão com prazo.
- Conexão **criptografada (HTTPS)** obrigatória, com cabeçalhos de segurança.
- **Nenhum serviço de terceiros no navegador:** sem Google Fonts, sem análise de audiência, sem anúncios, sem rastreadores. As fontes
  são servidas pelo próprio sistema, então o endereço IP de quem usa não é enviado a nenhuma empresa. O sistema usa um único cookie,
  o da sessão de login (necessário, não serve para rastrear).
- Dados de hóspedes **não viajam em endereços (URLs)**, para não ficarem gravados em logs. A busca é feita na própria tela.
- Histórico de alterações que **não guarda dados pessoais do hóspede** (só o que mudou em termos de datas, unidade e situação).
- Servidor protegido: firewall, acesso administrativo só por chave, atualizações de segurança automáticas, cópias de segurança
  com permissão restrita.
- Logs de segurança e de acesso **sem senhas, sem cookies e sem o corpo das requisições**; o token CSRF também não é gravado.
- **Número de cartão nunca é guardado.** O servidor recusa (422) qualquer texto livre (nome, grupo, extras, observações, motivo de
  cancelamento, observação e motivo da governança) que pareça um número de cartão: 13 a 19 dígitos que passam na conferência de
  Luhn, ou o desenho 4-4-4-x mesmo que falhe nela. Números mascarados ("**** 1234") e "final 1234" são aceitos. A mensagem de
  recusa nunca repete o número. Na importação da planilha, a linha com cartão vira erro na prévia (não entra) e o item da lista
  de espera com cartão é descartado. **Dados antigos:** `python app.py varrer-cartoes` lista (somente leitura, sem mostrar o
  número) onde há campos suspeitos, para a equipe limpar manualmente.

## 4. Onde os dados ficam

- Em **um único servidor** (VPS contratado pelo clube, na Hostinger), em arquivo de banco de dados protegido por permissões do sistema operacional.
- Cópias de segurança no mesmo servidor e, quando for ativada, **cópia externa cifrada** (item pendente).
- O provedor de hospedagem e o registro do domínio são operadores/terceiros do ponto de vista da LGPD: **[DECISÃO DO CLUBE]** formalizar
  contrato/termos de tratamento com a Hostinger.

## 5. Pendências que dependem do clube

1. **Encarregado (DPO):** nomear e divulgar o canal de contato. **[DECISÃO DO CLUBE]**
2. **Base legal** de cada tratamento (execução de contrato com o hóspede, obrigação legal, legítimo interesse...). **[DECISÃO DO CLUBE]**
3. **Prazo de guarda** dos dados de reservas encerradas e dos logs de acesso (hoje o sistema não apaga reservas encerradas, e os logs giram
   por tamanho: no máximo cerca de 50 MB por tipo no sistema e 100 MiB no Caddy). Sugestão de ponto de partida, a validar: definir por escrito
   um prazo (por exemplo, anos exigidos por obrigação fiscal/legal) e uma rotina de eliminação ou anonimização. **[DECISÃO DO CLUBE]**
4. **Aviso de privacidade** para hóspedes (texto a ser aprovado pelo clube).
5. **Resposta a pedidos dos titulares** (acesso, correção, eliminação - LGPD art. 18): hoje o administrador atende buscando a reserva no
   sistema; definir quem responde e em quanto tempo. **[DECISÃO DO CLUBE]**
6. **Antes do check-in digital (FNRH Digital/Cadastur):** o cadastro opcional de hóspedes já existe (2.4); decidir quais dados (CPF, documento, assinatura), por quanto tempo guardar, quem acessa,
   e se a FNRH Digital/Cadastur são obrigatórias para o clube. **[DECISÃO DO CLUBE]**
7. **Plano de resposta a incidente:** quem avisa a ANPD e os titulares em caso de vazamento. **[DECISÃO DO CLUBE]**

## 5.1 Boas práticas para a equipe

- Uma conta por pessoa; nunca compartilhar login. Desativar quem sair do clube.
- Trocar a senha provisória no primeiro acesso e usar frases longas.
- Não registrar telefone, documento ou dado de saúde no campo de observações.
- Imprimir só o necessário (a folha das camareiras já sai sem dados de pagamento) e descartar impressos com segurança.
- Sair do sistema ao deixar o computador.

## 6. Resumo técnico para auditoria

Sem dependências externas no navegador (testes automáticos conferem isso); cookie `__Host-` Secure/HttpOnly/SameSite; CSP restrita ao
próprio domínio; Referrer-Policy `no-referrer`; arquivos públicos sem cookies; PDFs e CSV sem cache; logs sem dados sensíveis; backups com
permissão 600 e pasta 700.
