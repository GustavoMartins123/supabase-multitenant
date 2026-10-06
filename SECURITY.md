# Política de segurança

Este repositório é um projeto **não oficial** que integra e adapta componentes do ecossistema Supabase para uma plataforma self-hosted multi-tenant.

A política de segurança da Supabase upstream **não é** o canal de disclosure deste repositório. Vulnerabilidades específicas deste código, dos scripts de lifecycle, do control plane, do OpenResty/Lua, do host-agent, do key-authorizer ou das integrações multi-tenant devem ser tratadas como vulnerabilidades deste projeto.

## Como reportar uma vulnerabilidade deste repositório

Prefira o mecanismo de **private vulnerability reporting** do GitHub deste repositório quando ele estiver habilitado.

Se esse mecanismo não estiver disponível, entre em contato com o mantenedor pelo perfil do GitHub para combinar um canal privado. Não publique payloads, credenciais, dumps, dados de usuários ou detalhes suficientes para exploração em uma issue pública.

Um relatório útil deve incluir, quando possível:

- branch, commit ou versão afetada;
- componente afetado;
- pré-condições necessárias;
- passos mínimos para reprodução;
- impacto observado ou potencial;
- diferença entre comportamento esperado e comportamento real;
- sugestão de mitigação, caso exista.

Não há SLA público de resposta ou recompensa financeira prometida por este repositório.

## Vulnerabilidades em componentes upstream

Se o problema estiver em um componente Supabase não modificado e for reproduzível no projeto upstream, use a política oficial de segurança do respectivo projeto Supabase.

Se a vulnerabilidade existir apenas por causa de uma adaptação, patch, configuração ou integração deste repositório, reporte-a aqui primeiro.

## Diretrizes para testes

- Teste somente infraestrutura que você possui ou para a qual tenha autorização explícita.
- Não execute scanners agressivos contra tenants, hosts ou projetos de terceiros.
- Não realize DoS, exaustão deliberada de recursos ou testes que possam comprometer disponibilidade compartilhada.
- Não acesse mais dados do que o mínimo necessário para demonstrar o problema.
- Não altere ou exclua dados reais para provar impacto.
- Não reutilize segredos encontrados durante um teste fora do escopo mínimo da reprodução.
- Redija tokens, JWTs, API keys, cookies, URLs com credenciais e dados pessoais antes de compartilhar logs ou evidências.

## Áreas sensíveis desta arquitetura

Relatórios envolvendo as seguintes fronteiras devem receber atenção especial:

- isolamento entre `project_ref`, `projects.id` e `tenant_uuid`;
- autorização de API keys opacas e comportamento fail-closed do `key-authorizer`;
- passagem de JWTs internos anon/service role pelos gateways;
- isolamento do Storage global e do namespace por tenant;
- acesso à Admin API do Storage e às redes internas de controle/data plane;
- HMAC, lease, reautorização e confinamento de comandos do `host-agent`;
- envelope encryption e transporte de segredos;
- isolamento de database, Supavisor e Realtime entre projetos;
- rewrites e compat layers do Supabase Studio/OpenResty.

## Divulgação

Evite divulgação pública antes de existir correção ou mitigação razoável, principalmente quando o problema permitir acesso entre tenants, exposição de segredos, execução no host ou bypass de autorização.

Depois da correção, o mantenedor e o pesquisador podem combinar uma divulgação responsável com escopo técnico suficiente para documentar o problema sem expor dados ou segredos reais.
