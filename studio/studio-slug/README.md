# Studio com contexto por aba

Esta imagem parte do Supabase Studio no commit
`20290c71bdc48bef1720bfe7d292f3b9e6154f7d` e aplica somente o patch
`studio-project-context.patch`.

O contrato do patch é intencionalmente estrito:

- `/project/<ref>` é a origem do contexto da aba;
- requisições same-origin feitas pelo cliente carregam
  `X-Studio-Project-Ref: <ref>`;
- caches que retornam dados dependentes do projeto incluem o ref na chave;
- o código não lê cookie de projeto, `Referer` nem usa `default` como projeto;
- as credenciais S3 locais são solicitadas pela rota explícita
  `/api/projects/<ref>/storage/s3-keys`;
- o upload resumable (tus) do Storage Explorer aponta para
  `/storage/v1/upload/resumable` na origem do Studio e envia
  `X-Studio-Project-Ref`, de modo que a service key permaneça no gateway.
- o assistente possui configuração de provedor, modelo e chave pessoal por projeto;
- a interface nunca recebe uma chave de provedor salva, somente o estado configurado;
- histórico e configuração usam o serviço `studio-assistant`, com identidade canônica e TLS;
- a execução de funções `[AI]` apresenta os argumentos e exige aprovação individual;
- o acesso total executa SQL não destrutivo de tabelas públicas diretamente, sem aprovação individual;
- exclusões e operações destrutivas exigem confirmação explícita separada, mesmo com acesso total;
- a execução do assistente não utiliza o botão de execução direta do editor SQL.

O Dockerfile verifica o patch contra o SHA fixado antes de aplicá-lo. Se o
upstream mudar, o build falha em vez de produzir uma imagem parcialmente
compatível.

## Distribuição

A instalação usa a imagem pronta do GHCR. `start.sh` baixa as imagens antes
de iniciar os serviços; o gateway OpenResty e o serviço do assistente são construídos localmente.
Falha no download interrompe a inicialização, sem usar uma imagem local como
substituta nem construir o Studio.

O build e a publicação são operações de manutenção, executadas na raiz do repo:

```sh
docker compose -f studio/docker-compose.maintenance.yml build studio
docker compose -f studio/docker-compose.maintenance.yml push studio
```

Publique a nova tag antes de distribuir a configuração que a utiliza.
O CI de build já usa cache do GitHub Actions; instalações não precisam desse cache.
