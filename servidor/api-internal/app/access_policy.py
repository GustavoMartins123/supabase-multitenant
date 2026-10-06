"""Canonical validation for project and consumer-slot admission policies."""

from __future__ import annotations

import ipaddress
import json
import datetime as dt
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATALOG = json.loads((Path(__file__).parent / "data/countries.json").read_text(encoding="utf-8"))
COUNTRY_CODES = frozenset(country["code"] for country in CATALOG["countries"])


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RateLimit(PolicyModel):
    requests_per_second: int = Field(ge=1, le=100000)
    burst: int = Field(ge=1, le=1000000)


class RequestQuota(PolicyModel):
    period: Literal["day", "month"]
    limit: int = Field(ge=1, le=1000000000000)


class AccessPolicy(PolicyModel):
    geo_mode: Literal["unrestricted", "inherit", "restrict"]
    allowed_countries: list[str] | None
    allowed_networks: list[str] = Field(max_length=128)
    rate_limit: RateLimit | None
    request_quota: RequestQuota | None

    @field_validator("allowed_countries")
    @classmethod
    def countries(cls, values):
        if values is None:
            return None
        if len(values) > len(COUNTRY_CODES) or any(code not in COUNTRY_CODES for code in values):
            raise ValueError("Invalid ISO country code")
        return sorted(set(values))

    @field_validator("allowed_networks")
    @classmethod
    def networks(cls, values):
        normalized = []
        for value in values:
            network = ipaddress.ip_network(value, strict=True)
            if isinstance(network, ipaddress.IPv6Network) and network.network_address.ipv4_mapped:
                network = ipaddress.ip_network(
                    (network.network_address.ipv4_mapped, network.prefixlen - 96), strict=True
                )
            if network.prefixlen == 0:
                raise ValueError("An unrestricted network must use unrestricted geography")
            normalized.append(str(network))
        return sorted(set(normalized))

    @model_validator(mode="after")
    def consistent_geography(self):
        if self.geo_mode == "restrict":
            if self.allowed_countries is None:
                raise ValueError("Restricted geography requires an explicit country list")
        elif self.allowed_countries is not None or self.allowed_networks:
            raise ValueError("Inherited/unrestricted geography cannot contain restrictions")
        return self

    def for_scope(self, scope: Literal["project", "slot"]) -> AccessPolicy:
        if (scope == "project" and self.geo_mode == "inherit") or (
            scope == "slot" and self.geo_mode == "unrestricted"
        ):
            raise ValueError("Geographic mode is not valid for this scope")
        return self

    def allows_network(self, ip: str) -> bool:
        address = canonical_ip(ip)
        return any(address in ipaddress.ip_network(value) for value in self.allowed_networks)

    def allows_country(self, country: str | None) -> bool:
        return self.geo_mode != "restrict" or (
            country is not None and self.allowed_countries is not None and country in self.allowed_countries
        )


def canonical_ip(value: str):
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def parse_policy(raw, scope: Literal["project", "slot"]) -> AccessPolicy:
    value = json.loads(raw) if isinstance(raw, str) else raw
    return AccessPolicy.model_validate(value).for_scope(scope)


class PolicyUpdate(PolicyModel):
    revision: int = Field(ge=1, le=9007199254740991)
    policy: AccessPolicy


class PolicyResponse(BaseModel):
    scope: Literal["project", "slot"]
    scope_id: str
    revision: int
    policy: AccessPolicy
    project_policy: AccessPolicy
    updated_at: str


class CountryItem(BaseModel):
    code: str
    name: str
    name_en: str


class CountryCatalog(BaseModel):
    version: int
    source: str
    countries: list[CountryItem]


class AccessUsageRow(BaseModel):
    scope_id: uuid.UUID
    scope_type: Literal["project", "slot", "admin"]
    period: Literal["day", "month"]
    period_start: dt.datetime
    period_end: dt.datetime
    admitted: int


class AccessUsageResponse(BaseModel):
    usage: list[AccessUsageRow]


async def copy_project_access_policy(conn, source_id, destination_id, actor_id):
    row = await conn.fetchrow(
        "SELECT policy FROM project_access_policies WHERE project_id=$1 FOR SHARE", source_id
    )
    if row is None:
        raise ValueError("Source project access policy is unavailable")
    policy = parse_policy(row["policy"], "project")
    result = await conn.execute(
        "UPDATE project_access_policies SET policy=$2::jsonb, updated_by=$3, updated_at=now() WHERE project_id=$1",
        destination_id,
        policy.model_dump_json(),
        actor_id,
    )
    if result != "UPDATE 1":
        raise ValueError("Destination project access policy is unavailable")


async def copy_matching_slot_access_policies(conn, source_id, destination_id, actor_id):
    slots = await conn.fetch(
        """SELECT target.id AS destination, original.id AS source
        FROM project_api_key_slots target JOIN project_api_key_slots original
        ON original.name=target.name AND original.kind=target.kind
        WHERE target.project_id=$1 AND original.project_id=$2 ORDER BY original.id""",
        destination_id,
        source_id,
    )
    for slot in slots:
        row = await conn.fetchrow(
            "SELECT policy FROM slot_access_policies WHERE slot_id=$1 FOR SHARE", slot["source"]
        )
        if row is None:
            raise ValueError("Source consumer access policy is unavailable")
        policy = parse_policy(row["policy"], "slot")
        result = await conn.execute(
            "UPDATE slot_access_policies SET policy=$2::jsonb,updated_by=$3,updated_at=now() WHERE slot_id=$1",
            slot["destination"],
            policy.model_dump_json(),
            actor_id,
        )
        if result != "UPDATE 1":
            raise ValueError("Destination consumer access policy is unavailable")
