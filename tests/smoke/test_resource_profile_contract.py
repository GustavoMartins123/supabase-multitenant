"""Contrato do perfil de recursos por projeto (criacao, edicao, protocolo)."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "servidor" / "api-internal" / "app"


class BackendResourceProfileContract(unittest.TestCase):
    def test_migration_adds_column_with_check(self) -> None:
        sql = (APP / "migrations" / "0005_project_resource_profile.sql").read_text()
        self.assertIn("ADD COLUMN resource_profile TEXT NOT NULL DEFAULT 'medium'", sql)
        self.assertIn("resource_profile IN ('small', 'medium', 'large')", sql)

    def test_schemas_accept_only_the_three_profiles(self) -> None:
        source = (APP / "schemas.py").read_text()
        self.assertIn('ResourceProfile = Literal["small", "medium", "large"]', source)
        self.assertIn("resource_profile: ResourceProfile = \"medium\"", source)

    def test_settings_whitelist_and_derived_guard(self) -> None:
        source = (APP / "project_settings.py").read_text()
        self.assertIn('"PROJECT_RESOURCE_PROFILE"', source)
        self.assertIn("DERIVED_LIMIT_KEYS", source)
        self.assertLess(
            source.index("def _normalize_settings_updates"),
            source.index("injected = set(settings.keys()) & DERIVED_LIMIT_KEYS"),
        )

    def test_main_persists_and_passes_profile_to_agent(self) -> None:
        main = (APP / "main.py").read_text()
        self.assertIn("owner_id, resource_profile)", main)
        self.assertIn('"resource_profile": resource_profile,', main)
        self.assertIn("resolve_resource_limits(updates[\"PROJECT_RESOURCE_PROFILE\"])", main)

    def test_worker_reads_the_persisted_profile(self) -> None:
        """O worker nao pode depender do corpo da requisicao.

        `_provision_and_store_keys` tambem e reentrado pela recuperacao de
        jobs (`_build_recovery_runner`), que so tem job_id/projeto/dono. Ler
        `projects.resource_profile` mantem o perfil correto no retry, em vez
        de rebaixar silenciosamente um projeto `large` para o default.
        """
        main = (APP / "main.py").read_text()
        worker = main.split("async def _provision_and_store_keys", 1)[1]
        worker = worker.split("\nasync def ", 1)[0]
        self.assertIn(
            "SELECT resource_profile FROM projects WHERE id = $1", worker
        )
        self.assertNotIn("body.", worker, "o worker nao recebe o request body")

    def test_duplicate_inherits_the_original_profile(self) -> None:
        """A copia nasce com o perfil do original, nao com o default.

        O INSERT da duplicacao le `resource_profile` do projeto de origem na
        mesma transacao, e o worker envia o valor persistido ao agent — sem
        isso um projeto `large` seria duplicado como `medium` em silencio.
        """
        main = (APP / "main.py").read_text()
        self.assertIn("SELECT $1, $1, $2, $3, resource_profile", main)
        worker = main.split("async def _duplicate_and_store_keys", 1)[1]
        worker = worker.split("\nasync def ", 1)[0]
        self.assertIn(
            "SELECT resource_profile FROM projects WHERE id = $1", worker
        )
        self.assertIn('"resource_profile": resource_profile,', worker)

    def test_telemetry_is_fail_closed_without_reader_identity(self) -> None:
        main = (APP / "main.py").read_text()
        # Sem fallback legado: startup recusa e o endpoint responde 503.
        self.assertIn('user="platform_reader"', main)
        self.assertGreaterEqual(main.count("PLATFORM_READER_DB_PASSWORD"), 2)
        self.assertNotIn("else dsn.username", main)

    def test_compose_requires_reader_password(self) -> None:
        compose = (ROOT / "servidor" / "docker-compose-api.yml").read_text()
        self.assertIn(
            "PLATFORM_READER_DB_PASSWORD: ${PLATFORM_READER_DB_PASSWORD:?defina PLATFORM_READER_DB_PASSWORD}",
            compose,
        )

    def test_profile_is_persisted_next_to_the_limits_it_derives(self) -> None:
        """A API de settings le o perfil do .env do projeto.

        Gravar so o trio derivado (MEM_LIMIT/CPUS/PIDS_LIMIT) deixa o seletor
        do Studio vazio com "Valor obrigatorio", mesmo com os limites certos
        aplicados nos containers.
        """
        helper = (
            ROOT / "servidor/generateProject/lib/resource_profiles.sh"
        ).read_text()
        self.assertIn("PROJECT_RESOURCE_PROFILE=%s", helper)
        # A chave antiga precisa ser removida antes de reescrita.
        self.assertIn(
            "^PROJECT_(RESOURCE_PROFILE|MEM_LIMIT|CPUS|PIDS_LIMIT)=", helper
        )
        settings = (APP / "project_settings.py").read_text()
        self.assertIn('"PROJECT_RESOURCE_PROFILE"', settings)

    def test_migration_keeps_the_project_own_profile(self) -> None:
        """O tool nao pode rebaixar um projeto com o default global."""
        tool = (ROOT / "tools/migrate_project_resource_limits.py").read_text()
        self.assertIn("def profile_for(", tool)
        self.assertIn("PROFILE_KEY", tool)
        # O perfil proprio do projeto vem antes do .env raiz.
        body = tool.split("def profile_for(", 1)[1].split("\ndef ", 1)[0]
        self.assertLess(body.index("project_env"), body.index("root_env"))
        self.assertIn("limits[PROFILE_KEY] = profile", tool)

    def test_tenant_reader_role_helper_is_wired(self) -> None:
        helper = (
            ROOT / "servidor" / "generateProject" / "lib" / "tenant_reader_role.sh"
        ).read_text()
        self.assertIn("provision_platform_reader()", helper)
        self.assertIn("GRANT SELECT ON auth.users, auth.sessions TO platform_reader;", helper)
        for script in (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh",
            ROOT / "servidor/generateProject/lib/duplicate_project_impl.sh",
            ROOT / "servidor/generateProject/lib/restore_project_impl.sh",
        ):
            with self.subTest(script=script.name):
                source = script.read_text()
                self.assertIn("lib/tenant_reader_role.sh", source)

    def test_secrets_never_reach_the_psql_argv(self) -> None:
        """Argumentos de processo sao visiveis em `ps` para qualquer usuario.

        O helper passava `-v reader_pwd=...` no argv — e `psql_exec_stdin` nem
        repassava argumentos extras, entao a variavel sumia e o `:'reader_pwd'`
        chegava sem substituicao ao Postgres.
        """
        helper = (
            ROOT / "servidor" / "generateProject" / "lib" / "tenant_reader_role.sh"
        ).read_text()
        self.assertNotIn("-v reader_pwd=", helper)
        self.assertIn("\\set reader_pwd", helper)
        # Um helper que engole argumentos extras esconde exatamente esse bug.
        self.assertIn('psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$db" "$@"', helper)

    def test_grant_waits_for_the_gotrue_migration(self) -> None:
        """auth.sessions so existe depois que o GoTrue do projeto migra.

        Um banco recem-criado do _supabase_template tem auth.users mas nao
        auth.sessions, entao o GRANT precisa rodar depois dos containers —
        caso contrario a criacao falha, ou o grant teria de ser alargado
        para todo o schema auth.
        """
        helper = (
            ROOT / "servidor" / "generateProject" / "lib" / "tenant_reader_role.sh"
        ).read_text()
        self.assertIn("wait_for_auth_sessions()", helper)
        self.assertIn("to_regclass('auth.sessions')", helper)
        # Least privilege preservado: nada de schema inteiro nem default privileges.
        self.assertNotIn("ALL TABLES IN SCHEMA auth", helper)
        self.assertNotIn("ALTER DEFAULT PRIVILEGES", helper)

        create = (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh"
        ).read_text()
        # Role cedo (fail-fast na senha), GRANT depois do compose up.
        self.assertIn("provision_platform_reader_role", create)
        self.assertIn("grant_platform_reader_on_tenant", create)
        self.assertLess(
            create.index("provision_platform_reader_role"),
            create.index("docker compose -p \"$PROJECT_ID\" --env-file"),
        )
        self.assertLess(
            create.index("docker compose -p \"$PROJECT_ID\" --env-file"),
            create.index("grant_platform_reader_on_tenant"),
        )


class StaleRecoveryContract(unittest.TestCase):
    """A recuperacao precisa aguentar um diretorio meio-criado."""

    def test_rollback_runs_only_in_the_main_shell(self) -> None:
        """`set -E` propaga o trap ERR a subshells.

        Uma falha dentro de `( docker compose up )` dispara o rollback no
        subshell e de novo no shell principal: o segundo tenta desfazer o que
        o primeiro ja removeu e termina em ROLLBACK_FAILED, marcando como
        residuo um projeto que foi limpo direitinho. As variaveis CREATED_*
        alteradas no subshell tambem nao voltam para o shell principal.
        """
        source = (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh"
        ).read_text()
        self.assertIn("set -Eeuo pipefail", source)
        self.assertIn('MAIN_SHELL_PID="$BASHPID"', source)
        rollback = source.split("rollback_transaction() {", 1)[1]
        rollback = rollback.split("\ntrap rollback_transaction", 1)[0]
        # Comentarios citam os comandos; comparar posicoes so no codigo.
        code = "\n".join(
            line for line in rollback.splitlines()
            if not line.lstrip().startswith("#")
        )
        guard = '[[ "$BASHPID" != "$MAIN_SHELL_PID" ]]'
        self.assertIn(guard, code)
        # O guard precisa vir antes de qualquer remocao.
        for destructive in ("docker compose", "drop_project_database", "rm -rf"):
            with self.subTest(destructive=destructive):
                self.assertLess(code.index(guard), code.index(destructive))

    def test_compose_down_is_skipped_without_env_and_compose(self) -> None:
        """Sem .env/compose nao ha stack a derrubar.

        Uma criacao que falha antes de renderizar os arquivos deixa so os
        subdiretorios (nginx/, pooler/). `docker compose down` sai com 1 por
        falta do --env-file e travaria o retry em `stale_compose`, deixando o
        nome do projeto impossivel de reutilizar.
        """
        source = (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh"
        ).read_text()
        stale = source.split("cleanup_stale_state() {", 1)[1]
        stale = stale.split("\nnormalize_public_base_url", 1)[0]
        guard = '[[ -f "$OUT_DIR/.env" && -f "$OUT_DIR/docker-compose.yml" ]]'
        self.assertIn(guard, stale)
        self.assertLess(
            stale.index(guard),
            stale.index("docker compose -p \"$PROJECT_ID\""),
        )
        # A varredura por label continua cobrindo containers orfaos.
        self.assertIn("label=com.docker.compose.project=$PROJECT_ID", stale)

class ProtocolAndAgentContract(unittest.TestCase):

    def test_protocol_validates_profiles_on_lifecycle_commands(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT / "servidor" / "host-agent"))
        from hostagent import host_agent_protocol as proto
        uuid_ok = "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa"
        base = {"tenant_uuid": uuid_ok, "recover_stale": False,
                "stale_tenant_uuids": []}
        self.assertEqual(
            proto.validate_command_args("create_project", "demo",
                                        {**base, "resource_profile": "small"}),
            [],
        )
        self.assertEqual(
            proto.validate_command_args("create_project", "demo",
                                        {**base, "resource_profile": "huge"}),
            ["invalid_resource_profile"],
        )
        self.assertEqual(
            proto.validate_command_args("duplicate_project", "novo",
                                        {"original_name": "origem",
                                         "copy_mode": "schema-only",
                                         "tenant_uuid": uuid_ok,
                                         "resource_profile": "medium"}),
            [],
        )

    def test_handlers_inject_override_env(self) -> None:
        commands = (ROOT / "servidor/host-agent/hostagent/commands.py").read_text()
        self.assertEqual(commands.count("PROJECT_RESOURCE_PROFILE_OVERRIDE"), 3)

    def test_scripts_forward_override_to_helper(self) -> None:
        for name in ("generate_project_impl.sh", "duplicate_project_impl.sh",
                     "rename_project_impl.sh"):
            path = ROOT / "servidor/generateProject/lib" / name
            with self.subTest(script=name):
                self.assertIn('${PROJECT_RESOURCE_PROFILE_OVERRIDE:-}',
                              path.read_text())


class FlutterContract(unittest.TestCase):
    def test_new_dialog_has_dropdown_and_structured_result(self) -> None:
        dialog = (ROOT / "studio/seletor_de_projetos/lib/new_project_dialog.dart"
                  ).read_text()
        self.assertIn("_resourceProfile", dialog)
        self.assertIn("DropdownButtonFormField<String>", dialog)
        self.assertIn("(name: ProjectNameValidator.normalize(_ctrl.text),", dialog)

    def test_env_section_renders_select_for_profile(self) -> None:
        section = (ROOT / "studio/seletor_de_projetos/lib/widgets/"
                   "project_settings/env_settings_section.dart").read_text()
        self.assertIn("'PROJECT_RESOURCE_PROFILE'", section)
        self.assertIn("case _FieldType.select:", section)
        self.assertIn("_kSelectOptions", section)


if __name__ == "__main__":
    unittest.main()
