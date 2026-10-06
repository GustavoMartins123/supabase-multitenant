"""Data-plane geographic evaluation and single-use admission accounting."""

import hashlib
import ipaddress
import json
import secrets
import urllib.parse

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from access_policy import AccessPolicy, canonical_ip, parse_policy

RATE_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return {-1,0} end
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2])/1000000
local proposed = {}
local wait = 0
for i=2,#KEYS do
  local rate = tonumber(ARGV[2+(i-2)*3])
  local capacity = tonumber(ARGV[3+(i-2)*3])
  local lifetime = tonumber(ARGV[4+(i-2)*3])
  local state = redis.call('HMGET',KEYS[i],'tokens','time','rate','capacity')
  local tokens = capacity
  if state[1] then tokens = math.min(capacity, tonumber(state[4]), tonumber(state[1]) + math.max(0,now-tonumber(state[2]))*tonumber(state[3])) end
  proposed[i] = {tokens, rate, capacity, lifetime}
  if tokens < 1 then wait = math.max(wait, math.ceil((1-tokens)/rate)) end
end
if wait > 0 then return {0,wait} end
for i=2,#KEYS do
  redis.call('HSET',KEYS[i],'tokens',proposed[i][1]-1,'time',now,'rate',proposed[i][2],'capacity',proposed[i][3])
  redis.call('EXPIRE',KEYS[i],proposed[i][4])
end
return {1,0}
"""


class AdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_ref: str
    gateway_token: str
    uri: str = Field(min_length=1, max_length=32768)
    method: str = Field(min_length=3, max_length=12)
    client_ip: str
    api_key: str = Field(max_length=512)
    authorization: str = Field(max_length=8192)


def route(uri: str, public_ref: str | None):
    parts = urllib.parse.urlsplit(uri)
    if not uri.startswith("/") or parts.scheme or parts.netloc or parts.fragment:
        raise HTTPException(403, "Invalid admission URI")
    path = parts.path
    if public_ref is None:
        ref = path.removeprefix("/config/")
        if (
            path != "/config/" + ref
            or len(ref) != 20
            or not ref.isascii()
            or not ref.isalpha()
            or not ref.islower()
            or parts.query
        ):
            raise HTTPException(400, "Invalid configuration reference")
        return "discovery", True, "", parts
    prefix = "/" + public_ref
    if not path.startswith(prefix + "/"):
        raise HTTPException(403, "Project URL mismatch")
    path = path[len(prefix) :]
    decoded = urllib.parse.unquote(path)
    if "\\" in decoded or any(p in {".", ".."} for p in decoded.split("/")):
        raise HTTPException(400, "Non-canonical project path")
    for prefix, service in (
        ("/auth/v1/", "auth"),
        ("/rest/v1/", "rest"),
        ("/graphql/v1", "graphql"),
        ("/storage/v1/", "storage"),
        ("/vector/", "storage"),
        ("/functions/v1/", "functions"),
        ("/realtime/v1/websocket", "realtime"),
    ):
        if path.startswith(prefix):
            missing = (service == "storage" and not path.startswith("/vector/")) or path in {
                "/auth/v1/verify",
                "/auth/v1/callback",
                "/auth/v1/authorize",
            }
            return service, missing, "service_role" if path == "/rest/v1/" else "", parts
    if path in {
        "/recovery.html",
        "/invite.html",
        "/magiclink.html",
        "/confirmation.html",
        "/email_change.html",
        "/verify-success.html",
        "/verify-success.html/",
        "/verify-success.js",
        "/verify-success.html/verify-success.js",
    }:
        return "auth", True, "", parts
    raise HTTPException(404, "Project route not found")


def query_key(query):
    values = urllib.parse.parse_qs(query, keep_blank_values=True)
    return values["apikey"][0] if "apikey" in values and len(values["apikey"]) == 1 else ""


def ticket_binding(body, project_id, key_id):
    return {
        "project": str(project_id),
        "key": key_id,
        "credential": hashlib.sha256(body.api_key.encode()).hexdigest(),
        "method": body.method,
        "uri": hashlib.sha256(body.uri.encode()).hexdigest(),
    }


class AdmissionEngine:
    def __init__(self, pool, redis, admin_cidrs):
        self.pool, self.redis = pool, redis
        self.admin_networks = [ipaddress.ip_network(v, strict=True) for v in admin_cidrs.split(",")]
        if not self.admin_networks or any(
            n.prefixlen == 0
            or (isinstance(n, ipaddress.IPv6Network) and n.network_address.ipv4_mapped)
            for n in self.admin_networks
        ):
            raise RuntimeError("Explicit administrative origins are required")
        self.http = httpx.AsyncClient(timeout=2, follow_redirects=False)
        self.epoch = None

    async def startup(self):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(739115992)")
                row = await conn.fetchrow(
                    "SELECT epoch,initialized FROM access_rate_epoch WHERE singleton"
                )
                if row is None:
                    raise RuntimeError("Missing access-rate epoch")
                self.epoch = str(row["epoch"])
                stored = await self.redis.get("access:epoch")
                if not row["initialized"]:
                    if stored is None and await self.redis.dbsize() != 0:
                        raise RuntimeError(
                            "Traffic initialization requires an empty Redis database"
                        )
                    if stored is not None and stored != self.epoch:
                        raise RuntimeError("Traffic Redis belongs to another epoch")
                    await self.redis.set("access:epoch", self.epoch, nx=True)
                    await conn.execute("SELECT initialize_access_rate_epoch()")
                elif stored != self.epoch:
                    raise RuntimeError(
                        "Traffic counter state lost; explicit maintenance is required"
                    )

    async def country(self, ip):
        response = await self.http.get("http://geoip-api:8000/v1/ip/country/" + ip)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise HTTPException(503, "Geographic evaluation unavailable")
        country = response.text
        from access_policy import COUNTRY_CODES

        if country not in COUNTRY_CODES:
            raise HTTPException(503, "Invalid geographic response")
        return country

    async def geographic(self, policies, ip):
        required = [p for p in policies if p.geo_mode == "restrict" and not p.allows_network(ip)]
        if not required:
            return
        if any(not p.allowed_countries for p in required):
            raise HTTPException(403, "Geographic access denied")
        country = await self.country(ip)
        if any(not p.allows_country(country) for p in required):
            raise HTTPException(403, "Geographic access denied")

    async def policies(self, conn, project_id, slot_id):
        project = await conn.fetchrow(
            "SELECT policy,revision FROM project_access_policies WHERE project_id=$1", project_id
        )
        slot = (
            await conn.fetchrow(
                "SELECT policy,revision FROM slot_access_policies WHERE slot_id=$1", slot_id
            )
            if slot_id
            else None
        )
        if project is None or (slot_id and slot is None):
            raise HTTPException(503, "Access policy unavailable")
        policies = [parse_policy(project["policy"], "project")]
        revisions = [project["revision"]]
        if slot:
            policies.append(parse_policy(slot["policy"], "slot"))
            revisions.append(slot["revision"])
        return policies, revisions

    async def rate(self, scopes, policies):
        keys, args = ["access:epoch"], [self.epoch]
        for scope, policy in zip(scopes, policies, strict=True):
            if policy.rate_limit:
                keys.append("access:rate:" + scope)
                lifetime = 1000001
                if scope.startswith("discovery:") or scope.endswith(":admin"):
                    lifetime = 5
                args.extend(
                    [policy.rate_limit.requests_per_second, policy.rate_limit.burst, lifetime]
                )
        result, wait = await self.redis.eval(RATE_SCRIPT, len(keys), *keys, *args)
        if result == -1:
            raise HTTPException(503, "Traffic counter epoch unavailable")
        if result == 0:
            raise HTTPException(429, "Request rate exhausted", headers={"Retry-After": str(wait)})

    async def issue(self, body, identity, project, service, discovery=False):
        slot_id = identity["slot_id"] if identity else None
        admin = bool(identity and identity["administrative"])
        ip = str(canonical_ip(body.client_ip))
        async with self.pool.acquire() as conn:
            policies, revisions = await self.policies(conn, project["id"], slot_id)
            if admin:
                if not any(canonical_ip(ip) in net for net in self.admin_networks):
                    raise HTTPException(403, "Administrative transport origin denied")
                policies = [
                    AccessPolicy(
                        geo_mode="unrestricted",
                        allowed_countries=None,
                        allowed_networks=[],
                        rate_limit={"requests_per_second": 20, "burst": 40},
                        request_quota=None,
                    )
                ]
                scopes = [str(project["id"]) + ":admin"]
            elif discovery:
                await self.geographic(policies, ip)
                policies = [
                    AccessPolicy(
                        geo_mode="unrestricted",
                        allowed_countries=None,
                        allowed_networks=[],
                        rate_limit={"requests_per_second": 10, "burst": 20},
                        request_quota=None,
                    )
                ]
                scopes = ["discovery:" + hashlib.sha256(ip.encode()).hexdigest()]
            else:
                await self.geographic(policies, ip)
                scopes = [str(project["id"]) + ":project"] + (
                    [str(project["id"]) + ":" + str(slot_id)] if slot_id else []
                )
            if body.method == "OPTIONS":
                return None
            await self.rate(scopes, policies)
            if not discovery:
                wait = await conn.fetchval(
                    "SELECT consume_access_quota($1,$2,$3)", project["id"], slot_id, admin
                )
                if wait:
                    raise HTTPException(
                        429, "Request quota exhausted", headers={"Retry-After": str(wait)}
                    )
        key_id = str(identity["id"]) if identity else None
        ticket = secrets.token_urlsafe(32)
        value = ticket_binding(body, project["id"], key_id)
        value.update(
            {
                "slot": str(slot_id) if slot_id else None,
                "revisions": revisions,
                "service": service,
                "client_ip": ip,
                "administrative": admin,
                "epoch": self.epoch,
            }
        )
        if not await self.redis.set("access:ticket:" + ticket, json.dumps(value), ex=10, nx=True):
            raise HTTPException(503, "Admission ticket unavailable")
        return ticket

    async def redeem(self, ticket, body, project, identity):
        if len(ticket) != 43 or any(
            c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
            for c in ticket
        ):
            raise HTTPException(403, "Admission ticket required")
        if await self.redis.get("access:epoch") != self.epoch:
            raise HTTPException(503, "Traffic counter epoch unavailable")
        raw = await self.redis.getdel("access:ticket:" + ticket)
        if raw is None:
            raise HTTPException(403, "Admission ticket expired or already used")
        value = json.loads(raw)
        expected = ticket_binding(body, project["id"], str(identity["id"]) if identity else None)
        if any(value[k] != v for k, v in expected.items()) or value["epoch"] != self.epoch:
            raise HTTPException(403, "Admission binding mismatch")
        slot_id = identity["slot_id"] if identity else None
        async with self.pool.acquire() as conn:
            _, revisions = await self.policies(conn, project["id"], slot_id)
        if value["revisions"] != revisions:
            raise HTTPException(403, "Access policy changed after admission")
