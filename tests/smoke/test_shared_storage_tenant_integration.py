"""Smoke ativo de isolamento do Storage compartilhado.

Esta suite e opt-in porque cria e remove projetos e interrompe brevemente o
Storage global. Ela deve rodar somente em uma instalacao descartavel dedicada.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import shlex
import subprocess
import tarfile
import time
import unittest
import urllib.error
import urllib.parse

from tests.smoke.common import (
    build_step_up_token,
    env_flag,
    request,
    wait_for_job,
)


ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read_env(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in values:
            raise AssertionError(f"duplicate environment key in {path}: {key}")
        values[key] = value
    return values


def _sigv4_headers(
    url: str,
    access_key: str,
    secret_key: str,
    *,
    service: str,
    body: bytes = b"",
) -> dict[str, str]:
    parsed = urllib.parse.urlsplit(url)
    now = dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = amz_date[:8]
    region = "us-east-1"
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_uri = urllib.parse.quote(parsed.path or "/", safe="/-_.~")
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    canonical_query = urllib.parse.urlencode(
        sorted(query_items),
        doseq=True,
        quote_via=urllib.parse.quote,
        safe="-_.~",
    )
    canonical_headers = (
        f"host:{parsed.netloc}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        [
            "GET" if not body else "POST",
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    scope = f"{short_date}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    def sign(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode(), hashlib.sha256).digest()

    date_key = sign(f"AWS4{secret_key}".encode(), short_date)
    region_key = sign(date_key, region)
    service_key = sign(region_key, service)
    signing_key = sign(service_key, "aws4_request")
    signature = hmac.new(
        signing_key,
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Host": parsed.netloc,
        "X-Amz-Content-Sha256": payload_hash,
        "X-Amz-Date": amz_date,
        "Authorization": (
            "AWS4-HMAC-SHA256 "
            f"Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


@unittest.skipUnless(
    env_flag("RUN_SHARED_STORAGE_SMOKE"),
    "set RUN_SHARED_STORAGE_SMOKE=1 on a disposable dedicated installation",
)
class SharedStorageTenantIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api_url = os.environ["SMOKE_API_URL"].rstrip("/")
        cls.public_base = os.environ["SMOKE_PUBLIC_BASE_URL"].rstrip("/")
        cls.server_root = pathlib.Path(
            os.getenv("SMOKE_SERVER_ROOT", str(ROOT / "servidor"))
        ).resolve()
        cls.headers = {
            "X-Shared-Token": os.environ["SMOKE_SHARED_TOKEN"],
            "X-User-Token": os.environ["SMOKE_USER_TOKEN"],
        }
        cls.hmac_secret = os.environ["SMOKE_NGINX_HMAC_SECRET"]
        suffix = f"{int(time.time()) % 1_000_000:06d}"
        cls.project_a = f"storagea_{suffix}"
        cls.project_b = f"storageb_{suffix}"
        cls.clone_data = f"storagec_{suffix}"
        cls.clone_schema = f"storaged_{suffix}"
        cls.renamed_a = f"storagee_{suffix}"
        cls.created_projects: set[str] = set()
        cls.storage_was_stopped = False

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.storage_was_stopped:
            subprocess.run(
                ["docker", "start", "supabase-storage-global"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        for project in sorted(cls.created_projects, reverse=True):
            try:
                cls._delete_project(project)
            except Exception:
                # unittest apresenta a falha original; o nome do projeto fica
                # deliberadamente previsivel para limpeza operacional.
                pass

    @classmethod
    def _step_up_headers(
        cls,
        project: str,
        *,
        action: str,
        resource: str,
    ) -> dict[str, str]:
        return {
            **cls.headers,
            "X-Step-Up-Token": build_step_up_token(
                cls.hmac_secret,
                cls.headers["X-User-Token"],
                action=action,
                project=project,
                resource=resource,
            ),
        }

    @classmethod
    def _delete_project(cls, project: str) -> None:
        status, body = request(
            "DELETE",
            f"{cls.api_url}/api/projects/{project}",
            headers=cls._step_up_headers(
                project,
                action="delete_project",
                resource=project,
            ),
        )
        if status == 404:
            cls.created_projects.discard(project)
            return
        if status != 202 or not isinstance(body, dict):
            raise AssertionError(f"delete {project}: HTTP {status}: {body}")
        wait_for_job(cls.api_url, body["job_id"], cls.headers)
        cls.created_projects.discard(project)

    def _create_project(self, project: str) -> None:
        status, body = request(
            "POST",
            f"{self.api_url}/api/projects",
            headers=self.headers,
            payload={"name": project},
        )
        self.assertEqual(status, 202, body)
        self.assertIsInstance(body, dict)
        self.created_projects.add(project)
        wait_for_job(self.api_url, body["job_id"], self.headers)

    def _duplicate_project(self, source: str, target: str, *, with_data: bool) -> None:
        status, body = request(
            "POST",
            f"{self.api_url}/api/projects/duplicate",
            headers=self.headers,
            payload={
                "original_name": source,
                "new_name": target,
                "copy_data": with_data,
            },
        )
        self.assertEqual(status, 202, body)
        self.assertIsInstance(body, dict)
        self.created_projects.add(target)
        wait_for_job(self.api_url, body["job_id"], self.headers)

    def _claim_keys(self, project: str) -> dict[str, str]:
        status, body = request(
            "GET",
            f"{self.api_url}/api/projects/{project}/api-key-reveals",
            headers=self.headers,
        )
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        reveals = body.get("reveals")
        self.assertIsInstance(reveals, list)
        claimed: dict[str, str] = {}
        for reveal in reveals:
            kind = reveal["kind"]
            key_id = reveal["key_id"]
            claim_headers = self.headers
            if kind == "secret":
                claim_headers = self._step_up_headers(
                    project,
                    action="reveal_secret_key",
                    resource=key_id,
                )
            claim_status, claim_body = request(
                "POST",
                f"{self.api_url}/api/projects/{project}/api-key-reveals/{key_id}/claim",
                headers=claim_headers,
            )
            self.assertEqual(claim_status, 200, claim_body)
            claimed[kind] = claim_body["api_key"]
        self.assertEqual(set(claimed), {"publishable", "secret"})
        return claimed

    def _storage_url(self, project: str, path: str) -> str:
        return f"{self.public_base}/{project}/storage/v1/{path.lstrip('/')}"

    @staticmethod
    def _key_headers(key: str, **extra: str) -> dict[str, str]:
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            **extra,
        }

    def _create_bucket(self, project: str, key: str, bucket: str) -> None:
        status, body = request(
            "POST",
            self._storage_url(project, "bucket"),
            headers=self._key_headers(key),
            payload={"id": bucket, "name": bucket, "public": False},
        )
        self.assertIn(status, {200, 201}, body)

    def _upload(
        self,
        project: str,
        key: str,
        bucket: str,
        object_name: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
        forwarded_host: str | None = None,
        upsert: bool = False,
    ) -> tuple[int, object]:
        extra = {"Content-Type": content_type}
        if forwarded_host:
            extra["X-Forwarded-Host"] = forwarded_host
            extra["X-Tenant-Id"] = forwarded_host
        if upsert:
            extra["x-upsert"] = "true"
        return request(
            "POST",
            self._storage_url(
                project,
                f"object/{bucket}/{urllib.parse.quote(object_name, safe='/')}",
            ),
            headers=self._key_headers(key, **extra),
            raw_body=content,
        )

    def _read_object(
        self,
        project: str,
        key: str,
        bucket: str,
        object_name: str,
        *,
        forwarded_host: str | None = None,
    ) -> tuple[int, object]:
        extra: dict[str, str] = {}
        if forwarded_host:
            extra["X-Forwarded-Host"] = forwarded_host
            extra["X-Tenant-Id"] = forwarded_host
        return request(
            "GET",
            self._storage_url(
                project,
                f"object/authenticated/{bucket}/{urllib.parse.quote(object_name, safe='/')}",
            ),
            headers=self._key_headers(key, **extra),
        )

    def _list_buckets(self, project: str, key: str) -> tuple[int, object]:
        return request(
            "GET",
            self._storage_url(project, "bucket"),
            headers=self._key_headers(key),
        )

    def _s3_request(
        self,
        project: str,
        access_key: str,
        secret_key: str,
    ) -> tuple[int, object]:
        url = self._storage_url(project, "s3")
        return request(
            "GET",
            url,
            headers=_sigv4_headers(
                url,
                access_key,
                secret_key,
                service="s3",
            ),
        )

    def _s3_credentials(self, project: str) -> dict[str, str]:
        status, body = request(
            "GET",
            f"{self.api_url}/api/projects/{project}/storage/s3-keys",
            headers=self.headers,
        )
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        return {
            "access_key": body["accessKey"],
            "secret_key": body["secretKey"],
        }

    def _update_file_limit(self, project: str, value: int) -> None:
        status, body = request(
            "PUT",
            f"{self.api_url}/api/projects/{project}/settings",
            headers=self.headers,
            payload={"settings": {"FILE_SIZE_LIMIT": str(value)}},
        )
        self.assertEqual(status, 200, body)
        services = body["affected_services"]
        status, job = request(
            "POST",
            f"{self.api_url}/api/projects/{project}/recreate-services",
            headers=self.headers,
            payload={"services": services},
        )
        self.assertEqual(status, 202, job)
        wait_for_job(self.api_url, job["job_id"], self.headers)

    def _bash(self, script: str, *, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
        outcome = subprocess.run(
            ["bash", "-lc", script],
            cwd=self.server_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1200,
            check=False,
        )
        if expect_success and outcome.returncode != 0:
            self.fail(f"bash probe failed ({outcome.returncode}): {outcome.stderr[-1000:]}")
        if not expect_success and outcome.returncode == 0:
            self.fail("negative isolation probe unexpectedly succeeded")
        return outcome

    def _vector_probe(
        self,
        credential_project: str,
        tenant_uuid: str,
        operation: str,
        body: dict[str, object],
        *,
        expect_success: bool,
    ) -> None:
        root = shlex.quote(str(self.server_root))
        project = shlex.quote(credential_project)
        tenant = shlex.quote(tenant_uuid)
        operation_arg = shlex.quote(operation)
        body_arg = shlex.quote(json.dumps(body, separators=(",", ":")))
        script = f"""
set -Eeuo pipefail
set -a
source {root}/.env
source {root}/projects/{project}/.env
set +a
source {root}/generateProject/lib/vector_lifecycle.sh
storage_sigv4_probe {tenant} "$S3_PROTOCOL_ACCESS_KEY_ID" \
  "$S3_PROTOCOL_ACCESS_KEY_SECRET" s3vectors POST \
  /vector/{operation_arg} {body_arg}
"""
        self._bash(script, expect_success=expect_success)

    def _wait_storage(self) -> None:
        root = shlex.quote(str(self.server_root))
        self._bash(
            f"source {root}/generateProject/lib/storage_multitenant.sh; storage_wait_global 60"
        )

    def test_shared_storage_full_tenant_matrix(self) -> None:
        # 1-2: dois projetos independentes.
        self._create_project(self.project_a)
        self._create_project(self.project_b)
        keys_a = self._claim_keys(self.project_a)
        keys_b = self._claim_keys(self.project_b)
        env_a = _read_env(self.server_root / "projects" / self.project_a / ".env")
        env_b = _read_env(self.server_root / "projects" / self.project_b / ".env")
        tenant_a = env_a["PROJECT_UUID"]
        tenant_b = env_b["PROJECT_UUID"]
        self.assertNotEqual(tenant_a, tenant_b)

        # 3-8, 17-18 e 26: objetos, nomes iguais, isolamento e header hostil.
        bucket = "shared-private"
        object_a = b"tenant-a-original"
        object_b = b"tenant-b-original"
        self._create_bucket(self.project_a, keys_a["secret"], bucket)
        self._create_bucket(self.project_b, keys_b["secret"], bucket)
        self.assertIn(
            self._upload(self.project_a, keys_a["secret"], bucket, "a.txt", object_a)[0],
            {200, 201},
        )
        self.assertIn(
            self._upload(self.project_b, keys_b["secret"], bucket, "b.txt", object_b)[0],
            {200, 201},
        )
        self.assertEqual(self._read_object(self.project_a, keys_a["secret"], bucket, "a.txt"), (200, object_a.decode()))
        self.assertEqual(self._read_object(self.project_b, keys_b["secret"], bucket, "b.txt"), (200, object_b.decode()))
        self.assertGreaterEqual(self._read_object(self.project_a, keys_a["secret"], bucket, "b.txt")[0], 400)
        self.assertGreaterEqual(self._read_object(self.project_b, keys_b["secret"], bucket, "a.txt")[0], 400)
        self.assertGreaterEqual(self._list_buckets(self.project_b, keys_a["publishable"])[0], 400)
        self.assertGreaterEqual(self._list_buckets(self.project_b, keys_a["secret"])[0], 400)
        spoof_status, spoof_body = self._read_object(
            self.project_a,
            keys_a["secret"],
            bucket,
            "a.txt",
            forwarded_host=f"{tenant_b}.storage.internal",
        )
        self.assertEqual((spoof_status, spoof_body), (200, object_a.decode()))

        # 15-16: limites e transformacao sao configuracoes por tenant.
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nLkAAAAASUVORK5CYII="
        )
        for project, key in (
            (self.project_a, keys_a["secret"]),
            (self.project_b, keys_b["secret"]),
        ):
            self.assertIn(
                self._upload(project, key, bucket, "pixel.png", png, content_type="image/png")[0],
                {200, 201},
            )
            transform_status, _ = request(
                "GET",
                self._storage_url(
                    project,
                    f"render/image/authenticated/{bucket}/pixel.png?width=1&height=1",
                ),
                headers=self._key_headers(key),
            )
            self.assertEqual(transform_status, 200)
        self._update_file_limit(self.project_a, 128)
        self._update_file_limit(self.project_b, 4096)
        self.assertEqual(
            self._upload(self.project_a, keys_a["secret"], bucket, "large.bin", b"x" * 1024)[0],
            413,
        )
        self.assertIn(
            self._upload(self.project_b, keys_b["secret"], bucket, "large.bin", b"x" * 1024)[0],
            {200, 201},
        )

        # 19-21: SigV4 e escopo tenant + access key.
        s3_a = self._s3_credentials(self.project_a)
        s3_b = self._s3_credentials(self.project_b)
        self.assertEqual(self._s3_request(self.project_a, **s3_a)[0], 200)
        self.assertEqual(self._s3_request(self.project_b, **s3_b)[0], 200)
        self.assertGreaterEqual(self._s3_request(self.project_b, **s3_a)[0], 400)
        self.assertGreaterEqual(self._s3_request(self.project_a, **s3_b)[0], 400)
        self.assertGreaterEqual(
            self._s3_request(self.project_a, "0" * 32, "1" * 64)[0],
            400,
        )

        # 22-24: Vector Buckets de mesmo nome e crossing SigV4.
        vector_bucket = f"vectors-{tenant_a[:8]}"
        vector_body = {"vectorBucketName": vector_bucket}
        self._vector_probe(self.project_a, tenant_a, "CreateVectorBucket", vector_body, expect_success=True)
        self._vector_probe(self.project_b, tenant_b, "CreateVectorBucket", vector_body, expect_success=True)
        self._vector_probe(self.project_a, tenant_a, "ListVectorBuckets", {}, expect_success=True)
        self._vector_probe(self.project_b, tenant_b, "ListVectorBuckets", {}, expect_success=True)
        self._vector_probe(self.project_a, tenant_b, "ListVectorBuckets", {}, expect_success=False)
        self._vector_probe(self.project_b, tenant_a, "ListVectorBuckets", {}, expect_success=False)
        operation = self.server_root / "generateProject" / "operations" / "setup_vector_bucket_wrapper.sh"
        self._bash(f"bash {shlex.quote(str(operation))} {self.project_a} {vector_bucket}")
        self._bash(f"bash {shlex.quote(str(operation))} {self.project_b} {vector_bucket}")

        # 13-14: backup contem somente A; restore de A preserva B.
        status, backup_job = request(
            "POST",
            f"{self.api_url}/api/projects/{self.project_a}/restore-points",
            headers=self.headers,
            payload={"title": "shared-storage-smoke", "description": "tenant isolation"},
        )
        self.assertEqual(status, 202, backup_job)
        wait_for_job(self.api_url, backup_job["job_id"], self.headers)
        point_id = backup_job["restore_point_id"]
        backup_dir = self.server_root / "backups" / tenant_a / point_id
        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["storage_tenant_id"], tenant_a)
        archive_bytes = b""
        with tarfile.open(backup_dir / "storage.tar.gz", "r:gz") as archive:
            self.assertTrue(all(not pathlib.PurePosixPath(item.name).is_absolute() for item in archive))
            for item in archive.getmembers():
                if item.isfile():
                    extracted = archive.extractfile(item)
                    if extracted is not None:
                        archive_bytes += extracted.read()
        self.assertIn(object_a, archive_bytes)
        self.assertNotIn(object_b, archive_bytes)

        # 10-12: os dois modos de clone e credenciais sempre novas.
        self._duplicate_project(self.project_a, self.clone_data, with_data=True)
        self._duplicate_project(self.project_b, self.clone_schema, with_data=False)
        clone_data_keys = self._claim_keys(self.clone_data)
        clone_schema_keys = self._claim_keys(self.clone_schema)
        clone_s3 = self._s3_credentials(self.clone_data)
        self.assertNotEqual(clone_s3, s3_a)
        self.assertEqual(
            self._read_object(self.clone_data, clone_data_keys["secret"], bucket, "a.txt"),
            (200, object_a.decode()),
        )
        schema_status, schema_buckets = self._list_buckets(
            self.clone_schema,
            clone_schema_keys["secret"],
        )
        self.assertEqual(schema_status, 200)
        self.assertEqual(schema_buckets, [])

        # 9: rename troca somente ref/rotas; UUID, objetos e S3 continuam.
        status, rename_job = request(
            "POST",
            f"{self.api_url}/api/projects/{self.project_a}/rename",
            headers=self.headers,
            payload={"new_name": self.renamed_a},
        )
        self.assertEqual(status, 202, rename_job)
        wait_for_job(self.api_url, rename_job["job_id"], self.headers)
        self.created_projects.discard(self.project_a)
        self.created_projects.add(self.renamed_a)
        self.assertEqual(
            _read_env(self.server_root / "projects" / self.renamed_a / ".env")["PROJECT_UUID"],
            tenant_a,
        )
        self.assertEqual(
            self._read_object(self.renamed_a, keys_a["secret"], bucket, "a.txt"),
            (200, object_a.decode()),
        )
        self.assertEqual(self._s3_request(self.renamed_a, **s3_a)[0], 200)
        self._bash(f"bash {shlex.quote(str(operation))} {self.renamed_a} {vector_bucket}")

        self.assertIn(
            self._upload(
                self.renamed_a,
                keys_a["secret"],
                bucket,
                "a.txt",
                b"tenant-a-after-backup",
                upsert=True,
            )[0],
            {200, 201},
        )
        status, restore_job = request(
            "POST",
            f"{self.api_url}/api/projects/{self.renamed_a}/restore-points/{point_id}/restore",
            headers=self.headers,
        )
        self.assertEqual(status, 202, restore_job)
        wait_for_job(self.api_url, restore_job["job_id"], self.headers)
        self.assertEqual(
            self._read_object(self.renamed_a, keys_a["secret"], bucket, "a.txt"),
            (200, object_a.decode()),
        )
        self.assertEqual(
            self._read_object(self.project_b, keys_b["secret"], bucket, "b.txt"),
            (200, object_b.decode()),
        )

        # 8: remover A apaga somente seu namespace/tenant.
        self._delete_project(self.renamed_a)
        self.assertEqual(
            self._read_object(self.project_b, keys_b["secret"], bucket, "b.txt"),
            (200, object_b.decode()),
        )

        # 25 e 28: host ausente e UUID bem-formado nao provisionado falham.
        root = shlex.quote(str(self.server_root))
        project_b = shlex.quote(self.project_b)
        self._bash(
            f"""
set -Eeuo pipefail
set -a; source {root}/.env; source {root}/projects/{project_b}/.env; set +a
source {root}/generateProject/lib/storage_multitenant.sh
storage_assert_jwt_data_plane 00000000-0000-4000-8000-000000000099 "$SERVICE_ROLE_KEY_PROJETO"
""",
            expect_success=False,
        )
        self._bash(
            f"""
set -Eeuo pipefail
set -a; source {root}/projects/{project_b}/.env; set +a
printf '%s' "$SERVICE_ROLE_KEY_PROJETO" | docker exec -i supabase-storage-global node -e '
let key=""; process.stdin.on("data", c => key += c); process.stdin.on("end", async () => {{
  const r = await fetch("http://127.0.0.1:5000/bucket", {{headers: {{authorization:`Bearer ${{key}}`, apikey:key}}}});
  process.exit(r.ok ? 1 : 0);
}});'
""",
            expect_success=True,
        )

        # 27-28 e criterio N: indisponibilidade e tenant ausente nunca usam
        # containers locais. Este trecho interrompe o global por poucos segundos.
        names = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        self.assertEqual(names.count("supabase-storage-global"), 1)
        self.assertEqual(names.count("supabase-imgproxy-global"), 1)
        self.assertFalse(
            any(
                (name.startswith("supabase-storage-") and name != "supabase-storage-global")
                or (name.startswith("supabase-imgproxy-") and name != "supabase-imgproxy-global")
                for name in names
            )
        )
        subprocess.run(
            ["docker", "stop", "--time", "30", "supabase-storage-global"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.storage_was_stopped = True
        try:
            try:
                unavailable_status, _ = self._list_buckets(
                    self.project_b,
                    keys_b["secret"],
                )
            except urllib.error.URLError:
                unavailable_status = 599
            self.assertGreaterEqual(unavailable_status, 500)
        finally:
            subprocess.run(
                ["docker", "start", "supabase-storage-global"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            self.storage_was_stopped = False
            self._wait_storage()
        self.assertEqual(
            self._read_object(self.project_b, keys_b["secret"], bucket, "b.txt"),
            (200, object_b.decode()),
        )


if __name__ == "__main__":
    unittest.main()
