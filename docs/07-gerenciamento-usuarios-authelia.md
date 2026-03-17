# Gerenciamento de Usuários - Authelia

Este guia explica como gerenciar usuários do sistema usando o Authelia.

---

## Visão Geral

O Authelia é responsável pela autenticação de todos os usuários que acessam o Studio. Existem duas formas de gerenciar usuários:

1. **Via Interface do Studio** (recomendado) - Para admins criarem novos usuários
2. **Via Arquivo YAML** (manual) - Para configuração inicial ou troubleshooting

---

## Criando Novos Usuários

### Método 1: Via Interface do Studio (Recomendado)

Se você é um administrador do sistema, pode criar novos usuários diretamente pela interface:

1. Acesse o Studio e faça login com uma conta admin
2. Clique no botão **Admin** (canto inferior direito)
3. Na página de administração, clique em **"Novo Usuário"** ou **"Criar Usuário"**
4. Preencha os dados:
   - **Email:** Email do usuário (será usado para login)
   - **Nome de exibição:** Nome que aparecerá na interface
   - **Senha:** Senha inicial do usuário
   - **Grupos:** Selecione "admin" se for administrador, ou deixe apenas "active" para usuário comum
5. Clique em **"Criar"**

O usuário será criado automaticamente e já poderá fazer login.

### Método 2: Via Arquivo YAML (Manual)

Para criar usuários manualmente ou fazer a configuração inicial, você precisa editar o arquivo de usuários do Authelia.

#### Passo 1: Gerar Hash da Senha

Primeiro, gere o hash da senha usando argon2:

```bash
echo -n "senha_do_usuario" | argon2 $(openssl rand -base64 32) -id -t 3 -m 16 -p 4 -l 32 -e
```

Isso vai gerar uma string como:
```
$argon2id$v=19$m=65536,t=3,p=4$W4CGddhkzRo9cARHsxdoPA$ly9FEn7cp3lzPsDtCz6JqTIm9XvVpTwVoHKyV4jTjTs
```

#### Passo 2: Editar o Arquivo de Usuários

Abra o arquivo de usuários do Authelia:

```bash
nano studio/authelia/users_database.yml
```

#### Passo 3: Adicionar o Novo Usuário

Adicione a estrutura do usuário no arquivo. Exemplo para um usuário comum:

```yaml
joao:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$W4CGddhkzRo9cARHsxdoPA$ly9FEn7cp3lzPsDtCz6JqTIm9XvVpTwVoHKyV4jTjTs
  disabled: false
  extra:
    created_at: ts:2026-03-16T18:30:22Z
  given_name: ''
  address: ~
  groups:
    - active
  email: joao@example.com
  phone_extension: ''
  displayname: joao
```

**Campos importantes:**
- **joao:** Username usado para login (deve ser único)
- **password:** Hash gerado no passo 1
- **email:** Email do usuário
- **displayname:** Nome que aparece na interface
- **groups:** Lista de grupos (sempre inclua "active")
- **disabled:** `false` para ativo, `true` para desativado
- **created_at:** Data de criação (formato ISO 8601 com prefixo `ts:`)

#### Passo 4: Salvar e Aguardar

Após salvar o arquivo, **não é necessário reiniciar nenhum container**. O sistema atualiza automaticamente:

- **Authelia:** Detecta mudanças no arquivo via file watcher e recarrega automaticamente
- **Nginx:** Atualiza o cache de usuários a cada 10 segundos

O usuário estará disponível para login em até 10 segundos.

---

## Grupos e Permissões

### Tipos de Usuários

Existem dois tipos de usuários no sistema:

#### 1. Usuário Comum (Grupo: `active`)

```yaml
groups:
  - active
```

**Permissões:**
- Visualizar seus próprios projetos
- Criar novos projetos
- Duplicar seus projetos
- Gerenciar membros dos seus projetos
- Start/Stop/Restart dos seus projetos
- Não pode acessar projetos de outros usuários (exceto se for adicionado como membro)
- Não pode deletar projetos
- Não pode gerenciar usuários do sistema
- Não pode transferir projetos

#### 2. Administrador (Grupos: `active` + `admin`)

```yaml
groups:
  - active
  - admin
```

**Permissões:**
- Todas as permissões de usuário comum
- Criar e desativar usuários do sistema
- Gerenciar TODOS os projetos (de qualquer usuário)
- Parar/Iniciar/Reiniciar qualquer projeto
- Transferir projetos entre usuários
- Deletar qualquer projeto
- Acessar painel administrativo

### Exemplo de Usuário Admin

```yaml
admin_user:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$W4CGddhkzRo9cARHsxdoPA$ly9FEn7cp3lzPsDtCz6JqTIm9XvVpTwVoHKyV4jTjTs
  disabled: false
  extra:
    created_at: ts:2025-07-04T13:19:01Z
  given_name: ''
  address: ~
  groups:
    - active
    - admin
  email: admin@example.com
  phone_extension: ''
  displayname: Administrador
```

**Importante:** Para tornar um usuário admin, basta adicionar `admin` na lista de grupos. Para remover privilégios de admin, remova `admin` da lista (mantendo apenas `active`).

---

## Resetar Senha de Usuário

### Método 1: Reset Automático via Email (Recomendado)

Se você configurou SMTP no Authelia (veja seção [Configuração de SMTP](#configuração-de-smtp)), os usuários podem resetar suas próprias senhas:

1. Na tela de login do Authelia, clique em **"Esqueci minha senha"**
2. Digite o email cadastrado
3. O usuário receberá um email com link para resetar a senha
4. Clique no link e defina uma nova senha

### Método 2: Reset Manual via YAML

Se não tiver SMTP configurado ou precisar resetar manualmente:

1. Gere um novo hash de senha:
   ```bash
   echo -n "nova_senha" | argon2 $(openssl rand -base64 32) -id -t 3 -m 16 -p 4 -l 32 -e
   ```

2. Edite o arquivo de usuários:
   ```bash
   sudo nano studio/authelia/users_database.yml
   ```

3. Substitua o campo `password` do usuário pelo novo hash:
   ```yaml
   usuario:
     password: $argon2id$v=19$m=65536,t=3,p=4$NOVO_HASH_AQUI
     # ... resto dos campos
   ```

4. Salve o arquivo. O Authelia detectará a mudança automaticamente.

5. O usuário já pode fazer login com a nova senha em até 10 segundos.

---

## Desativar/Reativar Usuários

### Via Interface (Admin)

1. Acesse o painel administrativo
2. Encontre o usuário na lista
3. Clique em **"Desativar"** ou **"Ativar"**

### Via YAML

Edite o arquivo `studio/authelia/users_database.yml` e altere o campo `disabled`:

```yaml
usuario:
  disabled: true
```

Usuários desativados não conseguem fazer login, mas seus dados são preservados.

---

## Configuração de SMTP

Para habilitar reset de senha via email, configure o SMTP no arquivo `studio/authelia/configuration.yml`:

```yaml
notifier:
  smtp:
    host: smtp.gmail.com
    port: 587
    username: seu_email@gmail.com
    password: sua_senha_de_app
    sender: noreply@seudominio.com
    identifier: localhost
    subject: "[Supabase] {title}"
    startup_check_address: test@authelia.com
    disable_require_tls: false
    disable_html_emails: false
```

**Nota para Gmail:**
- Você precisa gerar uma "Senha de App" nas configurações de segurança do Google
- Não use sua senha normal do Gmail
- Ative a verificação em duas etapas primeiro

Após configurar, reinicie o Authelia:

```bash
docker restart authelia
```

---

## Estrutura Completa do Arquivo users_database.yml

Exemplo de arquivo completo com múltiplos usuários:

```yaml
# Usuário admin
admin:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$HASH_AQUI
  disabled: false
  extra:
    created_at: ts:2025-07-04T13:19:01Z
  given_name: ''
  address: ~
  groups:
    - active
    - admin
  email: admin@example.com
  phone_extension: ''
  displayname: Administrador

# Usuário comum
joao:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$HASH_AQUI
  disabled: false
  extra:
    created_at: ts:2026-03-16T18:30:22Z
  given_name: ''
  address: ~
  groups:
    - active
  email: joao@example.com
  phone_extension: ''
  displayname: João Silva

# Usuário desativado
maria:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$HASH_AQUI
  disabled: true
  extra:
    created_at: ts:2025-08-15T10:00:00Z
  given_name: ''
  address: ~
  groups:
    - active
  email: maria@example.com
  phone_extension: ''
  displayname: Maria Santos
```

---

## Troubleshooting

### Usuário não consegue fazer login

1. **Verifique se o usuário está ativo:**
   ```yaml
   disabled: false
   ```

2. **Verifique se o grupo "active" está presente:**
   ```yaml
   groups:
     - active
   ```

3. **Verifique os logs do Authelia:**
   ```bash
   docker logs authelia
   ```

4. **Teste o hash da senha:**
   ```bash
   # Gere um novo hash e substitua no arquivo
   echo -n "senha_teste" | argon2 $(openssl rand -base64 32) -id -t 3 -m 16 -p 4 -l 32 -e
   ```

### Mudanças no arquivo não são aplicadas

1. **Verifique a sintaxe YAML:**
   - Indentação deve ser com espaços (não tabs)
   - Cada nível de indentação = 2 espaços
   - Não pode ter espaços extras no final das linhas

2. **Aguarde até 10 segundos** para o Nginx atualizar o cache

3. **Verifique os logs:**
   ```bash
   docker logs authelia
   docker logs nginx
   ```

4. **Em último caso, reinicie os containers:**
   ```bash
   docker restart authelia
   docker restart nginx
   ```

### Email de reset não chega

1. **Verifique a configuração SMTP** no `configuration.yml`
2. **Verifique os logs do Authelia:**
   ```bash
   docker logs authelia | grep -i smtp
   ```
3. **Teste a conexão SMTP:**
   ```bash
   docker exec authelia cat /config/configuration.yml | grep -A 10 smtp
   ```
4. **Verifique a pasta de spam** do email

---

## Boas Práticas

### Segurança

- Use senhas fortes (mínimo 12 caracteres)
- Limite o número de admins (apenas quem realmente precisa)
- Desative usuários inativos ao invés de deletar (preserva histórico)
- Configure SMTP para permitir reset de senha
- Faça backup regular do `users_database.yml`
- Não compartilhe o arquivo `users_database.yml` (contém hashes de senha)

### Organização

- Use emails reais para facilitar comunicação
- Use displaynames descritivos

### Backup

Faça backup regular do arquivo de usuários:

```bash
cp studio/authelia/users_database.yml studio/authelia/users_database.yml.backup

cp studio/authelia/users_database.yml studio/authelia/users_database.yml.$(date +%Y%m%d)
```

---

## Referências

- [Documentação oficial do Authelia](https://www.authelia.com/docs/)
- [Argon2 Password Hashing](https://github.com/P-H-C/phc-winner-argon2)
- [YAML Syntax](https://yaml.org/spec/1.2/spec.html)
