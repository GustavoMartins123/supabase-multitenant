class SettingMeta {
  final String key;
  final String label;
  final String description;
  final EnvFieldType type;
  final String category;

  const SettingMeta({
    required this.key,
    required this.label,
    required this.description,
    required this.type,
    required this.category,
  });
}

enum EnvFieldType { toggle, number, text, select }

const kEnvSelectOptions = <String, Map<String, String>>{
  'PROJECT_RESOURCE_PROFILE': {
    'small': 'Pequeno — 256 MB / 0,5 CPU / 128 PIDs no total',
    'medium': 'Médio — 1 GB / 1,5 CPU / 384 PIDs no total',
    'large': 'Grande — 4 GB / 3 CPUs / 768 PIDs no total',
    'custom': 'Personalizado — capacidade própria abaixo',
  },
};

const kEnvIntegerRanges = {
  'JWT_EXPIRY': (min: 60, max: 3153600000),
  'GOTRUE_MAILER_OTP_EXP': (min: 60, max: 3153600000),
  'GOTRUE_PASSWORD_MIN_LENGTH': (min: 6, max: 128),
  'PGRST_DB_MAX_ROWS': (min: 1, max: 1000000000),
  'PGRST_DB_POOL': (min: 1, max: 10000),
  'PGRST_DB_POOL_TIMEOUT': (min: 1, max: 3153600000),
  'PGRST_DB_POOL_ACQUISITION_TIMEOUT': (min: 1, max: 3153600000),
  'FILE_SIZE_LIMIT': (min: 1, max: 9007199254740991),
  'VECTOR_MAX_BUCKETS': (min: 1, max: 1000000),
  'VECTOR_MAX_INDEXES': (min: 1, max: 1000000),
};

const kEnvBooleanKeys = {
  'DISABLE_SIGNUP',
  'ENABLE_EMAIL_SIGNUP',
  'ENABLE_EMAIL_AUTOCONFIRM',
  'ENABLE_ANONYMOUS_USERS',
  'ENABLE_PHONE_SIGNUP',
  'ENABLE_PHONE_AUTOCONFIRM',
  'GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED',
  'ENABLE_IMAGE_TRANSFORMATION',
  'S3_PROTOCOL_ENABLED',
  'VECTOR_BUCKETS_ENABLED',
};

const kEnvSettings = [
  SettingMeta(
    key: 'DISABLE_SIGNUP',
    label: 'Bloquear Novos Cadastros',
    description:
        'Impede novos cadastros no projeto, mesmo com provedores habilitados',
    type: EnvFieldType.toggle,
    category: 'Autenticação',
  ),
  SettingMeta(
    key: 'PROJECT_RESOURCE_PROFILE',
    label: 'Perfil de Recursos',
    description:
        'Teto de CPU/memória/PIDs do projeto, rateado entre nginx, auth e rest; '
        'aplicado ao recriar os serviços',
    type: EnvFieldType.select,
    category: 'Recursos',
  ),
  SettingMeta(
    key: 'PROJECT_MEM_LIMIT',
    label: 'Capacidade: Memória Total',
    description:
        'Ex.: 512m ou 2g. Salvar converte o projeto para o perfil '
        'Personalizado e deriva o rateio entre os serviços',
    type: EnvFieldType.text,
    category: 'Recursos',
  ),
  SettingMeta(
    key: 'PROJECT_CPUS',
    label: 'Capacidade: CPUs Totais',
    description:
        'Ex.: 1.50 ou 3.00. Mínimo efetivo de 1.85 (pisos nginx/auth/rest); '
        'o resto é rateado pelos mesmos pesos dos perfis',
    type: EnvFieldType.text,
    category: 'Recursos',
  ),
  SettingMeta(
    key: 'PROJECT_PIDS_LIMIT',
    label: 'Capacidade: PIDs por Serviço',
    description:
        'Teto de processos/threads aplicado a cada serviço do projeto '
        '(mínimos garantidos por serviço)',
    type: EnvFieldType.text,
    category: 'Recursos',
  ),
  SettingMeta(
    key: 'ENABLE_EMAIL_SIGNUP',
    label: 'Cadastro por E-mail',
    description: 'Permitir que usuários se cadastrem via e-mail',
    type: EnvFieldType.toggle,
    category: 'Autenticação',
  ),
  SettingMeta(
    key: 'ENABLE_EMAIL_AUTOCONFIRM',
    label: 'Auto-confirmar E-mail',
    description: 'Confirmar e-mail automaticamente ao cadastrar',
    type: EnvFieldType.toggle,
    category: 'Autenticação',
  ),
  SettingMeta(
    key: 'ENABLE_ANONYMOUS_USERS',
    label: 'Usuários Anônimos',
    description: 'Permitir autenticação anônima',
    type: EnvFieldType.toggle,
    category: 'Autenticação',
  ),
  SettingMeta(
    key: 'ENABLE_PHONE_SIGNUP',
    label: 'Cadastro por Telefone',
    description: 'Permitir cadastro via número de telefone',
    type: EnvFieldType.toggle,
    category: 'Autenticação',
  ),
  SettingMeta(
    key: 'ENABLE_PHONE_AUTOCONFIRM',
    label: 'Auto-confirmar Telefone',
    description: 'Confirmar telefone automaticamente ao cadastrar',
    type: EnvFieldType.toggle,
    category: 'Autenticação',
  ),
  SettingMeta(
    key: 'JWT_EXPIRY',
    label: 'Expiração do JWT (seg)',
    description: 'Tempo em segundos até o token JWT expirar',
    type: EnvFieldType.number,
    category: 'Tokens e Segurança',
  ),
  SettingMeta(
    key: 'GOTRUE_MAILER_OTP_EXP',
    label: 'Expiração OTP E-mail (seg)',
    description: 'Tempo em segundos até o link/código de e-mail expirar',
    type: EnvFieldType.number,
    category: 'Tokens e Segurança',
  ),
  SettingMeta(
    key: 'GOTRUE_PASSWORD_MIN_LENGTH',
    label: 'Tamanho mín. da senha',
    description: 'Número mínimo de caracteres para senhas',
    type: EnvFieldType.number,
    category: 'Tokens e Segurança',
  ),
  SettingMeta(
    key: 'GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED',
    label: 'Implicit Flow Externo',
    description: 'Habilitar OAuth implicit flow para provedores externos',
    type: EnvFieldType.toggle,
    category: 'Tokens e Segurança',
  ),
  SettingMeta(
    key: 'PGRST_DB_SCHEMAS',
    label: 'Schemas Expostos (PostgREST)',
    description: 'Schemas acessíveis via API REST (separados por vírgula)',
    type: EnvFieldType.text,
    category: 'Banco de Dados',
  ),
  SettingMeta(
    key: 'PGRST_DB_MAX_ROWS',
    label: 'Máx. de Linhas por Consulta',
    description: 'Limite padrão de linhas retornadas pela API REST',
    type: EnvFieldType.number,
    category: 'Banco de Dados',
  ),
  SettingMeta(
    key: 'PGRST_DB_POOL',
    label: 'Pool do PostgREST',
    description: 'Quantidade de conexões que a API REST pode manter abertas',
    type: EnvFieldType.number,
    category: 'Banco de Dados',
  ),
  SettingMeta(
    key: 'PGRST_DB_POOL_TIMEOUT',
    label: 'Timeout do Pool (seg)',
    description: 'Tempo de espera por conexão livre no pool do PostgREST',
    type: EnvFieldType.number,
    category: 'Banco de Dados',
  ),
  SettingMeta(
    key: 'PGRST_DB_POOL_ACQUISITION_TIMEOUT',
    label: 'Timeout de Aquisição (seg)',
    description: 'Tempo máximo para a API REST adquirir uma conexão do pool',
    type: EnvFieldType.number,
    category: 'Banco de Dados',
  ),
  SettingMeta(
    key: 'FILE_SIZE_LIMIT',
    label: 'Limite de Arquivo (bytes)',
    description: 'Tamanho máximo de upload em bytes',
    type: EnvFieldType.number,
    category: 'Storage',
  ),
  SettingMeta(
    key: 'ENABLE_IMAGE_TRANSFORMATION',
    label: 'Transformação de Imagens',
    description: 'Habilitar resize/otimização de imagens via Storage',
    type: EnvFieldType.toggle,
    category: 'Storage',
  ),
  SettingMeta(
    key: 'S3_PROTOCOL_ENABLED',
    label: 'Protocolo S3',
    description: 'Habilitar o endpoint S3 SigV4 deste tenant',
    type: EnvFieldType.toggle,
    category: 'Storage',
  ),
  SettingMeta(
    key: 'VECTOR_BUCKETS_ENABLED',
    label: 'Storage Vectors',
    description: 'Habilitar Vector Buckets neste tenant',
    type: EnvFieldType.toggle,
    category: 'Storage',
  ),
  SettingMeta(
    key: 'VECTOR_MAX_BUCKETS',
    label: 'Máx. de Vector Buckets',
    description: 'Quantidade máxima de Vector Buckets para o tenant',
    type: EnvFieldType.number,
    category: 'Storage',
  ),
  SettingMeta(
    key: 'VECTOR_MAX_INDEXES',
    label: 'Máx. de Índices Vetoriais',
    description: 'Quantidade máxima de índices por Vector Bucket',
    type: EnvFieldType.number,
    category: 'Storage',
  ),
];
