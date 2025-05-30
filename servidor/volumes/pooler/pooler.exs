require Logger

# Inicia o Supavisor
{:ok, _} = Application.ensure_all_started(:supavisor)

# Obtém a versão do Postgres
version =
  case Supavisor.Repo.query!("SELECT version()") do
    %{rows: [[ver]]} ->
      case Supavisor.Helpers.parse_pg_version(ver) do
        {:ok, ver_string} -> ver_string
        _ -> raise "Não foi possível parsear a versão do Postgres"
      end
    _ ->
      raise "Não foi possível obter a versão do Postgres"
  end

# Define a lista de tenants com configurações
tenants = [
  %{
    "external_id" => "postgres",
    "db_host" => System.get_env("POSTGRES_HOST"),
    "db_port" => System.get_env("POSTGRES_PORT"),
    "db_database" => System.get_env("POSTGRES_DB"),
    "require_user" => false,
    "auth_query" => "SELECT * FROM pgbouncer.get_auth($1)",
    "default_max_clients" => System.get_env("POOLER_MAX_CLIENT_CONN") || "100",
    "default_pool_size" => System.get_env("POOLER_DEFAULT_POOL_SIZE") || "20",
    "default_parameter_status" => %{"server_version" => version},
    "ssl_config" => %{
      "ssl" => false
    },
    "users" => [
      %{
        "db_user" => "pgbouncer",
        "db_password" => System.get_env("POSTGRES_PASSWORD") || raise("POSTGRES_PASSWORD não definido"),
        "mode_type" => System.get_env("POOLER_POOL_MODE") || "transaction",
        "pool_size" => System.get_env("POOLER_DEFAULT_POOL_SIZE") || "20",
        "is_manager" => true
      }
    ]
  },
]

# Cria os tenants se não existirem
for params <- tenants do
  case Supavisor.Tenants.get_tenant_by_external_id(params["external_id"]) do
    nil ->
      Logger.info("Criando tenant #{params["external_id"]}")
      {:ok, _tenant} = Supavisor.Tenants.create_tenant(params)
    _ ->
      Logger.info("Tenant #{params["external_id"]} já existe")
      :ok
  end
end