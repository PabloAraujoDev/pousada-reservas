# Operação do dia (listas dos cartões, coluna Ações, diálogos) - decisões e padrões

Parte 1 da especificação "Operação do dia". O que está pronto, o que foi decidido e o que ainda depende do clube.

## 1. O que existe hoje

- **Cartões que abrem listas.** No Calendário e no "Mapa da reserva", clicar em Check-ins, Check-outs, Interditados, Ocupados ou Vagos
  mostra a lista do dia. No Mapa a lista abre **no lugar** (painel logo abaixo dos cartões), sem diálogo; "Abrir no Calendário" continua
  disponível. Esc ou Fechar fecha e devolve o foco ao cartão. A pesquisa e o painel sobrevivem ao redesenho automático de 8 s.
- **Colunas por categoria.** Vagos e Interditados: Apto, Situação, "Quando fica ocupada/livre" (Livre até dd/mm, próxima reserva, ou
  "Sem próxima reserva"). Ocupados: coluna "Sai em" (data + 12h). Reservas: as colunas de sempre.
- **Coluna Ações** (primeira coluna): Informações e Observações para quem tem `reservas.ver` (todos menos a camareira). Botões sem
  permissão não existem no HTML. O botão **Despesas** está atrás do interruptor `OD_DESPESAS_LIGADO` (em `static/operacao_acoes.js`),
  **desligado**; a Parte 2 constrói o módulo e implementa `odAbrirDespesas(botao)`.
- **Informações:** apartamento, hóspede, nº da reserva, pessoas, período e noites, situação do dia, sócio/convidado, grupo, pagamento e
  estado da governança (só quem tem `governanca.ver`). Endereço/contato: "Cadastro não preenchido (será habilitado com o cadastro de
  hóspedes)". Nunca mostra valores.
- **Observações (fase 1, sem migração):** abas Reserva (campo `o`), Extras e Governança (observação e motivo de manutenção da unidade,
  quem/quando atualizou). Quem pode editar a reserva (`reservas.editar` ou `reservas.editar_pagamento`) usa o botão "Editar observação
  da reserva", que abre o formulário que já existe (as regras de permissão são as de sempre).
- **Detector de número de cartão** (veja `docs/PRIVACIDADE.md`): recusa com 422 em nome, grupo, extras, observações, motivo de
  cancelamento e textos da governança; a importação da planilha recusa a linha (erro "cartao" na prévia). O formulário mostra um aviso
  amarelo ao digitar. Varredura de dados antigos: `python app.py varrer-cartoes` (somente leitura).

## 2. Padrões adotados (para a Parte 2 seguir)

- Arquivos: `operacao_dia.js` (lógica pura e HTML da tabela, a MESMA função nos dois lugares), `operacao_dia_tela.js` (painel do Mapa),
  `operacao_acoes.js` (coluna Ações), `operacao_dialogos.js` (Informações), `operacao_notas.js` (Observações), `cartao.js` (aviso de
  cartão). Estilos na seção "OPERAÇÃO DO DIA" de `app.css`.
- Guarda de diálogos: `algumDialogoAberto()` (app.js) = qualquer `<dialog open>`; enquanto houver um aberto, o polling e o redesenho
  pausam. Novos diálogos (conta, notas) só precisam ser `<dialog>`.
- Diálogos novos montam o conteúdo por `textContent`; HTML de lista só por `esc()` (há testes que conferem linha a linha).
- Lista e Ações **nunca** trazem valor, telefone ou texto livre; o indicador de observação é só um ponto (booleano).
- Foco: cada botão tem `data-foco`; ao fechar um diálogo o foco volta ao botão de origem (`odDevolverFoco`).
- Celular (até 560 px): a lista vira cartões empilhados (rótulo pequeno sobre cada dado; Ações no rodapé com rótulo curto) e os
  diálogos ocupam a tela inteira.

## 3. O que a Parte 2 encontra pronto

- Ponto de extensão `odAbrirDespesas(botao)` e o interruptor `OD_DESPESAS_LIGADO`; o botão usa a capacidade `despesas.ver`
  (ainda inexistente no servidor) e nunca aparece em vagas/interditadas.
- Os botões levam `data-rid` (id da reserva), `data-un`, `data-dia` e `data-foco`; `odDevolverFoco` e `odGuardarOrigem` servem a
  qualquer diálogo novo.
- Observações fase 1 pronta; a fase 2 (`013_notas.sql`, notas com autoria, corrigir/ocultar) troca só o conteúdo da aba Reserva.
- O detector de cartão (`contem_numero_cartao`) deve ser aplicado a toda descrição de despesa, motivo de estorno e nota nova.

## 4. Decisões do clube ainda pendentes

1. Interdição com motivo e prazo (hoje a unidade 104 é fixa em `regras.py`; a lista diz "Fora de venda (sem previsão)").
2. Endereço/contato do hóspede: base legal, retenção e tabela `hospedes` própria (a linha de Informações segue "não preenchido").
3. Adultos/crianças (hoje só "pessoas").
4. Café da manhã incluso: a lista não afirma nada.
5. Quem lê a nota do apartamento (a camareira?), e se a recepção estorna só o próprio lançamento (Parte 2).
6. Limpeza dos números de cartão já gravados: rodar `python app.py varrer-cartoes` no servidor e corrigir à mão o que for listado.
7. Despesas (Parte 2A, pronto): cardápio/produtos com preço sugerido (hoje digitação livre), taxa de serviço (não existe), forma de
   cobrança/quitação (a conta não vira `p = pago`), prazo máximo para lançar após a saída, se a recepção pode estornar.
8. Fuso: a partir da migração 016 o sistema usa America/Sao_Paulo explicitamente (pacote `tzdata` em requirements.txt), seja qual for o fuso do servidor. Instalar `tzdata` na VPS antes de publicar (`pip install -r requirements.txt`).

## 5. Despesas (Parte 2A): o que existe e o que a Parte 2B encontra pronto

- Backend: `migrations/012_despesas.sql`, `pousada/despesas.py` (regras puras), `pousada/rotas_despesas.py` (listar, lançar, estornar,
  resumo de contas abertas). Capacidades `despesas.ver|lancar|estornar|conta`. A tabela `despesa_conta` (situação, quitação, versão)
  já existe; as rotas de fechar/reabrir/quitar ficam para a próxima etapa. Cancelar com saldo e excluir com lançamentos dão 409.
- Front: `despesas_logica.js` (parser/formatador em centavos, testado em node), `despesas_form.js`, `despesas.js` (diálogo, estorno,
  extrato A4 por `body.imp-extrato`, atualização de 8 s só da lista). Botão na coluna Ações com ponto `tem_despesa`.
- A Parte 2B reaproveita `GET /api/reservas/<id>/despesas` (itens + totais com `estadia_centavos` quando há diária e `valores.ver`).
- Limites conhecidos: cartão "Contas abertas" na faixa de resumo ainda não ligado (o endpoint `/api/despesas/resumo` existe).

## 6. Notas e Resumo da conta (Parte 2B): o que existe e as decisões

- **Notas** (`migrations/013_notas.sql`, `pousada/notas.py`, `pousada/rotas_notas.py`): log imutável de anotações da reserva e do apartamento,
  com autor e data, correção (nova linha; o texto antigo fica guardado) e ocultar (nunca apaga; motivo obrigatório). Controle de edição
  simultânea por versão (a nota tem `versao` = 1 + correções; versão antiga = 409). Duplo clique: `chave` única. Veja `docs/PRIVACIDADE.md` 2.3.
  - **Decisão:** o campo `o` da reserva **não migra**: segue como "Observação padrão" (editável no formulário, como sempre) e as notas são
    entradas adicionais com autor e data. É o mais seguro e compatível (nada do que já existe muda de lugar).
  - **Decisão:** o autor corrige ou oculta a própria nota por 24 horas; depois, só admin e atendente (`reservas.editar`).
  - O ponto "há observações" das listas considera também as notas: `GET /api/reservas` traz `tem_nota` e `GET /api/governanca` traz `tem_nota_unidade` (só sim/não, só para `reservas.ver`; a camareira não recebe).
  - Rotas: `GET|POST /api/reservas/<id>/notas`, `GET|POST /api/unidades/<apto>/notas`, `POST /api/notas/<id>/corrigir|ocultar`.
- **Resumo da conta** (`static/resumo_logica.js`, `resumo_conta.js`, `resumo_acoes.js`, `resumo_ligar.js`; estilos na seção "RESUMO DA
  CONTA" de `app.css`): `<dialog id="dlgResumo">` aberto por `abrirReserva(r)` ao clicar numa reserva (barra do mapa, linhas das listas do
  Mapa e do Calendário, grade do Calendário, resultado da Busca e item de Canceladas). Quem não tem `reservas.ver` cai no formulário.
  - O formulário `#dlg` continua igual e abre pelo botão **Editar dados** (e por **Acompanhantes**/**Histórico**); célula vazia do mapa e
    "Nova reserva" abrem o formulário direto; arrastar/mover/criar não passam pelo Resumo.
  - Barra do cartão (some o que o perfil não pode): Editar dados, Acompanhantes, Trocar de apartamento (usa `POST /mover` com seletor de
    unidades livres), Cancelar reserva (motivo; 409 se houver despesas), Imprimir ficha (A4), Histórico, Despesas (diálogo existente).
    Reserva cancelada: leitura, selo com motivo e botão Reativar.
  - Faixa "Resumo da conta" recolhível (estado por usuário em `preferencias`, campo `resumo_recolhido`).
  - Polling: o Resumo aberto pausa o redesenho automático; ele só pergunta ao servidor (8 s) se a versão mudou e mostra
    "Esta reserva mudou. Recarregar", sem apagar o que está sendo digitado. Esc fecha só o painel/subdiálogo de cima; atalhos E, D, P
    fora de campos de texto; o foco volta ao elemento de origem.
- **Fora da v1 (como na especificação):** créditos/pagamentos com valor (o azulejo Crédito mostra "Em breve"; não há "saldo a pagar"),
  anexos, dividir conta, voucher, veículo, WhatsApp, empresa/pagante, café incluso, seção por hóspede (acompanhantes são só texto),
  "Evento", adultos/crianças. O seletor de abas no celular não foi necessário: as três abas cabem em 390 px.
- **Decisões do clube que continuam pendentes:** a camareira lê a nota do apartamento? (hoje sim, saneada e sem autor); a recepção pode
  trocar de apartamento? (hoje não); prazo para corrigir nota (24 h); origem da reserva (Walk-In etc.) e empresa pagante.

## 7. Relatório de ocupação com período escolhido (impressão e PDF)

- **Onde:** botão "Imprimir relatório de ocupação" na barra do Mapa da reserva e "Relatório de ocupação" na Folha da semana. Abre o
  diálogo `#dlgOcupacao`: De/Até (padrão = período exibido: o do mapa ou a semana da folha), atalhos (Hoje, Esta semana, Este mês, Próximo
  mês, Período do mapa), papel (paisagem/retrato; começa na escolha "Papel" já usada na folha) e Imprimir / Baixar PDF / Cancelar.
  Validação na tela e no servidor: datas reais, início <= fim, anos 2020-2100, **máximo de 92 dias**.
- **O que sai:** uma página por bloco de colunas (paisagem 14 dias, retrato 7), cabeçalho (pousada, período, "Emitido em dd/mm/aaaa hh:mm por
  usuário"), grade unidade x dia com o grupo (ou nome) e nº de pessoas, linhas de totais por dia (Ocupadas, Livres, Ocupação %, Check-ins,
  Check-outs, Pessoas), resumo do período (ocupação média, noites ocupadas de N, pico, check-ins/outs, pessoas-noite) e legenda na 1ª página.
  Reserva que cruza páginas é recortada e marcada com « (veio de antes) e » (continua). A hora impressa na tela é a do navegador; a do PDF
  é a do servidor (veja o item 8 da seção 4: servidor em UTC).
- **Regras:** reserva = unidade + [entrada, saída); a coluna é a NOITE do dia; contagem por UNIDADE (24 reserváveis, a 104 é interditada e
  fica fora da conta, mesmo que haja dado legado nela); saída e entrada no mesmo dia na mesma unidade não contam em dobro; canceladas não
  entram; sobreposição antiga (conflito importado) não quebra a grade (a segunda reserva não é desenhada, a unidade conta uma vez).
- **Código:** `pousada/ocupacao.py` (cálculo e blocos; ÚNICA fonte dos números), `pousada/ocupacao_pdf.py` (reportlab, reaproveita cabeçalho e
  margens de `folha_pdf.py`), rotas em `pousada/rotas.py`, `static/ocupacao_logica.js` (puro, testado em node), `static/ocupacao.js`
  (diálogo), seção "RELATÓRIO DE OCUPAÇÃO" de `app.css` (`body.imp-ocupacao`, `ocup-retrato|paisagem`, uma `<section class="oc-pagina">` por página).
- **API:** `GET /api/ocupacao?inicio=&fim=&orientacao=` (JSON) e `GET /api/ocupacao.pdf?...` (anexo), só leitura, `@exige("reservas.ver",
  "reservas.ver_resumo")`, `Cache-Control: no-store`, 400 com mensagem para qualquer entrada inválida (nunca 500). Nome e grupo só com
  `reservas.ver`; a camareira recebe "Ocupada (n)". Nunca devolve valor de diária, pagamento, observação ou extras. Não recebe ids.
- **Autoavaliação de segurança:** IDOR (não há id no pedido; os dados são os da pousada toda, que o perfil já pode listar); injeção (datas
  validadas por `data_valida` e SQL com parâmetros); XSS (tudo do servidor passa por `ocEsc`; o PDF escapa XML; testes com nome `<img onerror>`
  na tela, no HTML impresso e no PDF); DoS (limite de 92 dias, no máximo 25 x 92 células, passo por reserva limitado ao período, parâmetros
  repetidos/gigantes recusados); CSP estrita (sem script/style inline, estilos por classe); cache proibido; os nomes não ficam no DOM depois de imprimir.
- **Testes:** `tests/test_ocupacao.py` (cálculo), `tests/test_ocupacao_api.py` (6 papéis, hostis, limites, PDF), `tests/test_ocupacao_front.py` +
  `tests/js/ocupacao_logica.js` (node), `tests/e2e/test_ocupacao_e2e.py` (porta 5091: diálogo, atalhos, validação, conteúdo, XSS, páginas e
  orientação reais via PDF de impressão do navegador, download, perfis, celular 390 px, tema escuro).
- **Decisões que continuam do clube:** incluir sábado/domingo destacados (hoje só sombreados); se a camareira deve ter acesso à tela (hoje o
  menu Mapa/Folha não aparece para ela; só a API aceita, sem nomes); impressão de períodos maiores que 92 dias (hoje não).

## 8. Hospedagem no Resumo da conta (etapa 3A): o que existe, decisões e ganchos para a 3B

- **Migração 014** (`migrations/014_hospedagem.sql`, banco v14): colunas em `reservas` (`checkin_em/por`, `conta_aberta_em/por`, `placa`), tabela
  `hospedagem_hospede` (titular + acompanhantes) e log imutável `hospedagem_evento`. Tudo nasce neutro (check-in pendente, sem placa, sem hóspedes).
- **Código:** `pousada/hospedagem.py` (regras puras: placa, hóspede, estado), `rotas_hospedes.py` (lista de hóspedes), `rotas_hospedagem.py`
  (check-in, liberar, placa, ficha, contas abertas). Front: `resumo_itens.js` (seção do hóspede), `resumo_estado.js` (ações de estado e Contas
  abertas), `resumo_hospedes.js` (painel de hóspedes), `fnrh.js` (ficha A4), mais `resumo_logica.js`/`resumo_conta.js`/`resumo_acoes.js`.
- **Barra do cartão (ordem da referência; some o que o perfil não pode):** Alterar estadia (lápis, abre o formulário existente) · Hóspedes (dois
  homens) · Transferir apartamento (duas setas, `POST /mover` com seletor de livres) · Liberar apartamento/Desfazer liberação (cama) · Ficha FNRH
  (impressora) · Registrar check-in / Reverter check-in; depois Cancelar, Resumo (impressão do resumo, antes "Imprimir ficha"), Histórico, Despesas.
  Cada ícone tem texto curto visível, `title` e `aria-label` completo; alvos de 44 px; foco visível.
- **Rotas novas** (todas JSON + CSRF; mutações levam a `versao` da reserva e a incrementam; duplo clique/versão velha = 409):
  `GET|PUT /api/reservas/<id>/hospedes`, `POST .../checkin`, `POST .../checkin/reverter`, `POST .../liberar`, `POST .../liberar/reverter`,
  `PUT .../placa`, `POST .../ficha`, `GET /api/contas-abertas`; `GET /api/despesas/resumo` ganhou `liberadas`.
- **Permissões novas** (`permissoes.py`): `hospedes.gerir`, `checkin.registrar`, `checkin.reverter`, `conta.liberar`, `ficha.imprimir`, `veiculo.editar`.
  admin e atendente: todas; **recepção: hospedes.gerir, checkin.registrar, checkin.reverter, conta.liberar, ficha.imprimir, veiculo.editar**
  (decisão do usuário: a recepção reverte check-in e libera/desfaz a liberação, **sempre com motivo obrigatório**, veja a seção 9); diretoria e consulta só veem (lista de hóspedes com documento mascarado; GET exige `reservas.ver`);
  camareira nada (não abre o Resumo).
- **Check-in explícito:** `POST /checkin` só com a hospedagem em andamento (entrada <= hoje <= saída), registra data/hora/usuário. **Os cartões
  Check-ins/Ocupados e todos os relatórios seguem contados pelas datas** (nada muda); o estado só aparece no Resumo e em `estado_hospedagem`
  (pendente, efetuado, conta aberta) em `GET /api/reservas`.
- **Reverter check-in (regra do usuário):** bloqueado (409 com mensagem clara) se houver **qualquer lançamento**. Como hoje a diária não é
  lançada, e sim informada na reserva, **"tem lançamento" = despesa ativa (não estornada) OU diária informada (> 0)**; a segunda parte é a constante
  `BLOQUEIA_REVERSAO_COM_DIARIA` em `hospedagem.py` (decisão do clube relaxar: para reverter com diária informada, mude para `False`). Para reverter é
  preciso estornar as despesas e limpar o valor da diária em Alterar estadia. Não reverte com a conta aberta (desfaça a liberação antes).
- **Liberar o apartamento e deixar a conta aberta** (`conta.liberar`): só depois que a hospedagem começou; marca `conta_aberta_em/por`, a unidade vai
  para **suja** na Governança (evento `suja`, lote `conta_aberta`) e a reserva sai da derivação da Governança (a unidade aparece vaga/livre). A conta
  (Despesas) segue acessível e a reserva entra em **Contas abertas** (indicador no Resumo, `GET /api/contas-abertas`, e `liberadas` em
  `/api/despesas/resumo`; sai da lista quando a conta for fechada na etapa 3B). Desfazer (`liberar/reverter`) volta a hospedagem à Governança, **sem** mudar a
  limpeza. **Limites conhecidos:** a reserva continua ocupando as datas no Mapa/Calendário e nas contagens por datas até a data de saída (para
  reaproveitar a unidade antes, ajuste a saída em Alterar estadia); a categoria do apartamento não existe no sistema: o título usa o andar
  ("Apartamento 201 - 2º andar"; chalés: "Chalés").
- **Hóspedes:** lista = titular (nome vem da reserva; só dados extras) + acompanhantes, no máximo o nº de pessoas (`n`); reduzir `n` abaixo do
  cadastrado dá 409 (remova os acompanhantes antes). Documento e demais campos pessoais são opcionais (veja `docs/PRIVACIDADE.md` 2.4).
- **Placa:** formato antigo (ABC-1234) ou Mercosul (ABC1D23), normalizada em maiúsculas sem hífen; editável no botão do carro (barra de itens do hóspede)
  por `veiculo.editar`; aparece na ficha.
- **Ficha de check-in FNRH:** A4 retrato (`body.imp-fnrh`, `#fnrhImpressao`), campos pedidos (nome, documento, nacionalidade, procedência, destino, data
  de nascimento, profissão, motivo da viagem, meio de transporte, placa), com linhas em branco para preencher à mão e uma ficha em branco por
  pessoa não cadastrada. Nenhum campo obrigatório legal foi inventado. **A adequação ao modelo oficial FNRH/Cadastur é decisão do clube.**
- **Seção do hóspede ("1 - NOME"):** azulejos Diária, Evento, Consumo e Crédito com caixa de seleção, lista de itens por tipo (diária; lançamentos de consumo
  não estornados) e "Total selecionado". **É só seleção visual**: Evento e Crédito aparecem desabilitados ("Em breve").
- **Ganchos para a etapa 3B:** `rc.marcados` (ids selecionados), `rcItensDaConta()` (itens por tipo), `#rcBarraItens` (só o carro; os demais ícones da
  referência ficam para a 3B), `rcConfirmar()` (painel de confirmação reutilizável para recebimento, estorno com motivo e transferência de despesas),
  `rcAbrirPainel(titulo, construir, origem, destino)` (painel no cartão ou na seção do hóspede) e a conta `despesa_conta` (fechar/quitar ainda sem rota).
- **Testes:** `tests/test_hospedagem*.py` e `tests/test_hospedes.py` (migração 013->014, matriz dos 6 papéis, concorrência, hostis, vazamento em todas as rotas GET),
  `tests/js/fnrh.js` e `tests/js/resumo_logica.js` (node), `tests/e2e/test_hospedagem_e2e.py` (porta 5112) e `test_hospedagem_visual_e2e.py` (5113: perfis, celular 390,
  tema escuro, contraste, foco, ficha A4 em PDF de 1 página).
- **Decisões do clube pendentes (3A):** diária informada impede a reversão? (hoje sim);
  prazo de guarda dos dados pessoais dos hóspedes; adequação oficial da ficha FNRH/Cadastur; se a liberação deve encurtar a estadia (hoje não);
  campos obrigatórios (hoje todos opcionais).

## 9. Motivo obrigatório ao reverter check-in, liberar e desfazer a liberação

- **Quem pode:** admin, atendente **e recepção** (`checkin.reverter`, `conta.liberar`). Diretoria, consulta e camareira não.
- **Motivo obrigatório para todos** nas três ações (`POST .../checkin/reverter`, `.../liberar`, `.../liberar/reverter`): texto limpo, com texto
  visível, 5 a 140 caracteres e sem cara de número de cartão. Ausente ou em branco = **400**; caracteres invisíveis/inversão, curto, longo ou
  cartão = 422. Na tela, o painel de confirmação traz o campo "Motivo (obrigatório)".
- **Onde fica:** `hospedagem_evento.detalhe` (log imutável) e no `historico` (`depois.motivo`) com autor, data/hora e IP; aparece na tela de
  Histórico do administrador (coluna Detalhes, "motivo: ...") e na aba Histórico da reserva (`historico.reserva`: admin e atendente). A diretoria
  (`historico.resumo`) não vê detalhes.

## 10. Pagamentos, estorno, transferência e fechamento da conta (etapa 3B)

- **Migração 015:** tabelas `pagamento`, `transferencia` e `conta_evento` (todas append-only por trigger) e a coluna
  `despesa_lancamento.transferencia_id`. Valores em centavos inteiros; data/hora e autor vêm do servidor (hora local do servidor, America/Sao_Paulo).
- **Barra de itens** (Resumo, seção do hóspede; só o que o perfil pode): placa, **Extrato** (impressora), **Receber** (cifrão), **Estornar**
  (círculo com menos), **Transferir** (duas setas), **Info** (i) e **Fechar/Reabrir conta**. Estornar e Transferir só aparecem com algo selecionado.
- **Extrato:** A4 retrato, cabeçalho da pousada, hóspede, apto, período, itens, total, "Emitido em ... por ...". Imprime **só o selecionado**
  (a diária, ou todo o consumo...); sem seleção, a conta inteira com pagamentos e saldo. Montado na hora e limpo do DOM depois.
- **Recebimento** (`POST /api/reservas/<id>/pagamentos`, `pagamentos.receber`): leva o selecionado; sem seleção o valor sugerido é o saldo na tela.
  O valor é **editável** (parcial permitido) e **não pode exceder o saldo** (decisão registrada: bloqueia com 422; o troco do dinheiro é só
  informativo, nunca vira crédito). Formas: dinheiro (valor entregue opcional e troco), Pix (referência opcional, só letras e números, até 32) e
  cartão (bandeira da lista `config.PAG_BANDEIRAS`, crédito/débito, à vista ou parcelado de 2 até `config.PAG_MAX_PARCELAS` = 12, parcela
  mínima `config.PAG_PARCELA_MIN_CENTAVOS` = R$ 5,00, código de autorização/NSU opcional de até 12 letras/números; **nunca** número, CVV ou
  validade). Parcelas: a soma é sempre o valor; as primeiras absorvem os centavos que sobram (R$ 100,01 em 3x = 33,34 + 33,34 + 33,33).
  Só recebe hospedagem ativa que já começou e com a conta aberta. No máximo 100 pagamentos por reserva.
- **Idempotência e versão:** toda mutação financeira leva `chave` (8 a 64 caracteres; a mesma chave devolve o mesmo registro, 200) e
  `conta_versao` (a `versao` de `despesa_conta`, que sobe a cada lançamento, estorno, pagamento, transferência, fechamento e reabertura;
  versão velha = 409). A gravação é serializada por `BEGIN IMMEDIATE`. Zerar a diária usa a `versao` da reserva.
- **Estorno de pagamento** (`POST /api/pagamentos/<id>/estorno`, `pagamentos.estornar`): linha negativa com motivo obrigatório; um estorno por
  pagamento (índice único), sempre do valor inteiro. **Estorno de despesa:** o mesmo `POST /api/despesas/<id>/estorno`. **Diária informada:** não há
  linha para estornar, então "estornar a diária" = **zerar a diária** (`POST /api/reservas/<id>/diaria/zerar`, `despesas.estornar` + `valores.editar`,
  com motivo): `reservas.diaria_centavos` vira 0 e o evento (com o valor zerado) fica em `conta_evento`; o histórico recebe só `diaria_zerada`
  (sem valor nem motivo). Para voltar a cobrar usa-se Alterar estadia (fica no histórico). Estornar vários itens faz uma chamada por item, pagamentos primeiro.
- **Regra de ouro:** o total da conta (diárias + despesas líquidas) nunca fica abaixo dos pagamentos líquidos; por isso estornar despesa, zerar
  ou transferir a diária, reduzir a diária/estadia (Alterar) e cancelar a reserva são **bloqueados (409)** enquanto houver pagamento a mais:
  estorne antes o pagamento. Invariante testada: pagamentos + saldo = total, com saldo >= 0. O mesmo vale para **arrastar/redimensionar no Mapa** (Mover) e, com a **conta fechada**, datas e diária ficam travadas (reabra antes);
  reserva com fechamento/reabertura/diária zerada registrados não pode ser excluída em definitivo (cancele).
- **Transferir** (`POST /api/reservas/<id>/transferir`, `despesas.transferir`; busca em `GET .../destinos?q=`): uma transação cria o cabeçalho
  em `transferencia`, um **estorno na origem** ("Transferido para #X (apto Y)") e um **lançamento igual no destino**, ambos com
  `transferencia_id`; a mesma reserva é recusada. Destino: reserva ativa em andamento (entrada <= hoje <= saída) ou liberada com conta aberta,
  de conta aberta, nunca cancelada. A **diária informada** vira **um lançamento de categoria "outros"** no destino ("Diária da reserva #N (k noites)",
  k x valor por noite; limite k <= 99 e R$ 10.000,00 por noite, senão 422) e a origem tem a diária **zerada com motivo**. Pagamentos não se transferem.
  Chave anti-duplicidade por origem.
- **Info** (`GET .../lancamentos`, `despesas.ver`): lista somente leitura e cronológica de lançamentos, estornos, transferências (saída/entrada),
  diária zerada, fechamentos/reaberturas e, com `pagamentos.ver`, os pagamentos; autor, data/hora e motivo; filtro por tipo na tela.
- **Fechar conta** (`POST .../conta/fechar`, `despesas.conta`): só com saldo zero; depois, lançar, estornar, receber, estornar pagamento e transferir
  (origem ou destino) dão 409. **Reabrir** (`.../conta/reabrir`, `conta.reabrir`: admin e atendente) exige motivo. Crédito = soma dos pagamentos líquidos.
- **Permissões novas:** `pagamentos.ver`, `pagamentos.receber`, `pagamentos.estornar`, `despesas.transferir`, `conta.reabrir`. Admin e atendente: todas;
  recepção: ver e receber (fechar conta já era `despesas.conta`); diretoria: só `pagamentos.ver`; consulta e camareira: nada.
- **Testes:** `tests/test_pagamentos*.py`, `test_transferencia.py`, `test_hospedagem_motivo.py`, `tests/js/resumo_pag_logica.js`,
  E2E `test_pagamentos_e2e.py` (porta 5121) e `test_transferencia_e2e.py` (5122).
- **Pendências do clube:** (1) **não há caixa/turno**: o dinheiro recebido não é conferido por turno nem por usuário, só registrado por pagamento
  (conta de caixa simples e fechamento de turno ficam como pendência; nada foi implementado); (2) a recepção estorna pagamento, transfere ou reabre conta?
  (hoje não); (3) conciliação com a maquineta/Pix e emissão fiscal; (4) lista de bandeiras, limite de parcelas e parcela mínima; (5) devolução quando o
  hóspede pagou a mais; (6) pagamento antecipado de hospedagem futura (hoje bloqueado); (7) categoria própria "diária" no destino (hoje "outros").

## 11. Catálogo de itens de consumo, lançamento por item e hora do lançamento (migração 016)

- **Catálogo** (tabela `catalogo_item`): categoria (Bebidas, Porções, Lavanderia, Outros), grupo opcional (ex.: "Cervejas Long Neck"),
  descrição, preço em centavos, ativo, `versao` (bloqueio otimista). Itens **nunca são apagados** (trigger): só desativados/reativados.
  Cada alteração grava uma linha em `catalogo_log` (imutável por trigger): quem, quando, IP, antes e depois. Ordem alfabética sem
  considerar acento (categoria, grupo, descrição), a mesma na tela do lançamento e na do administrador.
- **Carga inicial**: 28 itens (16 Bebidas, 12 Porções) na própria migração, com os preços do pedido. Categoria do lançamento: Bebidas = bar,
  Porções = restaurante (as 4 categorias antigas de `despesa_lancamento` continuam valendo).
- **Quem faz o quê**: `catalogo.gerir` (só administrador) cadastra/edita/desativa e vê a aba **Despesas**; quem já lança (`despesas.lancar`:
  administrador, atendente, recepção) **só escolhe item e quantidade** e vê o catálogo ativo com preços, sem editar.
  O lançamento **avulso** (descrição e valor digitados) ficou só para o administrador (marcar "Lançamento avulso" no formulário); recepção e
  atendente recebem 403. `POST /api/reservas/<id>/despesas` por item aceita só `item_id`, `item_versao`, `quantidade`, `chave`
  (qualquer campo de preço/descrição é recusado). Se o preço mudou desde que a tela abriu (versão diferente) ou o item foi desativado: 409
  e a lista é recarregada.
- **Congelamento**: descrição e preço unitário são copiados para o lançamento; mudar o preço depois não altera o histórico. Estorno,
  transferência, fechamento e a regra de ouro (total da conta nunca abaixo dos pagamentos líquidos) seguem iguais e valem para os dois tipos.
  `despesa_lancamento.item_id` é NULL nos lançamentos antigos e nos avulsos.
- **Hora exata**: `despesa_lancamento.em` (AAAA-MM-DD HH:MM:SS, `NOT NULL`, fuso America/Sao_Paulo) já existia desde a migração 012 e todos
  os lançamentos antigos TÊM hora (nenhum fica "hora desconhecida"; o "-" só aparece se o servidor não mandar a hora). A migração 016 acrescenta
  um trigger que recusa `em` vazio ou fora do formato. A hora vem sempre do servidor, nunca do cliente.
- **Só o administrador vê a hora** (`despesas.hora`): filtrada NO SERVIDOR em `GET /api/reservas/<id>/despesas`, na resposta do lançar/estornar,
  em `/api/reservas/<id>/lancamentos` (Info), no histórico geral e no da reserva (ações de despesa e transferência). Os demais perfis
  recebem apenas a data. Testes: `tests/test_despesas_hora.py` (6 perfis x rotas). O extrato A4 entregue ao hóspede **não imprime a hora**
  mesmo quando o administrador o emite (classe `.ds-hora` escondida em `body.imp-extrato`): decisão do clube se isso deve mudar.
- **Relatório de consumo** (aba Despesas, só administrador): `GET /api/relatorio/consumo?inicio=&fim=` (máx. 93 dias, 3000 linhas) com data e
  hora, apartamento, hóspede, item, quantidade, unitário, total, quem lançou e observação (estorno/transferência/avulso). Imprime em A4
  paisagem (`body.imp-consumo`), marcado como uso interno.
- **Decisões que dependem do clube**: (1) manter o avulso só para o administrador? (2) o extrato do hóspede deve mostrar a hora? (3) prazo de
  guarda da hora (câmeras costumam guardar poucos dias; o registro de despesas não é apagado); (4) itens de Lavanderia/Outros ainda não
  têm carga inicial; (5) a hora do histórico geral (`historico.em`) ainda usa o relógio do servidor por `regras.agora()` (agora também em Sao_Paulo).


## 12. Importação que atualiza e cancela (migração 017)

**Regra de ouro:** a planilha nova é a fonte da verdade. Ao ler a planilha, a prévia mostra três tipos de mudança sobre reservas que já estão no sistema; **nada é cancelado ou alterado sem o administrador ver e confirmar** (só o administrador importa).

- **Atualizações** (marcadas por padrão): linha da planilha com o mesmo apto, período sobreposto e nome igual ou parecido (sem acento, caixa e posto CEL/TEN/CAP/MAJ…). **Regra estrita, na dúvida não casa:** as mesmas palavras-chave (sem DE/DA/DOS), na mesma quantidade; só se perdoa erro de digitação de 1 caractere em palavra de 6+ letras (nunca a letra final a/o). Sufixo (JUNIOR, NETO, COSTA), prenome diferente (ANA PAULA x ANA CLARA, JOAO x JOSE SILVA) e gênero (RAFAEL x RAFAELA) não casam; nome de uma só palavra só casa se o texto inteiro, com o posto, for igual. Quando não casa, a linha vira nova reserva e a antiga aparece como "sumiu" para o administrador decidir. A prévia lista campo a campo o que muda (nome, acompanhantes, pessoas, entrada, saída, pagamento, observação, grupo). Mantém o mesmo id, soma versão, registra "alterar" no histórico (antes/depois). **Nunca** toca em diária, tipo, hóspedes, placa, pagamentos, notas nem governança. Campos de texto em branco na planilha (acompanhantes, observação, grupo) **não apagam** o que está no sistema, e "Nº de pessoas" em branco mantém o número do sistema. Sem diferença nenhuma continua "Já importada". Reimportar a mesma planilha não propõe nada (inclusive quando a mesma reserva aparece em duas abas, na virada do mês, com o nome escrito diferente). Vale também para reserva criada à mão (ela não vira "importada").
- **Cancelamentos** (seção CANCELAMENTOS de cada aba, texto livre): o parser tolera `APTO 305`, `204 E 304`, `303/304`, `203,204`, `APTOS 207/208 E CHALÉ C`, `CHALÉ E`, data na coluna A, nome + período (`24 A 26/07`, `31/07 A 03/08`, `29 A 02/08`, `29/07 A 01/08/26`) e colunas C/D/E. Linha sem unidade, com unidade inexistente ou sem nome e período vira "não identificada" (só informativa). Casamento com reserva ativa: mesmo apto + período sobreposto + nome parecido = **alta confiança** (marcada); só apto + período igual com nome diferente, ou apto + nome parecido sem período, ou reserva que também aparece na grade = **média** (desmarcada); sem casamento = "não encontrada no sistema" (informativa).
- **Sumiu da planilha** (marcada): reserva ativa de importação anterior (com lote), entrada de hoje em diante, em mês de aba escolhida **que teve reservas lidas**, que não aparece mais na grade (conservador: qualquer linha do mesmo apto com período sobreposto conta como presente). Reserva criada à mão **nunca** entra aqui. **Planilha cortada ou errada:** se sumirem pelo menos 5 reservas e mais de 30% das reservas de importação de um mês, as caixas vêm **desmarcadas** e a tela avisa.
- **Bloqueios** (aparecem na prévia, caixa desabilitada, e o servidor recusa): check-in feito, apartamento liberado com conta aberta, despesas lançadas, pagamentos registrados. Vale para cancelar e para atualizar.
- **Mesma confirmação:** os cancelamentos acontecem antes da checagem de conflito, então uma reserva nova que ocupa o apto de uma reserva cancelada entra junto (a linha fica "Aviso: depende do cancelamento" e só entra se o cancelamento estiver marcado). Ordem no servidor: cancelamentos, atualizações, reservas novas; **tudo ou nada**, com backup antes.
- **Revalidação no servidor** (409 em português): reserva existe, ainda ativa, mesma versão da prévia, sem bloqueio, "sumiu" só para reserva com lote e entrada futura, atualização só com mesmo apto, período sobreposto e nome parecido, sem conflito. Limites: 500 cancelamentos e 500 atualizações por confirmação, 500 linhas de cancelamento lidas por planilha. Motivo gravado: "Cancelada conforme planilha importada (aba X, linha N)" (sem nome de hóspede); histórico guarda só campos permitidos e o lote. Textos livres passam pelo detector de cartão (linha com cartão vira "não identificada", sem repetir o número). Na tela tudo vai por `esc()`.
- **Selo da prévia (segurança):** cada cancelamento e cada atualização proposta sai da prévia com um selo (HMAC com chave derivada da chave secreta, sobre usuário, hora, id, versão, origem, aba/linha e os dados novos; vale 2 horas e só para o usuário que leu a planilha, depois disso "refaça a prévia"). Na confirmação o servidor só aceita item com selo válido: o cliente não decide a "origem" nem os dados, então reserva criada à mão não é cancelada nem alterada por pedido forjado. Pedido inválido (tipos, limites, linha inválida, selo) é recusado **antes** da cópia de segurança, e se já existe cópia de menos de 20 segundos não se faz outra, para não empurrar as cópias boas para fora. **Cartão:** o detector também pega 13-19 dígitos soltos ou separados por espaço, `_`, `,`, `/`, bullet e hífens unicode, mas só com o mesmo separador e soma de verificação (Luhn) válida; limite: separadores mistos ou dígitos misturados a letras podem escapar. Células com mais de 2000 caracteres são cortadas; a seção CANCELAMENTOS lê no máximo 500 linhas.
- **Desfazer importação:** não apaga reserva criada pelo lote que já foi editada depois (versão > 1) ou está com check-in/conta aberta, e não reverte atualização/cancelamento de reserva que já tem check-in, conta aberta, despesa ou pagamento (a tela informa quantas ficaram). Além disso: além de remover o que o lote criou, **reativa** as canceladas e **restaura** as atualizadas (tabela `importacao_alteracao`: estado anterior + versão logo após a importação). Se alguém mexeu na reserva depois (versão mudou) ou a unidade foi ocupada, ela **não** é revertida e a tela informa quantas ficaram. Cada reversão é registrada no histórico.
- **Decisões pendentes do clube:** (1) "sumiu da planilha" marcado por padrão (hoje ignora abas sem reserva lida e desmarca quando sumiria quase um mês inteiro); (2) atualizar reservas criadas à mão pela planilha; (3) reserva com pagamento/despesa fica bloqueada: o clube quer um caminho (estornar antes) ou aviso basta?
