#!/usr/bin/env python3
"""Migrate active legacy mail: shared platform defaults and project overrides.

Default: inspect and report. --apply backs up the effective static trees, imports
the current templates as published in one database transaction and rewrites the
mailer URLs. Existing Nginx configuration and custom verification pages survive.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit
import uuid

from configure_mailer_templates import project_key

FILES = {
    "confirmation": "confirmation.html",
    "invite": "invite.html",
    "magic_link": "magiclink.html",
    "recovery": "recovery.html",
    "email_change": "email_change.html",
    "reauthentication": "reauthentication.html",
}
TARGET = "/usr/share/nginx/html"
ASSET_DIRECTORY = "nginx/mailer-static-assets"
RECIPE_BEGIN = "# BEGIN IDR MAILER STATIC ASSETS"
RECIPE_END = "# END IDR MAILER STATIC ASSETS"


def read_env(path, names=None):
    result = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^(?:export\s+)?([A-Z_][A-Z_0-9]*)=(.*)$", line.strip())
        if not match or (names is not None and match[1] not in names):
            continue
        if match[1] in result:
            raise RuntimeError("Entrada de ambiente duplicada: " + match[1])
        result[match[1]] = " ".join(shlex.split(match[2], comments=True))
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compose_command(root, project):
    command = [
        "docker",
        "compose",
        "-p",
        project.name,
        "--project-directory",
        str(project),
        "--env-file",
        str(root / ".env"),
        "--env-file",
        str(project / ".env"),
        "-f",
        str(project / "docker-compose.yml"),
    ]
    # A project override can change the effective mount or template URL. Never
    # ignore it when deciding which files production is using.
    override = project / "docker-compose.override.yml"
    if override.exists():
        command += ["-f", str(override)]
    return command


def compose_document(root, project):
    result = subprocess.run(
        compose_command(root, project) + ["config", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError(
            "Compose não validou; nenhum arquivo foi alterado: " + project.name
        )
    # Rendered Compose contains secrets. Keep it in memory and never print it.
    return json.loads(result.stdout)


def snapshot_files(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("Origem estática ausente ou é um link: " + str(directory))
    result, total = {}, 0
    for base, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            path = Path(base) / name
            if path.is_symlink():
                raise RuntimeError(
                    "A origem estática contém um link; revise antes de migrar: "
                    + str(path)
                )
        for name in sorted(files):
            path = Path(base) / name
            if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise RuntimeError(
                    "Arquivo estático especial ou maior que 16 MB: " + str(path)
                )
            data = path.read_bytes()
            total += len(data)
            if len(result) >= 2000 or total > 64 * 1024 * 1024:
                raise RuntimeError("A origem estática excede o limite de migração")
            result[path.relative_to(directory).as_posix()] = data
    return result


def input_files(project):
    if (project / "nginx").is_symlink():
        raise RuntimeError("Diretório Nginx é um link; projeto preservado")
    paths = [project / name for name in (".env", "docker-compose.yml", "Dockerfile")]
    paths += [
        p
        for p in (
            project / ".dockerignore",
            project / "Dockerfile.dockerignore",
            project / "docker-compose.override.yml",
        )
        if p.exists()
    ]
    paths += sorted((project / "nginx").glob("*.conf"))
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Arquivo de projeto ausente ou inválido: " + str(path))
    return {p.relative_to(project).as_posix(): p.read_bytes() for p in paths}


def inspect_project(root, project, document):
    services = document.get("services", {})
    nginx, auth = services.get("nginx", {}), services.get("auth", {})
    mounts = [v for v in nginx.get("volumes", []) if v.get("target") == TARGET]
    if not mounts:
        return None
    if len(mounts) != 1 or mounts[0].get("type") != "bind":
        raise RuntimeError(
            "A raiz estática não tem um único bind mount reconhecido: " + project.name
        )
    source = Path(mounts[0]["source"])
    if not source.is_absolute() or source.is_symlink():
        raise RuntimeError("Origem de volume inválida")
    source = source.resolve()
    if not source.is_relative_to(root) or source in {root, project, root / "projects"}:
        raise RuntimeError(
            "Origem estática fora da instalação ou abrangente demais: " + str(source)
        )
    build = nginx.get("build", {})
    if (
        not isinstance(build, dict)
        or Path(build.get("context", "")).resolve() != project
        or build.get("dockerfile", "Dockerfile") != "Dockerfile"
    ):
        raise RuntimeError(
            "Build Nginx personalizado; a migração não vai substituí-lo automaticamente"
        )
    assets = snapshot_files(source)
    environment = auth.get("environment", {})
    configured, templates = [], {}
    for name, value in environment.items():
        if not name.startswith("GOTRUE_MAILER_TEMPLATES_") or not value:
            continue
        kind = name.removeprefix("GOTRUE_MAILER_TEMPLATES_").lower()
        if kind not in FILES:
            raise RuntimeError(
                "Tipo GoTrue não suportado; preserve a configuração: " + name
            )
        configured.append(kind)
        parsed = urlsplit(str(value))
        if parsed.hostname == "template-service":
            continue
        if parsed.hostname not in {
            nginx.get("container_name"),
            "supabase-nginx-" + project.name,
            "nginx",
        }:
            raise RuntimeError(
                "Template vem de outro servidor; origem não será inferida: " + name
            )
        relative = PurePosixPath(unquote(parsed.path).lstrip("/"))
        if (
            ".." in relative.parts
            or "\\" in str(relative)
            or str(relative) not in assets
        ):
            raise RuntimeError(
                "Template não está na raiz estática montada; confira o Nginx: " + name
            )
        data = assets[str(relative)]
        if not 0 < len(data) <= 1048576:
            raise RuntimeError(
                "Template legado vazio ou maior que 1 MB: " + str(relative)
            )
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeError:
            raise RuntimeError(
                "Template legado não é UTF-8: " + str(relative)
            ) from None
        templates[kind] = str(relative)
    if not configured:
        raise RuntimeError(
            "Compose não contém URLs de templates reconhecidas: " + project.name
        )
    return {
        "source": str(source),
        "assets": assets,
        "templates": templates,
        "configured": sorted(configured),
        "inputs": input_files(project),
    }


def checkpoint_path(root, project):
    return root / ".migration" / "mailer-prepared" / (project.name + ".json")


def fingerprint(plan, tenant):
    return {
        "format": 2,
        "tenant": tenant,
        "source": plan["source"],
        "assets": {name: digest(data) for name, data in sorted(plan["assets"].items())},
        "inputs": {name: digest(data) for name, data in sorted(plan["inputs"].items())},
        "templates": plan["templates"],
        "configured": plan["configured"],
    }


def atomic(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("Destino de migração é um link: " + str(path))
    fd, temporary = tempfile.mkstemp(prefix=".mailer-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


RPC_CODE = """
import json,os,sys,urllib.request,urllib.error
data=json.load(sys.stdin)
key=open(os.environ.get('MAILER_TEMPLATE_ADMIN_KEY_FILE','/run/secrets/mailer/ADMIN_KEY')).read().strip()
url='http://127.0.0.1:18020/internal/projects/'+data['tenant']+'/mailer-templates'+data['suffix']
body=json.dumps(data['body']).encode() if data.get('body') is not None else None
request=urllib.request.Request(url,data=body,method=data['method'],headers={
'Content-Type':'application/json','X-Mailer-Admin':key,'X-Mailer-Actor':'legacy-migration'})
try:
    with urllib.request.urlopen(request,timeout=20) as response: print(response.read().decode())
except urllib.error.HTTPError as error:
    print(json.dumps({'error':error.code}));sys.exit(1)
"""


def service_command(root):
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(root),
        "--env-file",
        str(root / ".env"),
    ]
    for name in (
        "docker-compose.yml",
        "docker-compose-api.yml",
        "docker-compose.override.yml",
    ):
        if (root / name).exists():
            command += ["-f", str(root / name)]
    return command + ["exec", "-T", "template-service"]


def run_service(root, command, payload):
    result = subprocess.run(
        service_command(root) + command,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=40,
    )
    if result.returncode:
        try:
            detail = json.loads(result.stdout).get("error")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, str):
            raise RuntimeError(detail)
        raise RuntimeError(
            "O serviço recusou a migração; confirme seu estado antes de continuar"
        )
    return json.loads(result.stdout)


def service_request(root, tenant, suffix="", method="GET", body=None):
    return run_service(
        root,
        ["python", "-c", RPC_CODE],
        {"tenant": tenant, "suffix": suffix, "method": method, "body": body},
    )


def import_legacy(root, projects):
    directory = root / "auth_template"
    assets = snapshot_files(directory) if directory.exists() else {}
    defaults = {
        kind: assets[name].decode("utf-8", errors="strict")
        for kind, name in FILES.items()
        if name in assets
    }
    payload = {"defaults": defaults, "projects": []}
    for project, tenant, plan, _ in projects:
        shared = Path(plan["source"]) == directory
        migrated = set(plan["configured"]) - set(plan["templates"])
        templates = {kind: None for kind in FILES if kind not in migrated}
        for kind, name in plan["templates"].items():
            body = plan["assets"][name].decode("utf-8", errors="strict")
            templates[kind] = None if shared and body == defaults.get(kind) else body
        payload["projects"].append(
            {"name": project.name, "tenant": tenant, "templates": templates}
        )
    return run_service(root, ["python", "legacy_migration.py"], payload)


def unmigrated_templates(plan, saved):
    rows = {row["kind"]: row for row in saved["templates"]}
    pending = []
    for kind, name in sorted(plan["templates"].items()):
        row = rows[kind]
        original = plan["assets"][name].decode("utf-8", errors="strict")
        if row["published_body"] != original or row.get("published_version", 0) <= 0:
            pending.append(kind)
    return pending


VERIFY_CODE = """
import hashlib,hmac,json,os,sys,urllib.request
data=json.load(sys.stdin)
secret=open(os.environ.get('MAILER_TEMPLATE_URL_SECRET_FILE','/run/secrets/mailer/URL_SECRET')).read().strip()
key=hmac.new(secret.encode(),('mailer-url-v1:'+data['tenant']).encode(),hashlib.sha256).hexdigest()
for kind,expected in data['templates'].items():
    url='http://127.0.0.1:18020/mailer/'+data['tenant']+'/'+kind+'?k='+key
    with urllib.request.urlopen(url,timeout=15) as response:
        if hashlib.sha256(response.read()).hexdigest()!=expected: sys.exit(1)
print('{}')
"""


def verify_runtime(root, tenant, plan):
    run_service(
        root,
        ["python", "-c", VERIFY_CODE],
        {
            "tenant": tenant,
            "templates": {
                kind: digest(plan["assets"][name])
                for kind, name in plan["templates"].items()
            },
        },
    )


def remove_static_mount(text):
    """Remove only the /usr/share/nginx/html list item in the Nginx service."""
    lines = text.splitlines(keepends=True)
    service = next(
        (i for i, line in enumerate(lines) if re.fullmatch(r"  nginx:\s*\n?", line)),
        None,
    )
    if service is None:
        return text, 0
    end = next(
        (
            i
            for i in range(service + 1, len(lines))
            if re.match(r"^(?:  [A-Za-z0-9_-]+:|\S)", lines[i])
        ),
        len(lines),
    )
    volume = next(
        (
            i
            for i in range(service + 1, end)
            if re.fullmatch(r"    volumes:\s*\n?", lines[i])
        ),
        None,
    )
    if volume is None:
        return text, 0
    volume_end = next(
        (i for i in range(volume + 1, end) if re.match(r"^    \S", lines[i])), end
    )
    items = [
        i for i in range(volume + 1, volume_end) if re.match(r"^      -\s", lines[i])
    ]
    removed, preserved = 0, []
    for offset, start in enumerate(items):
        stop = items[offset + 1] if offset + 1 < len(items) else volume_end
        item = "".join(lines[start:stop])
        short = re.search(
            r":/usr/share/nginx/html(?::(?:ro|rw))?(?:[\"']?\s*(?:#.*)?\n|[\"']?\s*$)",
            item,
        )
        long = re.search(
            r"^\s+target:\s*[\"']?/usr/share/nginx/html[\"']?\s*$", item, re.M
        )
        if short or long:
            removed += 1
        else:
            preserved += lines[start:stop]
    if not removed:
        return text, 0
    replacement = [lines[volume], *preserved] if preserved else []
    return "".join(lines[:volume] + replacement + lines[volume_end:]), removed


def render_files(project, tenant, secret, plan):
    changes = {}
    env = project / ".env"
    text = env.read_text()
    assignment = "MAILER_TEMPLATE_KEY=" + project_key(secret, tenant)
    text = (
        re.sub(r"^MAILER_TEMPLATE_KEY=.*$", assignment, text, flags=re.M)
        if re.search(r"^MAILER_TEMPLATE_KEY=", text, re.M)
        else text.rstrip() + "\n" + assignment + "\n"
    )
    changes[env] = text.encode()
    compose = project / "docker-compose.yml"
    text = compose.read_text()
    for kind in plan["configured"]:
        key = "GOTRUE_MAILER_TEMPLATES_" + kind.upper()
        assignment = f"      {key}: http://template-service:18020/mailer/${{PROJECT_UUID}}/{kind}?k=${{MAILER_TEMPLATE_KEY:?MAILER_TEMPLATE_KEY is required}}"
        text, count = re.subn(
            r"^      " + key + r":.*$", lambda _: assignment, text, flags=re.M
        )
        if count != 1:
            raise RuntimeError(
                "URL definida por override ou formato não reconhecido; arquivo preservado: "
                + key
            )
    if re.search(r"^      GOTRUE_MAILER_TEMPLATE_MAX_AGE:", text, re.M):
        text = re.sub(
            r"^      GOTRUE_MAILER_TEMPLATE_MAX_AGE:.*$",
            "      GOTRUE_MAILER_TEMPLATE_MAX_AGE: 1m",
            text,
            flags=re.M,
        )
    else:
        anchor = "GOTRUE_MAILER_TEMPLATES_" + plan["configured"][0].upper()
        text = re.sub(
            r"(^      " + anchor + r":.*$)",
            r"\1\n      GOTRUE_MAILER_TEMPLATE_MAX_AGE: 1m",
            text,
            count=1,
            flags=re.M,
        )
    text, removed = remove_static_mount(text)
    if removed != 1:
        raise RuntimeError(
            "Volume vem de override ou formato não reconhecido; Compose preservado"
        )
    changes[compose] = text.encode()
    # Copy the *whole effective mount*, including custom verification/reset
    # pages and nested JS/CSS/images. Do not substitute platform defaults.
    for name, data in plan["assets"].items():
        target = project / ASSET_DIRECTORY / name
        if any(
            parent.is_symlink()
            for parent in target.parents
            if parent.is_relative_to(project)
        ):
            raise RuntimeError("Destino de arquivos estáticos atravessa um link")
        changes[target] = data
    dockerfile = project / "Dockerfile"
    recipe = f"\n{RECIPE_BEGIN}\nCOPY {ASSET_DIRECTORY}/ {TARGET}/\n{RECIPE_END}\n"
    text = dockerfile.read_text()
    if RECIPE_BEGIN in text:
        raise RuntimeError(
            "Receita de migração já existe; confira o estado antes de ativar"
        )
    changes[dockerfile] = (text.rstrip() + "\n" + recipe).encode()
    for ignore in (project / ".dockerignore", project / "Dockerfile.dockerignore"):
        if ignore.exists():
            text = ignore.read_text()
            text += f"\n!nginx/\n!{ASSET_DIRECTORY}/\n!{ASSET_DIRECTORY}/**\n"
            changes[ignore] = text.encode()
    return {
        p: data
        for p, data in changes.items()
        if not p.exists() or p.read_bytes() != data
    }


def persist_preparation(root, project, tenant, plan):
    state = fingerprint(plan, tenant)
    path = checkpoint_path(root, project)
    if path.exists():
        existing = json.loads(path.read_text())
        if {key: existing[key] for key in state} != state:
            raise RuntimeError(
                "As origens ou configurações mudaram depois da preparação; preserve o backup e revise a migração"
            )
        return existing.get("prepared", False)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = root / ".migration" / ("mailer-prepare-" + stamp) / project.name
    backup.mkdir(parents=True, mode=0o700)
    # Parent state and backup trees are private; .env is never printed.
    os.chmod(root / ".migration", 0o700)
    for name, data in plan["inputs"].items():
        atomic(backup / "config" / name, data, 0o600)
    for name, data in plan["assets"].items():
        atomic(backup / "static" / name, data, 0o600)
    state["backup"] = str(backup.relative_to(root))
    atomic(path, json.dumps(state, sort_keys=True, indent=2).encode(), 0o600)
    return False


def activate_project(root, project, tenant, plan, document, saved, *, restart=False):
    state_path = checkpoint_path(root, project)
    if not state_path.is_file():
        raise RuntimeError("Execute primeiro a preparação com --apply: " + project.name)
    state = json.loads(state_path.read_text())
    if not state.get("prepared"):
        raise RuntimeError(
            "A preparação não terminou; conclua a importação com --apply antes de ativar"
        )
    if any(state.get(key) != value for key, value in fingerprint(plan, tenant).items()):
        raise RuntimeError(
            "Arquivos mudaram após a preparação; ativação bloqueada e configuração preservada"
        )
    pending = unmigrated_templates(plan, saved)
    if pending:
        raise RuntimeError(
            "O banco ainda não corresponde aos templates em uso; configuração preservada: "
            + ", ".join(pending)
        )
    verify_runtime(root, tenant, plan)
    secret = (root / "secrets/mailer/URL_SECRET").read_text().strip()
    changes = render_files(project, tenant, secret, plan)
    original = {
        p: (p.read_bytes(), p.stat().st_mode & 0o777) if p.exists() else None
        for p in changes
    }
    command = compose_command(root, project)
    try:
        for path, data in changes.items():
            atomic(path, data, 0o600 if path.name == ".env" else 0o644)
        rendered = compose_document(root, project)
        if any(
            v.get("target") == TARGET
            for v in rendered["services"]["nginx"].get("volumes", [])
        ):
            raise RuntimeError("Um override ainda monta a raiz estática")
        for kind in plan["configured"]:
            value = rendered["services"]["auth"]["environment"].get(
                "GOTRUE_MAILER_TEMPLATES_" + kind.upper(), ""
            )
            parsed = urlsplit(value)
            if (
                parsed.hostname != "template-service"
                or parsed.path != f"/mailer/{tenant}/{kind}"
            ):
                raise RuntimeError("Um override substitui a URL de template")
        # Catch source edits made while validation was running.
        if {
            name: digest(data)
            for name, data in snapshot_files(Path(plan["source"])).items()
        } != state["assets"]:
            raise RuntimeError("Origem estática mudou durante a ativação")
    except BaseException:
        for path, previous in original.items():
            if previous:
                atomic(path, *previous)
            else:
                path.unlink(missing_ok=True)
        raise RuntimeError(
            "Ativação não validou; arquivos anteriores restaurados e containers não recriados"
        ) from None
    state["activated"] = True
    atomic(state_path, json.dumps(state, sort_keys=True, indent=2).encode(), 0o600)
    print(
        project.name
        + ": configuração ativada; Nginx preservado, pasta original mantida. Backup: "
        + state["backup"]
    )
    if restart:
        subprocess.run(
            command + ["up", "--build", "-d", "--no-deps", "nginx", "auth"],
            check=True,
            timeout=600,
        )
    else:
        print(
            project.name
            + ": recrie nginx e auth após revisar os arquivos; os containers atuais continuam intactos"
        )


def migrate(root, *, apply=False, restart=False, only=None):
    root = Path(root).resolve()
    if only and not re.fullmatch(r"[a-z_][a-z0-9_]{2,39}", only):
        raise RuntimeError("Projeto inválido")
    projects = (
        [root / "projects" / only] if only else sorted((root / "projects").iterdir())
    )
    planned = []
    for project in projects:
        if not project.is_dir():
            if only:
                raise RuntimeError("Projeto não encontrado: " + project.name)
            continue
        if (
            not re.fullmatch(r"[a-z_][a-z0-9_]{2,39}", project.name)
            or project.is_symlink()
        ):
            if only:
                raise RuntimeError("Projeto inválido")
            continue
        tenant = str(
            uuid.UUID(read_env(project / ".env", {"PROJECT_UUID"})["PROJECT_UUID"])
        )
        document = compose_document(root, project)
        plan = inspect_project(root, project, document)
        if plan is None:
            print(
                project.name + ": sem bind mount de templates; nenhum arquivo alterado"
            )
            continue
        print(project.name + ": origem efetiva " + plan["source"])
        print(
            project.name
            + ": "
            + str(len(plan["assets"]))
            + " arquivo(s) preservados; e-mails: "
            + ", ".join(plan["templates"])
        )
        if not apply:
            print(
                project.name
                + ": simulação; Compose, Nginx e containers permanecem intactos"
            )
            continue
        persist_preparation(root, project, tenant, plan)
        planned.append((project, tenant, plan, document))
    if not planned:
        return
    result = import_legacy(root, planned)
    print(
        f"Legado registrado como ativo: {result['imported']} template(s), {result['projects']} projeto(s); padrões compartilhados e personalizações preservados"
    )
    for project, tenant, plan, document in planned:
        state_path = checkpoint_path(root, project)
        state = json.loads(state_path.read_text())
        state["prepared"] = True
        atomic(state_path, json.dumps(state, sort_keys=True, indent=2).encode(), 0o600)
        saved = service_request(root, tenant)
        activate_project(root, project, tenant, plan, document, saved, restart=restart)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--project")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="importar o legado como ativo e atualizar a configuração",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="recriar somente nginx/auth após ativação validada",
    )
    args = parser.parse_args()
    if args.restart and not args.apply:
        parser.error("--restart exige --apply")
    try:
        migrate(
            args.server_root, apply=args.apply, restart=args.restart, only=args.project
        )
    except (RuntimeError, KeyError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
