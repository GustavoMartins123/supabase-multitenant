import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/api-internal"))
from app.access_policy import AccessPolicy, CATALOG, PolicyUpdate, canonical_ip, parse_policy

BASE = {
    "geo_mode": "unrestricted",
    "allowed_countries": None,
    "allowed_networks": [],
    "rate_limit": None,
    "request_quota": None,
}


class AccessPolicyTests(unittest.TestCase):
    def test_explicit_unrestricted_and_scope(self):
        self.assertEqual(parse_policy(BASE, "project").geo_mode, "unrestricted")
        with self.assertRaises(ValueError):
            parse_policy(BASE, "slot")

    def test_country_catalog_unique_and_attributed(self):
        codes = [c["code"] for c in CATALOG["countries"]]
        self.assertEqual(len(codes), 250)
        self.assertEqual(len(set(codes)), 250)
        self.assertIn("source", CATALOG)

    def test_restricted_geo_denies_unknown_and_empty(self):
        policy = AccessPolicy(**{**BASE, "geo_mode": "restrict", "allowed_countries": ["BR"]})
        self.assertTrue(policy.allows_country("BR"))
        self.assertFalse(policy.allows_country("US"))
        self.assertFalse(policy.allows_country(None))
        self.assertFalse(
            AccessPolicy(
                **{**BASE, "geo_mode": "restrict", "allowed_countries": []}
            ).allows_country("BR")
        )

    def test_explicit_network_and_ipv4_mapped_ipv6(self):
        policy = AccessPolicy(
            **{
                **BASE,
                "geo_mode": "restrict",
                "allowed_countries": [],
                "allowed_networks": ["192.168.0.0/24"],
            }
        )
        self.assertTrue(policy.allows_network("::ffff:192.168.0.108"))
        self.assertFalse(policy.allows_network("10.0.0.1"))
        self.assertEqual(str(canonical_ip("::ffff:1.2.3.4")), "1.2.3.4")
        mapped = AccessPolicy(
            **{
                **BASE,
                "geo_mode": "restrict",
                "allowed_countries": [],
                "allowed_networks": ["::ffff:192.168.0.0/120"],
            }
        )
        self.assertEqual(mapped.allowed_networks, ["192.168.0.0/24"])
        self.assertTrue(mapped.allows_network("192.168.0.108"))

    def test_invalid_policy_never_gets_defaults(self):
        invalid = [
            {},
            {**BASE, "extra": True},
            {**BASE, "geo_mode": "restrict"},
            {**BASE, "geo_mode": "restrict", "allowed_countries": ["ZZ"]},
            {**BASE, "allowed_networks": ["10.0.0.0/8"]},
            {
                **BASE,
                "geo_mode": "restrict",
                "allowed_countries": [],
                "allowed_networks": ["0.0.0.0/0"],
            },
            {
                **BASE,
                "geo_mode": "restrict",
                "allowed_countries": [],
                "allowed_networks": ["10.0.0.1/8"],
            },
            {**BASE, "rate_limit": {"requests_per_second": True, "burst": 10}},
            {**BASE, "rate_limit": {"requests_per_second": 0, "burst": 10}},
            {**BASE, "rate_limit": {"requests_per_second": "10", "burst": 10}},
            {**BASE, "request_quota": {"period": "week", "limit": 1}},
            {**BASE, "request_quota": {"period": "day", "limit": 0}},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_policy(value, "project")

    def test_complete_revisioned_update(self):
        self.assertEqual(PolicyUpdate(revision=1, policy=copy.deepcopy(BASE)).revision, 1)
        for value in (
            {"policy": BASE},
            {"revision": 0, "policy": BASE},
            {"revision": 1, "policy": BASE, "ignored": True},
        ):
            with self.assertRaises(ValueError):
                PolicyUpdate(**value)


if __name__ == "__main__":
    unittest.main()
