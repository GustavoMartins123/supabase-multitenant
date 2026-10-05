"""Etapas emitidas pelos executores de lifecycle."""

ProgressEvent = tuple[int, str, str]

DUPLICATE_PROGRESS_EVENTS: dict[str, ProgressEvent] = {
    "HOST_AGENT_PROGRESS=duplicate:prepare_destination": (15, "prepare_destination", "Preparando o destino da duplicação..."),
    "HOST_AGENT_PROGRESS=duplicate:pause_source": (20, "pause_source", "Pausando a origem para capturar um estado consistente..."),
    "HOST_AGENT_PROGRESS=duplicate:export_database": (25, "export_database", "Exportando o banco da origem..."),
    "HOST_AGENT_PROGRESS=duplicate:copy_storage": (35, "copy_storage", "Copiando os arquivos e metadados do Storage..."),
    "HOST_AGENT_PROGRESS=duplicate:restore_database": (40, "restore_database", "Importando o banco no clone..."),
    "HOST_AGENT_PROGRESS=duplicate:isolate_vectors": (50, "isolate_vectors", "Isolando tabelas vetoriais e removendo credenciais copiadas..."),
    "HOST_AGENT_PROGRESS=duplicate:create_empty_storage": (52, "create_empty_storage", "Criando o namespace Storage vazio do clone sem dados..."),
    "HOST_AGENT_PROGRESS=duplicate:configure_realtime": (55, "configure_realtime", "Configurando o Realtime do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:configure_pooler": (60, "configure_pooler", "Configurando o pool de conexões do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:configure_storage": (65, "configure_storage", "Registrando o tenant Storage do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:create_credentials": (70, "create_credentials", "Criando credenciais SigV4 exclusivas..."),
    "HOST_AGENT_PROGRESS=duplicate:render_files": (75, "render_files", "Gerando a configuração do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:start_services": (80, "start_services", "Construindo e iniciando os serviços do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:verify_storage": (85, "verify_storage", "Validando Storage, S3 e o gateway do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:configure_wrappers": (90, "configure_wrappers", "Recriando e verificando os wrappers vetoriais..."),
    "HOST_AGENT_PROGRESS=duplicate:configure_identity": (94, "configure_identity", "Provisionando a identidade SQL isolada do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:publish_configuration": (97, "publish_configuration", "Publicando a configuração do clone..."),
    "HOST_AGENT_PROGRESS=duplicate:infrastructure_ready": (98, "infrastructure_ready", "Infraestrutura do clone validada."),
}

ROTATE_PROGRESS_EVENTS: dict[str, ProgressEvent] = {
    "HOST_AGENT_PROGRESS=rotate:generate_tokens": (15, "generate_tokens", "Gerando os novos tokens internos..."),
    "HOST_AGENT_PROGRESS=rotate:configure_storage": (30, "configure_storage", "Atualizando as credenciais do Storage..."),
    "HOST_AGENT_PROGRESS=rotate:render_files": (50, "render_files", "Atualizando a configuração das chaves..."),
    "HOST_AGENT_PROGRESS=rotate:restart_services": (75, "restart_services", "Recriando os serviços com as novas chaves..."),
    "HOST_AGENT_PROGRESS=rotate:verify_storage": (90, "verify_storage", "Validando as novas credenciais no Storage e no gateway..."),
    "HOST_AGENT_PROGRESS=rotate:publish_configuration": (98, "publish_configuration", "Publicando a configuração atualizada..."),
}

REFERENCE_PROGRESS_EVENTS: dict[str, ProgressEvent] = {
    "HOST_AGENT_PROGRESS=reference:validate": (10, "validate_reference", "Validando a regeneração da URL pública..."),
    "HOST_AGENT_PROGRESS=reference:prepare_transaction": (20, "prepare_reference_transaction", "Preparando a transação de regeneração da URL..."),
    "HOST_AGENT_PROGRESS=reference:stop_services": (35, "stop_reference_services", "Pausando o gateway e o Auth para atualizar a URL..."),
    "HOST_AGENT_PROGRESS=reference:render_files": (50, "render_reference_files", "Gerando a configuração da nova URL..."),
    "HOST_AGENT_PROGRESS=reference:commit_reference": (65, "commit_reference", "Atualizando a referência pública do projeto..."),
    "HOST_AGENT_PROGRESS=reference:restart_services": (80, "restart_reference_services", "Reconstruindo e validando os serviços com a nova URL..."),
    "HOST_AGENT_PROGRESS=reference:publish_configuration": (95, "publish_reference_configuration", "Publicando a nova URL do projeto..."),
}

RESTORE_PROGRESS_EVENTS: dict[str, ProgressEvent] = {
    "HOST_AGENT_PROGRESS=restore:pause_services": (8, "pause_restore_services", "Pausando serviços e bloqueando o Storage para restauração..."),
    "HOST_AGENT_PROGRESS=restore:capture_safety_backup": (10, "capture_safety_backup", "Capturando o ponto de segurança antes da restauração..."),
    "HOST_AGENT_PROGRESS=restore:safety_backup_ready": (30, "safety_backup_ready", "Ponto de segurança criado; preparando a substituição do banco..."),
    "HOST_AGENT_PROGRESS=restore:replace_database": (35, "replace_database", "Preparando o banco de destino da restauração..."),
    "HOST_AGENT_PROGRESS=restore:restore_database": (40, "restore_database", "Restaurando o banco de dados..."),
    "HOST_AGENT_PROGRESS=restore:configure_database": (55, "configure_database", "Configurando permissões, Realtime e extensões do banco restaurado..."),
    "HOST_AGENT_PROGRESS=restore:restore_storage": (65, "restore_storage", "Restaurando arquivos e metadados do Storage..."),
    "HOST_AGENT_PROGRESS=restore:migrate_storage": (75, "migrate_storage", "Reconectando o Storage e aplicando suas migrations..."),
    "HOST_AGENT_PROGRESS=restore:restart_services": (80, "restart_restore_services", "Religando e validando os serviços do projeto..."),
    "HOST_AGENT_PROGRESS=restore:configure_wrappers": (88, "configure_wrappers", "Reconciliando os wrappers vetoriais restaurados..."),
    "HOST_AGENT_PROGRESS=restore:configure_identity": (92, "configure_identity", "Reaplicando a identidade SQL isolada..."),
    "HOST_AGENT_PROGRESS=restore:publish_configuration": (95, "publish_configuration", "Publicando a configuração restaurada..."),
    "HOST_AGENT_PROGRESS=restore:cleanup_transaction": (98, "cleanup_restore_transaction", "Removendo o estado anterior da transação de restauração..."),
}

DELETE_FILES_PROGRESS_EVENTS: dict[str, ProgressEvent] = {
    "HOST_AGENT_PROGRESS=delete_files:validate": (15, "validate_project_removal", "Validando a remoção dos arquivos do projeto..."),
    "HOST_AGENT_PROGRESS=delete_files:remove_configuration": (45, "remove_project_configuration", "Removendo as configurações e arquivos do projeto..."),
}

DELETE_STORAGE_PROGRESS_EVENTS: dict[str, ProgressEvent] = {
    "HOST_AGENT_PROGRESS=delete_storage:validate": (10, "validate_storage_removal", "Validando a identidade do tenant Storage..."),
    "HOST_AGENT_PROGRESS=delete_storage:remove_tenant": (25, "remove_storage_tenant", "Revogando credenciais e removendo o tenant do registry Storage..."),
    "HOST_AGENT_PROGRESS=delete_storage:remove_objects": (75, "remove_storage_objects", "Removendo os arquivos do namespace Storage..."),
    "HOST_AGENT_PROGRESS=delete_storage:verify": (95, "verify_storage_removal", "Verificando a remoção do tenant Storage..."),
}
