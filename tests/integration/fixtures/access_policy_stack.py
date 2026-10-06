"""Synthetic control-plane records and checks for the disposable admission stack."""

import asyncio
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import statistics
import sys
import threading
import time
import uuid
from unittest.mock import patch

WORK = Path("/work")
CONFIG = json.loads((WORK / "config.json").read_text())
sys.path.insert(0, str(WORK / "api"))


def environment():
    from cryptography.fernet import Fernet

    os.environ.update(
        {
            "DB_DSN": f"postgres://postgres:{CONFIG['password']}@pg:5432/postgres",
            "HOST_AGENT_HMAC_SECRET": "h" * 32,
            "NGINX_HMAC_SECRET": "n" * 32,
            "STUDIO_GATEWAY_HMAC_SECRET": "g" * 32,
            "PROJECTS_API_HMAC_SECRET": "p" * 32,
            "LOGFLARE_PRIVATE_ACCESS_TOKEN": "l" * 32,
            "PROJECT_SECRETS_MASTER_KEY": Fernet.generate_key().decode(),
            "PG_META_CRYPTO_KEY": Fernet.generate_key().decode(),
            "STUDIO_SERVICE_KEY_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
    )


def policy(mode="unrestricted", countries=None, networks=None, rate=None, quota=None):
    return dict(
        geo_mode=mode,
        allowed_countries=countries,
        allowed_networks=networks or [],
        rate_limit=rate,
        request_quota=quota,
    )


async def connection():
    import asyncpg

    return await asyncpg.connect(f"postgres://postgres:{CONFIG['password']}@pg:5432/postgres")


async def seed():
    environment()
    import asyncpg
    from app.schema_migrations import apply_migrations
    from app.control_plane_roles import (
        ensure_key_authorizer_role,
        ensure_client_configuration_reader_role,
        ensure_platform_app_role,
    )
    from app.opaque_keys import generate_opaque_key, generate_application_ref

    conn = await connection()
    await apply_migrations(conn)
    owner, member = uuid.uuid4(), uuid.uuid4()
    for uid in (owner, member):
        await conn.execute("INSERT INTO users(id,authelia_username) VALUES($1,$2)", uid, str(uid))
    state = {"owner": str(owner), "member": str(member), "projects": []}
    for index, name in enumerate(("alpha", "bravo")):
        pid, gateway = uuid.uuid4(), secrets.token_hex(32)
        ref = chr(97 + index) * 20
        await conn.execute(
            """INSERT INTO projects(id,tenant_uuid,name,display_name,owner_id,public_ref,
            api_gateway_token_hash,opaque_keys_activated_at,opaque_gateway_ready_at)
            VALUES($1,$1,$2,$2,$3,$4,$5,now(),now())""",
            pid,
            name,
            owner,
            ref,
            hashlib.sha256(gateway.encode()).digest(),
        )
        await conn.execute(
            "INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,'admin'),($1,$3,'member')",
            pid,
            owner,
            member,
        )
        project = dict(id=str(pid), name=name, ref=ref, gateway=gateway, slots=[])
        for kind in ("publishable", "secret"):
            sid, kid, token = uuid.uuid4(), uuid.uuid4(), generate_opaque_key(pid, kind)
            await conn.execute(
                """INSERT INTO project_api_key_slots(id,project_id,name,kind,allowed_services,
                automatic_rotation_enabled,rotation_interval_days,application_ref) VALUES($1,$2,$3,$4,$5,false,null,$6)""",
                sid,
                pid,
                "default-" + kind,
                kind,
                ["auth", "rest", "graphql", "storage", "functions", "realtime"],
                generate_application_ref() if kind == "publishable" else None,
            )
            await conn.execute(
                """INSERT INTO project_api_keys(id,slot_id,secret_hash,token_hint,status,activated_at)
                VALUES($1,$2,$3,$4,'active',now())""",
                kid,
                sid,
                token.digest,
                token.token_hint,
            )
            if kind == "publishable":
                await conn.execute(
                    "INSERT INTO public_client_configuration_keys VALUES($1,$2)", kid, token.token
                )
            application_ref = await conn.fetchval(
                "SELECT application_ref FROM project_api_key_slots WHERE id=$1", sid
            )
            project["slots"].append(
                dict(id=str(sid), key_id=str(kid), key=token.token, kind=kind, ref=application_ref)
            )
        studio = generate_opaque_key(pid, "secret")
        await conn.execute(
            "INSERT INTO project_studio_keys(project_id,secret_hash,secret_ciphertext) VALUES($1,$2,$3)",
            pid,
            studio.digest,
            "synthetic-unused-ciphertext",
        )
        project["studio"] = studio.token
        state["projects"].append(project)
    pool = await asyncpg.create_pool(os.environ["DB_DSN"], min_size=1, max_size=2)
    await ensure_key_authorizer_role(pool, password=CONFIG["password"])
    await ensure_client_configuration_reader_role(pool, password=CONFIG["password"])
    await ensure_platform_app_role(pool, password=CONFIG["password"])
    await pool.close()
    await privilege_checks(conn, state["projects"][0])
    await conn.close()
    (WORK / "state.json").write_text(json.dumps(state))
    first = state["projects"][0]
    template = (WORK / "nginxtemplate").read_text()
    values = {
        "{{project_id}}": first["name"],
        "{{project_uuid}}": first["id"],
        "{{project_public_ref}}": first["ref"],
        "{{server_url}}": "example.test",
        "${ANON_KEY_PROJETO}": "synthetic-anon-jwt",
        "${SERVICE_ROLE_KEY_PROJETO}": "synthetic-service-jwt",
        "${API_GATEWAY_TOKEN_PROJETO}": first["gateway"],
        "${SUPABASE_NETWORK_SUBNET}": "10.207.0.0/24",
        "${FILE_SIZE_LIMIT}": "50m",
    }
    for key, value in values.items():
        template = template.replace(key, value)
    assert "{{" not in template and "${" not in template
    (WORK / "nginx.conf").write_text(template)
    sys.path.insert(0, str(WORK))
    from render_dynamic_config import render

    root = WORK / "root.env"
    root.write_text(
        f"ACCESS_ADMISSION_SECRET={CONFIG['secret']}\nACCESS_TRUSTED_PROXY_CIDRS=10.207.0.100/32\nSERVER_PROTO=http\n"
    )
    projects = WORK / "projects"
    for p in state["projects"]:
        folder = projects / p["name"]
        folder.mkdir(parents=True)
        (folder / ".env").write_text(
            f"PROJECT_ID={p['name']}\nPROJECT_UUID={p['id']}\nPROJECT_PUBLIC_REF={p['ref']}\nAPI_GATEWAY_TOKEN_PROJETO={p['gateway']}\n"
        )
    import yaml

    routes = yaml.safe_load(render(root, projects))
    # The fixture isolates admission, not the independent scanner/catch-all middlewares.
    for name, router in routes["http"]["routers"].items():
        router["middlewares"] = [
            m
            for m in router["middlewares"]
            if m.startswith(("project-admission-", "project-strip-", "discovery-admission"))
        ]
    routes["http"]["routers"].pop("projects-api")
    (WORK / "dynamic/routes.yml").write_text(json.dumps(routes))
    print(
        "PASS migrations, seeded canonical identities, least-privilege roles, production route renderer"
    )


async def privilege_checks(conn, project):
    import asyncpg
    from app.opaque_keys import generate_application_ref

    for role in ("key_authorizer", "platform_app"):
        for table in ("access_quota_usage", "access_rate_epoch"):
            for operation in ("INSERT", "UPDATE", "DELETE"):
                assert not await conn.fetchval(
                    "SELECT has_table_privilege($1,$2,$3)", role, table, operation
                )
    assert not await conn.fetchval(
        "SELECT has_table_privilege('platform_app','access_rate_epoch','SELECT')"
    )
    assert await conn.fetchval(
        "SELECT has_table_privilege('platform_app','access_quota_usage','SELECT')"
    )
    transaction = conn.transaction()
    await transaction.start()
    try:
        slot, project_id = uuid.uuid4(), uuid.UUID(project["id"])
        await conn.execute("SET LOCAL ROLE platform_app")
        await conn.execute(
            """INSERT INTO project_api_key_slots(id,project_id,name,kind,allowed_services,application_ref,automatic_rotation_enabled,rotation_interval_days)
            VALUES($1,$2,'quota-cleanup-probe','publishable',ARRAY['rest'],$3,false,null)""",
            slot,
            project_id,
            generate_application_ref(),
        )
        await conn.execute("SET LOCAL ROLE key_authorizer")
        assert (
            await conn.fetchval("SELECT consume_access_quota($1,$2,false)", project_id, slot) == 0
        )
        try:
            async with conn.transaction():
                await conn.execute("UPDATE access_rate_epoch SET initialized=false")
        except asyncpg.InsufficientPrivilegeError:
            pass
        else:
            raise AssertionError("Authorizer can mutate traffic epoch directly")
        await conn.execute("SET LOCAL ROLE platform_app")
        assert (
            await conn.fetchval("SELECT count(*) FROM access_quota_usage WHERE scope_id=$1", slot)
            == 2
        )
        await conn.execute("DELETE FROM project_api_key_slots WHERE id=$1", slot)
        assert (
            await conn.fetchval("SELECT count(*) FROM access_quota_usage WHERE scope_id=$1", slot)
            == 0
        )
    finally:
        await transaction.rollback()
    print(
        "PASS database privileges: bounded quota function, no direct counters/epoch writes, slot deletion clears its usage"
    )


def mock():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            data = json.dumps(
                {"method": self.command, "path": self.path, "headers": dict(self.headers)}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_PUT = do_PATCH = do_DELETE = do_GET

    servers = [
        ThreadingHTTPServer(("0.0.0.0", port), Handler) for port in (9999, 3000, 5000, 9000, 4000)
    ]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()


def state():
    return json.loads((WORK / "state.json").read_text())


async def set_policy(conn, project, value, slot=None):
    table, column, target = (
        ("slot_access_policies", "slot_id", slot)
        if slot
        else ("project_access_policies", "project_id", project["id"])
    )
    await conn.execute(
        f"UPDATE {table} SET policy=$2::jsonb,revision=revision+1 WHERE {column}=$1",
        uuid.UUID(target),
        json.dumps(value),
    )


async def admin_checks(conn):
    environment()
    import asyncpg
    import httpx
    from fastapi import FastAPI
    from app.routers import access_policy as module
    from app.database import get_pool

    app = FastAPI()
    app.include_router(module.router)
    pool = await asyncpg.create_pool(
        f"postgres://platform_app:{CONFIG['password']}@pg:5432/postgres", min_size=1, max_size=4
    )
    app.dependency_overrides[get_pool] = lambda: pool
    s = state()
    p = s["projects"][0]
    actor = dict(db_user_id=uuid.UUID(s["owner"]), is_global_admin=False, login_session="a" * 43)

    async def auth(*args):
        return actor

    def grant(resource):
        now = int(time.time())
        claims = dict(
            sub=s["owner"],
            iat=now,
            exp=now + 300,
            login_session="a" * 43,
            action="update_access_policy",
            project=p["ref"],
            resource=resource,
            jti=secrets.token_urlsafe(16),
        )
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        key = hmac.new(b"n" * 32, b"supabase-multitenant:step-up-token:v1", hashlib.sha256).digest()
        return "su1." + payload + "." + hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()

    try:
        with patch.object(module, "resolve_authenticated_user", auth):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                base = "/api/projects/" + p["ref"]
                r = await client.get(base + "/access-policy")
                assert r.status_code == 200, r.text
                assert len((await client.get("/api/projects/countries")).json()["countries"]) == 250
                assert (await client.get("/api/projects/alpha/access-policy")).status_code == 400
                slotpath = base + "/api-key-slots/" + p["slots"][0]["id"] + "/access-policy"
                snapshot = (await client.get(slotpath)).json()
                body = dict(revision=snapshot["revision"], policy=policy("inherit"))
                r = await client.put(slotpath, json=body)
                assert r.status_code == 200, r.text
                assert (await client.put(slotpath, json=body)).status_code == 409
                actor["db_user_id"] = uuid.UUID(s["member"])
                assert (await client.get(slotpath)).status_code == 403
                actor["db_user_id"] = uuid.UUID(s["owner"])
                assert (
                    await client.get(
                        base
                        + "/api-key-slots/"
                        + s["projects"][1]["slots"][0]["id"]
                        + "/access-policy"
                    )
                ).status_code == 404
                for path, scope in (
                    (base + "/access-policy", p["id"]),
                    (
                        base + "/api-key-slots/" + p["slots"][1]["id"] + "/access-policy",
                        p["slots"][1]["id"],
                    ),
                ):
                    snapshot = (await client.get(path)).json()
                    body = dict(revision=snapshot["revision"], policy=snapshot["policy"])
                    assert (await client.put(path, json=body)).status_code == 403
                    bad = await client.put(
                        path, json=body, headers={"x-step-up-token": grant(scope + ":999")}
                    )
                    assert bad.status_code == 403
                    r = await client.put(
                        path,
                        json=body,
                        headers={"x-step-up-token": grant(scope + ":" + str(snapshot["revision"]))},
                    )
                    assert r.status_code == 200, r.text
                snapshot = (await client.get(slotpath)).json()
                body = dict(revision=snapshot["revision"], policy=snapshot["policy"])
                results = await asyncio.gather(
                    client.put(slotpath, json=body), client.put(slotpath, json=body)
                )
                assert sorted(r.status_code for r in results) == [200, 409]
                assert (await client.get(base + "/access-usage")).status_code == 200
        print(
            "PASS API: admin/member isolation, cross-project slot, strict public ref, step-up action/resource, stale/concurrent revisions"
        )
    finally:
        await pool.close()


async def lifecycle_checks(conn):
    from app.access_policy import copy_project_access_policy, copy_matching_slot_access_policies

    s = state()
    source, destination = s["projects"]
    actor = uuid.UUID(s["owner"])
    async with conn.transaction():
        await set_policy(conn, source, policy("restrict", [], ["10.1.2.3/32"]))
        await set_policy(
            conn,
            source,
            policy("restrict", ["BR"], rate={"requests_per_second": 3, "burst": 5}),
            source["slots"][0]["id"],
        )
        await copy_project_access_policy(
            conn, uuid.UUID(source["id"]), uuid.UUID(destination["id"]), actor
        )
        await copy_matching_slot_access_policies(
            conn, uuid.UUID(source["id"]), uuid.UUID(destination["id"]), actor
        )
        assert await conn.fetchval(
            "SELECT policy FROM project_access_policies WHERE project_id=$1",
            uuid.UUID(source["id"]),
        ) == await conn.fetchval(
            "SELECT policy FROM project_access_policies WHERE project_id=$1",
            uuid.UUID(destination["id"]),
        )
        assert await conn.fetchval(
            "SELECT policy FROM slot_access_policies WHERE slot_id=$1",
            uuid.UUID(source["slots"][0]["id"]),
        ) == await conn.fetchval(
            "SELECT policy FROM slot_access_policies WHERE slot_id=$1",
            uuid.UUID(destination["slots"][0]["id"]),
        )
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM access_quota_usage WHERE project_id=$1",
                uuid.UUID(destination["id"]),
            )
            == 0
        )
        await conn.execute(
            "DELETE FROM slot_access_policies WHERE slot_id=$1", uuid.UUID(source["slots"][0]["id"])
        )
        try:
            await copy_matching_slot_access_policies(
                conn, uuid.UUID(source["id"]), uuid.UUID(destination["id"]), actor
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Missing source policy must not become inherited access")
    # Restore explicit fixtures; the helpers were tested inside real database transactions.
    for project in (source, destination):
        await set_policy(conn, project, policy())
        sid = uuid.UUID(project["slots"][0]["id"])
        await conn.execute(
            "INSERT INTO slot_access_policies(slot_id,policy) VALUES($1,$2::jsonb) ON CONFLICT(slot_id) DO UPDATE SET policy=EXCLUDED.policy,revision=slot_access_policies.revision+1",
            sid,
            json.dumps(policy("inherit")),
        )
    print(
        "PASS duplication: validated project and matching slot rules, independent usage, missing source policy rejected"
    )


async def check():
    import httpx
    from app.opaque_keys import generate_opaque_key

    s = state()
    p, slot = s["projects"][0], s["projects"][0]["slots"][0]
    conn = await connection()
    await admin_checks(conn)
    await lifecycle_checks(conn)
    async with httpx.AsyncClient(timeout=8) as client:
        for _ in range(60):
            try:
                if (await client.get("http://key-authorizer:18010/healthz")).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
        else:
            raise AssertionError("Authorizer not ready")

        async def request(
            path="/rest/v1/table", key=slot["key"], ip="8.8.8.8", status=200, method="GET", **kwargs
        ):
            headers = {"X-Forwarded-For": ip}
            if key:
                headers["apikey"] = key
            headers.update(kwargs.pop("headers", {}))
            r = await client.request(
                method, "http://edge:8080/" + p["ref"] + path, headers=headers, **kwargs
            )
            assert r.status_code == status, (path, status, r.status_code, r.text[:200])
            if status >= 400:
                assert r.headers.get("cache-control") == "no-store", r.headers
            return r

        await asyncio.sleep(1)
        for path in (
            "/rest/v1/table",
            "/auth/v1/user",
            "/graphql/v1",
            "/storage/v1/object/a/b",
            "/functions/v1/hello",
            "/vector/bucket",
        ):
            r = await request(
                path,
                headers={
                    "X-Gateway-Admission": "forged",
                    "X-Opaque-Key-Id": "forged",
                    "X-Country-Code": "BR",
                    "X-Project-Name": "forged",
                },
            )
            seen = {k.lower(): v for k, v in r.json()["headers"].items()}
            assert seen["apikey"] == "synthetic-anon-jwt", (path, seen)
            assert "x-gateway-admission" not in seen and "x-admission-uri" not in seen
            assert seen["x-api-key-id"] == slot["key_id"]
        await request("/rest/v1/table", method="POST", json={"v": 1})
        await request("/rest/v1/table?apikey=" + slot["key"], key=None)
        await request("/realtime/v1/websocket?apikey=" + slot["key"] + "&vsn=1.0.0", key=None)
        await request("/auth/v1/verify?token=opaque-capability", key=None)
        await request("/storage/v1/object/sign/bucket/a%20b.png?token=storage-capability", key=None)
        await request(key=None, status=401)
        await request(key=s["projects"][1]["slots"][0]["key"], status=403)
        await request(
            "/rest/v1/table?apikey=" + slot["key"] + "&apikey=" + slot["key"], key=None, status=403
        )
        r = await client.get(
            "http://supabase-nginx-alpha:8080/rest/v1/table", headers={"apikey": slot["key"]}
        )
        assert r.status_code == 403
        ref = slot["ref"]
        discovery = "http://edge:8080/config/" + ref
        r = await client.get(discovery, headers={"X-Forwarded-For": "8.8.8.8"})
        assert r.status_code == 200, r.text
        assert r.json()["key_id"] == slot["key_id"]
        assert (
            await client.get("http://client-configuration:18011/config/" + ref)
        ).status_code == 403
        print(
            "PASS real Traefik/Nginx: services, POST, query key, keyless capabilities, encoded filename, identity translation, forged-header stripping, direct-access rejection, discovery"
        )

        await set_policy(conn, p, policy("restrict", ["US"]))
        await request()
        await request(ip="200.160.2.3", status=403)
        await request(ip="10.1.2.3", status=403)
        await request(ip="200.160.2.3, 8.8.8.8")
        await request(ip="8.8.8.8, 200.160.2.3", status=403)
        await set_policy(conn, p, policy("restrict", ["US"], ["10.1.2.3/32"]))
        await request(ip="10.1.2.3")
        await set_policy(conn, p, policy("restrict", []))
        await request(status=403)
        await request("/auth/v1/verify", key=None, status=403)
        await request("/storage/v1/object/sign/a/b?token=abc", key=None, status=403)
        assert (
            await client.get(discovery, headers={"X-Forwarded-For": "8.8.8.8"})
        ).status_code == 403
        await request(key=p["studio"], status=403)
        await request(key=p["studio"], ip="10.207.0.100")
        await set_policy(conn, p, policy())
        await set_policy(conn, p, policy("restrict", ["BR"]), slot["id"])
        await request(status=403)
        await request(ip="200.160.2.3")
        assert (
            await client.get(discovery, headers={"X-Forwarded-For": "8.8.8.8"})
        ).status_code == 403
        await set_policy(conn, p, policy("inherit"), slot["id"])
        print(
            "PASS country selection, project AND slot restriction, unknown fail-closed, explicit CIDR, proxy-chain anti-spoofing, callbacks/discovery, bounded separate Studio namespace"
        )

        await set_policy(
            conn, p, policy("inherit", rate={"requests_per_second": 1, "burst": 2}), slot["id"]
        )
        await request()
        await request()
        r = await request(status=429)
        assert int(r.headers["retry-after"]) >= 1
        await request(key=p["slots"][1]["key"])
        await set_policy(conn, p, policy("inherit"), slot["id"])
        before = await conn.fetchval(
            "SELECT admitted FROM access_quota_usage WHERE scope_id=$1 AND period='day' AND scope_type='slot' ORDER BY period_start DESC LIMIT 1",
            uuid.UUID(slot["id"]),
        )
        await set_policy(
            conn, p, policy("inherit", quota={"period": "day", "limit": before + 3}), slot["id"]
        )
        results = await asyncio.gather(
            *[
                client.get(
                    "http://edge:8080/" + p["ref"] + "/rest/v1/table",
                    headers={"apikey": slot["key"], "X-Forwarded-For": "8.8.8.8"},
                )
                for _ in range(12)
            ]
        )
        assert sorted(r.status_code for r in results) == [200] * 3 + [429] * 9, [
            (r.status_code, r.text[:90]) for r in results
        ]
        after = await conn.fetchval(
            "SELECT admitted FROM access_quota_usage WHERE scope_id=$1 AND period='day' AND scope_type='slot' ORDER BY period_start DESC LIMIT 1",
            uuid.UUID(slot["id"]),
        )
        assert after == before + 3
        rotated = generate_opaque_key(uuid.UUID(p["id"]), "publishable")
        kid = uuid.uuid4()
        async with conn.transaction():
            await conn.execute(
                "UPDATE project_api_keys SET status='revoked',revoked_at=now() WHERE id=$1",
                uuid.UUID(slot["key_id"]),
            )
            await conn.execute(
                "INSERT INTO project_api_keys(id,slot_id,secret_hash,token_hint,status,activated_at) VALUES($1,$2,$3,$4,'active',now())",
                kid,
                uuid.UUID(slot["id"]),
                rotated.digest,
                rotated.token_hint,
            )
            await conn.execute(
                "INSERT INTO public_client_configuration_keys VALUES($1,$2)", kid, rotated.token
            )
        slot.update(key=rotated.token, key_id=str(kid))
        await request(key=slot["key"], status=429)
        r = await client.get(discovery, headers={"X-Forwarded-For": "8.8.8.8"})
        assert r.status_code == 200 and r.json()["key_id"] == str(kid)
        await set_policy(conn, p, policy("inherit"), slot["id"])
        print(
            "PASS slot isolation, 429/Retry-After, concurrent exact daily quota, durable day/month ledgers, rotation preserves quota, discovery has separate accounting"
        )

        body = dict(
            project_ref=p["name"],
            gateway_token=p["gateway"],
            uri="/" + p["ref"] + "/rest/v1/table",
            method="GET",
            client_ip="8.8.8.8",
            api_key=slot["key"],
            authorization="",
        )
        r = await client.post(
            "http://key-authorizer:18010/v1/admit",
            json=body,
            headers={"X-Admission-Secret": CONFIG["secret"]},
        )
        assert r.status_code == 204, r.text
        ticket = r.headers["x-gateway-admission"]
        headers = {
            "apikey": slot["key"],
            "X-Gateway-Admission": ticket,
            "X-Admission-URI": body["uri"],
            "X-Admission-Method": "GET",
        }
        url = "http://supabase-nginx-alpha:8080/rest/v1/table"
        assert (await client.get(url, headers=headers)).status_code == 200
        assert (await client.get(url, headers=headers)).status_code == 403
        r = await client.post(
            "http://key-authorizer:18010/v1/admit",
            json=body,
            headers={"X-Admission-Secret": CONFIG["secret"]},
        )
        headers["X-Gateway-Admission"] = r.headers["x-gateway-admission"]
        await set_policy(conn, p, policy())
        assert (await client.get(url, headers=headers)).status_code == 403
        print("PASS single-use ticket redemption and revision-change rejection")

        await set_policy(conn, p, policy(rate={"requests_per_second": 100000, "burst": 100000}))
        samples = []
        for _ in range(100):
            started = time.perf_counter()
            await request(key=slot["key"])
            samples.append((time.perf_counter() - started) * 1000)
        print(
            f"MEASURE sequential full HTTP admission + mock proxy, n=100 median={statistics.median(samples):.2f}ms p95={sorted(samples)[94]:.2f}ms"
        )

        async def measured():
            async with semaphore:
                started = time.perf_counter()
                await request(key=slot["key"])
                return (time.perf_counter() - started) * 1000

        semaphore = asyncio.Semaphore(8)
        started = time.perf_counter()
        samples = await asyncio.gather(*[measured() for _ in range(200)])
        elapsed = time.perf_counter() - started
        print(
            f"MEASURE full HTTP admission + mock proxy, n=200 concurrency=8 throughput={200 / elapsed:.1f}req/s p95={sorted(samples)[189]:.2f}ms"
        )
        await set_policy(conn, p, policy())
        await set_policy(
            conn, p, policy("inherit", quota={"period": "month", "limit": 1}), slot["id"]
        )
        await request(key=slot["key"], status=429)
        (WORK / "state.json").write_text(json.dumps(s))
        print("PASS changing day to month uses existing month ledger; restart invariant prepared")
    await conn.close()


async def restart_check():
    import httpx

    s = state()
    p = s["projects"][0]
    async with httpx.AsyncClient(timeout=8) as client:
        for _ in range(60):
            try:
                if (await client.get("http://key-authorizer:18010/healthz")).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
        r = await client.get(
            "http://edge:8080/" + p["ref"] + "/rest/v1/table",
            headers={"apikey": p["slots"][0]["key"], "X-Forwarded-For": "8.8.8.8"},
        )
        assert r.status_code == 429, (r.status_code, r.text)
    print("PASS authorizer restart preserves exhausted durable quota")


async def prepare_failure():
    p = state()["projects"][0]
    conn = await connection()
    await set_policy(conn, p, policy("restrict", ["US"]) if sys.argv[2] == "geoip" else policy())
    await set_policy(conn, p, policy("inherit"), p["slots"][0]["id"])
    await conn.close()


async def failure_check():
    import httpx

    p = state()["projects"][0]
    async with httpx.AsyncClient(timeout=12) as client:
        for path in ("/" + p["ref"] + "/rest/v1/table", "/config/" + p["slots"][0]["ref"]):
            r = await client.get(
                "http://edge:8080" + path,
                headers={"apikey": p["slots"][0]["key"], "X-Forwarded-For": "8.8.8.8"},
            )
            assert r.status_code == 503, (sys.argv[2], r.status_code, r.text[:100])
            assert (
                r.json()["error"] == "admission_unavailable"
                and r.headers["cache-control"] == "no-store"
            )
    print("PASS dependency fail-closed: " + sys.argv[2] + " for project and discovery")


async def geoip_reloaded():
    import httpx

    p = state()["projects"][0]
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            "http://edge:8080/" + p["ref"] + "/rest/v1/table",
            headers={"apikey": p["slots"][0]["key"], "X-Forwarded-For": "8.8.8.8"},
        )
        assert r.status_code == 200, (r.status_code, r.text[:100])
    print("PASS atomic GeoIP replacement reopens validated database without service restart")


async def recover_epoch():
    environment()
    from app.reset_access_rate_epoch import reset

    p = state()["projects"][0]
    conn = await connection()
    epoch = await conn.fetchval("SELECT epoch FROM access_rate_epoch WHERE singleton")
    await set_policy(
        conn, p, policy("inherit", quota={"period": "month", "limit": 1}), p["slots"][0]["id"]
    )
    await conn.close()
    await reset(epoch)
    print("PASS explicit privileged epoch recovery, no quota reset")


if __name__ == "__main__":
    if sys.argv[1] == "mock":
        mock()
    else:
        asyncio.run(
            {
                "seed": seed,
                "check": check,
                "restart-check": restart_check,
                "prepare-failure": prepare_failure,
                "failure-check": failure_check,
                "geoip-reloaded": geoip_reloaded,
                "recover-epoch": recover_epoch,
            }[sys.argv[1]]()
        )
