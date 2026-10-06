# Benchmark de capacidade da plataforma

`platform_load_probe.py` mede simultaneamente os containers de um projeto e os serviços compartilhados. O relatório compara pico observado, limite aplicado e recomendação com folga para RAM, CPU e PIDs. Também registra reinícios, OOM kills, leitura e escrita em disco, requisições e MiB por segundo, erros e latência p95 por rota.

## Perfis de carga

| Perfil | Workers HTTP por rota | Workers SQL | Linhas SQL | Linhas por resposta REST |
| --- | ---: | ---: | ---: | ---: |
| small | 1 | 2 | 20.000 | 100 |
| medium | 2 | 4 | 60.000 | 1.000 |
| large | 4 | 8 | 120.000 | 5.000 |

A carga HTTP percorre uma listagem administrativa do Auth, uma consulta REST com resposta crescente, a listagem de buckets do Storage, Edge Functions, o gateway do projeto e Studio. Ela também exercita diretamente os endpoints internos de Realtime, Analytics, Supavisor, Vector, Projects API, Key Authorizer, Postgres Meta e Imgproxy. A carga SQL com ordenação e hash roda ao mesmo tempo no banco do projeto. Cada rota recebe workers independentes, evitando que uma rota lenta reduza a pressão sobre todas as outras e garantindo progressão uniforme entre os perfis.

## Isolamento

O comando valida o label `com.docker.compose.project.working_dir` de cada container. Se qualquer container pertencer a outro diretório, o benchmark termina antes de gerar tráfego. Isso permite manter este repositório como fonte real e apontar os testes para uma instalação descartável.

Por padrão, as rotas do projeto usam os IPs internos do Docker. Esse modo evita que limites do Traefik escondam a capacidade dos serviços. Para incluir o caminho público e o Key Authorizer com chaves opacas, informe `PLATFORM_LOAD_ANON_KEY` e `PLATFORM_LOAD_SERVICE_KEY` no ambiente; as chaves não são exibidas nem gravadas no relatório.

## Execução no ambiente de teste

```bash
python3 tools/platform_load_probe.py \
  --root "/path/to/disposable-installation" \
  --project meu_projeto \
  --profile all \
  --seconds 60 \
  --repetitions 3 \
  --prepare-fixture \
  --headroom 30 \
  --max-usage 80 \
  --output /tmp/platform-load-matrix.json
```

Use `--profile small`, `medium` ou `large` para uma execução isolada. `--workers` substitui a concorrência HTTP por rota e `--db-workers` substitui a concorrência SQL. `--prepare-fixture` cria uma tabela `UNLOGGED` exclusiva no banco do projeto, concede somente leitura às roles da API e remove a tabela ao terminar, inclusive quando a carga falha. Essa opção e `--restart` devem ser usadas apenas em instalação descartável.

## Formação dos perfis de hardware

Execute cada perfil pelo menos três vezes após aquecer a plataforma. `--repetitions` agrega automaticamente o maior pico e a maior recomendação de cada serviço, além do menor throughput das rodadas. Para evitar medição ceifada, configure o projeto de teste com limites iguais ou maiores que o maior perfil antes da rodada. O pico observado representa esse cenário sintético, enquanto o valor recomendado acrescenta a folga definida por `--headroom`; nenhum dos dois substitui uma rodada com tráfego real e SLOs de latência.

O total `project_recommendation` forma a referência do projeto. A seção `services` preserva a divisão entre Nginx, Auth e REST. O total `shared_recommendation` dimensiona a base compartilhada para a intensidade testada; os valores individuais devem alimentar os baselines do calculador de capacidade. O bloco raiz `capacity_profiles` reúne `small`, `medium` e `large` em um formato estável para essa calibração.

Uma execução reprovada continua gerando o relatório e retorna código `1`. Código `2` significa erro de configuração, ambiente incorreto ou Docker indisponível.
