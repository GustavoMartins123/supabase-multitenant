# Ensaio funcional de gargalos da plataforma

`platform_bottleneck_probe.py` complementa o benchmark de capacidade com operações reais em toda a instalação. Ele não usa apenas endpoints de saúde: cria uma chave opaca descartável, atravessa os gateways, consulta bancos, abre WebSockets, movimenta objetos e mede todos os cgroups durante a mesma janela.

## Cobertura

| Cadeia | Operação sob carga |
| --- | --- |
| Postgres | consultas concorrentes com ordenação e hash, estatísticas de blocos, transações, temporários, deadlocks e conflitos |
| Supavisor | novas conexões e consultas SQL pelo pool transacional do tenant |
| Auth | criacao descartavel, login com senha e listagem administrativa pelo gateway com chave opaca |
| REST | leitura crescente de uma tabela temporária pelo gateway e por Traefik |
| Realtime | conexões WebSocket, `phx_join` e broadcast com confirmação |
| Storage | bucket temporário, upload com upsert e download autenticado |
| Imgproxy | transformação autenticada de uma imagem PNG real |
| Edge Functions | invocação da função `hello` pelo gateway |
| Key Authorizer | validação de chave opaca, gateway token e consulta ao control plane |
| Projects API | resolução interna de projeto com HMAC novo por requisição |
| Postgres Meta | listagem real das tabelas do banco do tenant |
| Analytics e Vector | ingestão Logflare explícita e pipeline natural de logs Docker/Fluentd |
| Studio, Nginx e Authelia | perfil dinâmico e cadeia HTTPS de autenticação |
| Traefik, GeoIP e deny-service | roteamento do tenant, consulta de país e resposta de bloqueio |
| Watcher do Traefik | cgroup observado durante toda a mudança de carga |

Cada perfil aumenta independentemente concorrência HTTP, conexões diretas e pelo pooler, conexões Realtime, tamanho dos objetos, dimensão das imagens, volume de Analytics e tamanho da consulta REST. O relatório registra p50, p95, p99, throughput, erros, CPU, RAM, PIDs, I/O, OOM, reinícios e saturação do host.

## Segurança e limpeza

Por padrão, a ferramenta recusa o próprio repositório-fonte. A execução exige `--allow-temporary-fixtures` e deve apontar para uma instalação descartável. Os labels de working directory dos containers são conferidos antes da primeira alteração.

As fixtures possuem nomes aleatorios e sao removidas no `finally`: usuario Auth, tabela REST, objetos, bucket, slots e chaves opacas. Um lock impede duas cargas simultaneas no mesmo projeto. A execucao seguinte recupera fixtures com os prefixos exclusivos da ferramenta caso o processo anterior seja morto sem executar o `finally`. Falha de limpeza aparece no relatorio e torna o comando reprovado. Logs gerados pela carga seguem a retencao normal do Analytics, da mesma maneira que trafego real.

Os nomes `small`, `medium` e `large` descrevem intensidades crescentes de carga, nao alteram os limites do projeto durante o teste. Para formar um perfil de hardware sem ceifar a medicao, rode a matriz em um projeto descartavel com limites acima do maior cenario e use as recomendacoes com folga. Rodar todos contra um projeto `small` e um teste de ruptura valido, mas nao mede a capacidade livre dos perfis `medium` e `large`.

## Execução curta

```bash
python3 tools/platform_bottleneck_probe.py \
  --root "/path/to/disposable-installation" \
  --project meu_projeto \
  --profile small \
  --seconds 30 \
  --allow-temporary-fixtures \
  --output /tmp/platform-bottleneck-small.json
```

## Matriz definitiva

```bash
python3 tools/platform_bottleneck_probe.py \
  --root "/path/to/disposable-installation" \
  --project meu_projeto \
  --profile all \
  --seconds 120 \
  --repetitions 3 \
  --cooldown 30 \
  --headroom 30 \
  --max-usage 80 \
  --host-max-usage 75 \
  --max-p95-ms 500 \
  --allow-temporary-fixtures \
  --output /tmp/platform-bottleneck-consensus.json
```

Uma execução com erro funcional, p95 de qualquer rota/protocolo acima de `--max-p95-ms`, OOM, reinício, troca de container, uso de container acima de `--max-usage`, CPU ou RAM do host acima de `--host-max-usage`, ou falha de limpeza retorna `1`. Se `--host-max-usage` for omitido, o limite vem de `100 - PLATFORM_RESERVE_PERCENT`. O campo `host_recommendation` informa CPUs lógicas e memória para o limite configurado. Configuração inválida retorna `2`. Nas repetições, contadores são somados, throughput usa o menor valor e latências usam o maior.
