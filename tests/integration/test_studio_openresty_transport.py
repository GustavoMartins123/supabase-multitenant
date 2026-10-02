"""Use the real OpenResty harness; authorization separately uses PostgreSQL tests."""
import json
import os
import unittest
import urllib.request
import urllib.error


@unittest.skipUnless(os.environ.get("STUDIO_TRANSPORT_TEST_URL"), "Start the disposable OpenResty harness")
class StudioOpenRestyTransportTest(unittest.TestCase):
    def request(self, resource, actor="admin"):
        url = os.environ["STUDIO_TRANSPORT_TEST_URL"] + "/api/platform/projects/demo/api/" + resource
        return urllib.request.urlopen(urllib.request.Request(url, headers={"X-Test-Actor": actor}), timeout=5)

    def test_rest_resource_and_query_are_preserved_and_opaque_key_is_injected(self):
        with self.request("rest/orders?select=id&limit=2") as response:
            body=json.load(response)
        self.assertEqual(body["uri"], "/demo/rest/v1/orders")
        self.assertEqual(body["args"], "select=id&limit=2")
        self.assertTrue(body["opaque"])
        self.assertTrue(body["administrative"])

    def test_graphql_has_canonical_uri_and_administrative_opaque_key(self):
        with self.request("graphql") as response:
            body=json.load(response)
        self.assertEqual(body["uri"], "/demo/graphql/v1")
        self.assertTrue(body["opaque"])
        self.assertTrue(body["administrative"])

    def test_denied_actor_is_not_proxied(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("rest/orders", actor="member")
        self.assertEqual(error.exception.code, 403)
