# Como publicar o sistema na internet (passo a passo)

Endereço final: **https://reservapousadaboaesperanca.com.br**
Servidor: VPS com **Ubuntu 24.04**. Banco SQLite em disco fixo da própria VPS.

Como funciona: o navegador fala com o **Caddy** (cuida do HTTPS e do certificado sozinho); o Caddy repassa
para o sistema (**waitress**), que escuta só dentro da VPS (127.0.0.1:5000). Nada do sistema fica exposto direto.

> Os comandos abaixo são digitados no terminal da VPS (acesso SSH). Copie e cole linha por linha.
> Onde aparecer `SEU_USUARIO`, troque pelo seu usuário de administração da VPS (nunca trabalhe como `root`).

---

## 0. Antes de tudo (no PC, uma vez)

1. **Troque a senha do administrador.** A senha atual circulou em conversa e deve ser considerada vazada.
   Veja a seção 9. Faça isso logo que o sistema estiver no ar (ou antes de copiar o banco, se preferir).
2. Compre/aponte o domínio: no painel do domínio (Registro.br), crie dois registros **A**
   (`@` e `www`) apontando para o **IP da VPS**. Espere propagar (de minutos a algumas horas).

## 1. Proteger a VPS (acesso, firewall, atualizações)

```bash
# Atualizar e instalar o que vamos usar
sudo apt update && sudo apt -y upgrade
sudo apt -y install ufw fail2ban unattended-upgrades python3-venv python3-pip sqlite3 rclone caddy

# Atualizações de segurança automáticas (responda "Sim")
sudo dpkg-reconfigure -plow unattended-upgrades

# Firewall: só SSH (22), HTTP (80) e HTTPS (443). O resto é bloqueado.
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

**SSH só por chave (sem senha).** No SEU PC, gere/enviar a chave (`ssh-keygen` e depois
`ssh-copy-id SEU_USUARIO@IP_DA_VPS`) e **teste entrar por chave numa janela nova antes de continuar**.
Só então, na VPS:

```bash
sudo tee /etc/ssh/sshd_config.d/99-endurecer.conf >/dev/null <<'EOF'
PasswordAuthentication no
PermitRootLogin no
KbdInteractiveAuthentication no
MaxAuthTries 3
EOF
sudo systemctl reload ssh
```

**fail2ban** (bloqueia quem fica errando senha do SSH):

```bash
sudo tee /etc/fail2ban/jail.d/pousada.local >/dev/null <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
[sshd]
enabled = true
EOF
sudo systemctl enable --now fail2ban
```

## 2. Instalar o sistema

```bash
# Usuário SEM privilégios que roda o sistema (sem login e sem senha)
sudo useradd --system --home /opt/pousada --shell /usr/sbin/nologin pousada

# Copie a pasta "pousada" do seu PC para a VPS (rode ESTE comando no PC, na pasta Projeto Reservas):
#   scp -r pousada SEU_USUARIO@IP_DA_VPS:/tmp/pousada
# NÃO copie: reservas.db, instance/, venv/, __pycache__ (o banco novo nasce vazio na VPS).

sudo mkdir -p /opt/pousada
sudo cp -r /tmp/pousada/. /opt/pousada/
sudo rm -rf /opt/pousada/venv /opt/pousada/instance /opt/pousada/reservas.db /opt/pousada/seed.json
sudo python3 -m venv /opt/pousada/venv
sudo /opt/pousada/venv/bin/pip install -r /opt/pousada/requirements.txt
# Código só leitura para o serviço:
sudo chown -R root:root /opt/pousada && sudo chmod -R go-w /opt/pousada
```

## 3. Configuração e chave secreta

```bash
sudo cp /opt/pousada/deploy/pousada.env.exemplo /etc/pousada.env
python3 -c "import secrets;print(secrets.token_hex(32))"      # copie o resultado
sudo nano /etc/pousada.env      # troque COLE-AQUI-A-CHAVE-GERADA pela chave; salve com Ctrl+O, saia com Ctrl+X
sudo chown root:root /etc/pousada.env && sudo chmod 600 /etc/pousada.env
```

Nunca mostre, envie por mensagem nem coloque essa chave em lugar público. Se trocar a chave, todo mundo
precisa entrar de novo (é a forma de "rotacionar": edite o arquivo e reinicie o serviço).

O sistema **se recusa a ligar** em modo servidor se faltar `TRUSTED_HOSTS`, `POUSADA_HTTPS`,
`POUSADA_PROXY` ou se a chave for fraca. Isso é proposital.

## 4. Ligar o sistema (serviço)

```bash
sudo cp /opt/pousada/deploy/pousada.service /etc/systemd/system/pousada.service
sudo systemctl daemon-reload
sudo systemctl enable --now pousada
sudo systemctl status pousada          # deve mostrar "active (running)"
sudo journalctl -u pousada -n 30       # mensagens do sistema, se algo der errado
```

Criar o primeiro administrador (senha forte, mínimo 10 caracteres; é um comando só):

```bash
sudo cp /opt/pousada/deploy/pousada-cli.sh /usr/local/sbin/pousada-cli && sudo chmod 755 /usr/local/sbin/pousada-cli
sudo pousada-cli criar-admin
```

(O comando `pousada-cli` carrega o `/etc/pousada.env` como root e roda como o usuário `pousada`. Não digite a senha
em conversas: ela é pedida no terminal, sem aparecer na tela.)

(Se preferir levar o banco atual, pare o serviço, copie `reservas.db` para `/var/lib/pousada/`, rode
`sudo chown pousada:pousada /var/lib/pousada/reservas.db && sudo chmod 600 /var/lib/pousada/reservas.db` e inicie de novo.)

## 5. HTTPS com Caddy

```bash
sudo cp /opt/pousada/deploy/Caddyfile /etc/caddy/Caddyfile
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
sudo systemctl reload caddy
sudo systemctl status caddy
```

Abra **https://reservapousadaboaesperanca.com.br** (o cadeado deve aparecer sozinho; o certificado é grátis e
renova sozinho). `www.` redireciona para o endereço sem www. Se não abrir: confira o DNS (seção 0) e as
portas 80/443 (`sudo ufw status`).

## 6. Backups (obrigatório)

O sistema já faz cópia ao ligar e a cada 6 horas em `/var/lib/pousada/backups`. Isso **não basta**: se a VPS
for perdida, as cópias vão junto. Mande cópias para fora:

```bash
sudo rclone config                       # crie um destino (ex.: "pousada-nuvem"); prefira o tipo "crypt" (cifrado)
sudo cp /opt/pousada/deploy/backup-externo.sh /usr/local/sbin/ && sudo chmod 700 /usr/local/sbin/backup-externo.sh
echo '30 3 * * * root /usr/local/sbin/backup-externo.sh' | sudo tee /etc/cron.d/pousada-backup
sudo /usr/local/sbin/backup-externo.sh   # teste agora e confira no destino
```

Contém dados pessoais de hóspedes (LGPD): mantenha o destino privado e cifrado. **Teste a restauração** de vez
em quando: `sudo systemctl stop pousada`, depois
`sudo pousada-cli restaurar /var/lib/pousada/backups/ARQUIVO.db`
e `sudo systemctl start pousada`.

Também vale tirar um "snapshot" da VPS no painel do provedor antes de mudanças grandes.

## 7. Logs (quem entrou, falhou, foi negado)

- `/var/log/pousada/seguranca.log` — logins, falhas, bloqueios, respostas 400/401/403/429. Sem senhas.
- `/var/log/pousada/acesso.log` — cada pedido (IP, método, caminho, status). Sem corpo, sem query.
- `/var/log/caddy/pousada-acesso.log` — log do Caddy.

Ver falhas de login: `sudo grep LOGIN_FALHA /var/log/pousada/seguranca.log | tail`.
(Os arquivos giram sozinhos: 5 MB x 10.) O histórico dentro do sistema (aba de administração) também registra tudo.

## 8. Atualizar o sistema depois

```bash
# copie a pasta nova para /tmp/pousada (scp), depois:
sudo systemctl stop pousada
sudo rsync -a --exclude venv --exclude instance --exclude reservas.db /tmp/pousada/ /opt/pousada/
sudo /opt/pousada/venv/bin/pip install -r /opt/pousada/requirements.txt
sudo chown -R root:root /opt/pousada && sudo chmod -R go-w /opt/pousada
sudo systemctl start pousada
```

De tempos em tempos (mensal) verifique dependências com falhas conhecidas:
`/opt/pousada/venv/bin/pip install pip-audit && /opt/pousada/venv/bin/pip-audit`.

## 9. Trocar a senha do administrador (a antiga circulou em conversa)

Não existe tela de troca de senha ainda; use um destes caminhos.

**Caminho A (mais simples, banco novo):** na seção 4 você já cria o admin com uma senha **nova e forte** que
nunca foi falada em lugar nenhum. Pronto.

**Caminho B (banco existente, admin antigo):** crie um admin novo com `app.py criar-admin` (seção 4) usando
outro login e senha novas; entre com ele. Depois desative o antigo: no navegador, logado, aperte F12,
aba "Console", cole (troque `ID_DO_ANTIGO` pelo número, que aparece em `/api/usuarios`):

```js
fetch('/api/sessao').then(r=>r.json()).then(s=>fetch('/api/usuarios/ID_DO_ANTIGO/ativo',{method:'POST',
 headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf},body:JSON.stringify({ativo:false})}))
 .then(r=>r.json()).then(console.log)
```

**Caminho C (mudar a senha do mesmo usuário):** logado como ele, no Console:

```js
fetch('/api/sessao').then(r=>r.json()).then(s=>fetch('/api/senha',{method:'POST',
 headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf},
 body:JSON.stringify({atual:'SENHA_ATUAL',nova:'NOVA_SENHA_FORTE_AQUI'})})).then(r=>r.json()).then(console.log)
```

Use gerenciador de senhas. Nunca envie senha por WhatsApp/e-mail/chat. Faça o mesmo para qualquer outro
usuário que tenha tido a senha divulgada.

---

## Checklist final de publicação

- [ ] DNS `@` e `www` apontam para a VPS
- [ ] Login na VPS só por chave SSH; `PasswordAuthentication no`; sem login de `root`
- [ ] `sudo ufw status` mostra só 22, 80, 443
- [ ] `fail2ban` ativo; `unattended-upgrades` ativo
- [ ] `/etc/pousada.env` com permissão 600 e chave secreta nova (32+ caracteres)
- [ ] `systemctl status pousada` e `caddy` ativos; site abre com cadeado; `http://` redireciona para `https://`
- [ ] Senha do administrador trocada (seção 9); sem usuários de teste
- [ ] Teste: 5 senhas erradas travam o login; usuário "camareira" não enxerga dados de hóspedes
- [ ] Backup externo diário configurado **e restauração testada**
- [ ] Conferir em https://securityheaders.com e https://www.ssllabs.com/ssltest/ (esperado: nota A)
- [ ] Porta 5000 **não** acessível de fora: `curl http://IP_DA_VPS:5000` deve falhar
- [ ] Responsável definido para atualizar a VPS e o sistema todo mês

## Variáveis de ambiente (referência)

| Variável | Para que serve |
|---|---|
| `POUSADA_PRODUCAO=1` | mesmo que `python app.py servir` (waitress + exigências de segurança) |
| `POUSADA_HTTPS=1` | cookie Secure + `__Host-`, HSTS, `upgrade-insecure-requests` |
| `POUSADA_PROXY=1` | confia em `X-Forwarded-*` do Caddy (IP, Host e esquema reais). Só ligue com proxy na frente |
| `TRUSTED_HOSTS` | domínios aceitos (obrigatório em modo servidor); outro Host recebe 400 |
| `POUSADA_SECRET_KEY` | chave de assinatura da sessão (32+ caracteres) |
| `POUSADA_LOG_DIR` | pasta dos logs de segurança e acesso (vazio = não grava) |
| `POUSADA_THREADS` | threads do waitress (padrão 8) |
| `POUSADA_PERMITIR_HTTP=1` | libera modo servidor sem HTTPS (só rede interna; nunca na internet) |
| `POUSADA_HOST` / `POUSADA_PORTA` | onde escuta (padrão 127.0.0.1:5000) |
| `POUSADA_DB`, `POUSADA_BACKUP_DIR`, `POUSADA_INSTANCIA` | onde ficam banco, backups e a pasta instance |
