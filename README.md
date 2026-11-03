# Sistema de Reservas — Pousada Boa Esperança

Sistema web de gestão de reservas, hospedagem e conta do hóspede para uma pousada de 25 unidades,
desenvolvido sob medida e em produção. Projeto de portfólio: **todos os dados nos testes e exemplos são fictícios**.

## Funcionalidades
- **Mapa de reservas** (linha do tempo, arrastar/mover/criar), disponibilidade e calendário do dia com listas de check-in/check-out.
- **Hospedagem**: check-in e reversão com regras, hóspedes, ficha FNRH para impressão, placa do veículo, conta aberta.
- **Conta do hóspede**: despesas, pagamentos (dinheiro, Pix, cartão com parcelas), estorno com motivo obrigatório, transferência de despesas entre apartamentos, fechamento/reabertura de conta, extrato.
- **Governança**: lista de arrumação por camareira (sem acesso a dados financeiros ou pessoais).
- **Relatórios**: ocupação por período (PDF), folha da semana.
- **Notas**, histórico imutável de alterações e perfis de acesso (administrador, atendente, recepção, camareira, diretoria, consulta).

## Stack
Python 3 · Flask · SQLite (WAL, migrações numeradas com backup automático) · HTML/CSS/JS puro (sem framework) · ReportLab · Waitress + Caddy em produção.

## Decisões de engenharia
- Valores monetários em **centavos inteiros**; "regra de ouro": o total da conta nunca fica abaixo dos pagamentos líquidos.
- Trilhas de auditoria **append-only** garantidas por triggers no banco; cancelamento lógico; estorno como lançamento negativo.
- **Bloqueio otimista** (campo `versao`) e transações `BEGIN IMMEDIATE` contra edição concorrente.
- Segurança: CSP estrita sem scripts/estilos inline, token CSRF, API somente JSON, autorização *deny-by-default* por capacidades, limitação de tentativas de login, detector de número de cartão (Luhn + normalização anti-evasão) que impede gravar PAN/CVV, varredura `varrer-cartoes`.
- Testes: ~1500 testes `pytest`, testes de lógica de front em Node e ~230 testes ponta a ponta com Playwright.

## Como rodar localmente
```bash
python -m venv venv && venv\Scripts\activate      # Windows (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
python app.py criar-admin                          # cria o administrador (não há senha padrão)
python app.py                                      # http://localhost:5000
```
Testes: `pip install -r requirements-dev.txt && python -m pytest` (E2E: `POUSADA_E2E=1 python -m pytest tests/e2e`).

Documentação em [`docs/`](docs) (requisitos, operação, privacidade/LGPD, governança) e implantação em [`deploy/`](deploy).

## Licença
[MIT](LICENSE)
