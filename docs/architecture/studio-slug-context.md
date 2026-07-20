# Contexto do Supabase Studio por aba

## Objetivo

Cada aba mantém seu projeto exclusivamente pela URL:

```text
/project/<project_ref>/...
```

Não existe projeto selecionado globalmente no navegador. Cookie, `Referer`,
local storage e o literal `default` não participam da resolução.

## Contrato

1. O seletor Flutter abre `/project/<ref>`.
2. O Nginx aceita a página somente quando `<ref>` segue
   `[a-z_][a-z0-9_]{2,39}`.
3. O Studio lê o ref da URL atual e inclui
   `X-Studio-Project-Ref: <ref>` em toda requisição same-origin feita por seu
   transporte HTTP.
4. O gateway resolve o contexto uma única vez, usando o path original
   (`request_uri`) e/ou o header explícito.
5. Quando path e header coexistem, eles precisam ser idênticos. Divergência
   retorna `409 project_ref_mismatch`.
6. O ref capturado fica em `ngx.ctx.studio_request_project_ref`. Rewrites e o
   access gate usam esse mesmo valor; não há segunda resolução.
7. Antes de obter qualquer service role, o gateway consulta o control plane e
   valida o usuário e o membership do projeto.

```text
aba /project/alpha
        |
        +-- pagina: path alpha --------------------+
        |                                          |
        +-- APIs: X-Studio-Project-Ref: alpha -----+--> captura única
                                                       |
                                                       +--> membership
                                                       +--> contexto alpha
                                                       +--> proxy alpha
```

## Fontes aceitas

| Requisição | Fonte obrigatória |
| --- | --- |
| Página `/project/<ref>` | Segmento `<ref>` do path |
| API com ref no path | Ref do path; header, se enviado, deve coincidir |
| API sem ref no path, como profile e lista self-hosted | `X-Studio-Project-Ref` |
| AI | Header explícito e `projectRef` do body, ambos iguais |
| Credenciais S3 locais | Path `/api/projects/<ref>/storage/s3-keys` |

Ausência de contexto falha fechada. Não há fallback.

## Estado no front-end

O patch do Studio também inclui o ref nas chaves de cache cujo payload depende
do projeto:

- profile self-hosted;
- lista self-hosted de projetos;
- credenciais S3 locais.

Assim, uma navegação ou restauração de aba não reutiliza dados de outro ref.

## Build reproduzível

O código upstream não é copiado para este repositório. A imagem em
`studio/studio-slug/Dockerfile` busca o commit exato
`20290c71bdc48bef1720bfe7d292f3b9e6154f7d`, valida
`studio-project-context.patch` com `git apply --check` e só então compila o
Studio seguindo as etapas do Dockerfile oficial.

Uma atualização do Studio exige deliberadamente:

1. alterar o SHA;
2. reaplicar e revisar o patch;
3. validar build e fluxos por projeto;
4. atualizar os contratos smoke.

## Invariantes de segurança

- `X-Studio-Project-Ref` identifica o contexto solicitado, mas não concede
  acesso;
- o control plane continua sendo a autoridade de membership;
- service role nunca é devolvida ao navegador;
- o header externo é removido após a captura e substituído internamente por
  `X-Project-Ref` validado;
- endpoints sem ref explícito não podem escolher um projeto por estado global.
