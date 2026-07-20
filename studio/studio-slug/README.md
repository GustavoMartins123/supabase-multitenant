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
  `/api/projects/<ref>/storage/s3-keys`.

O Dockerfile verifica o patch contra o SHA fixado antes de aplicá-lo. Se o
upstream mudar, o build falha em vez de produzir uma imagem parcialmente
compatível.
