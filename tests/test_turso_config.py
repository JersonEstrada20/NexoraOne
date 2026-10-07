import unittest
from scripts.check_turso import endpoint


class TursoEndpointTests(unittest.TestCase):
    def test_cloud_endpoint(self):
        self.assertEqual(endpoint("libsql://example.turso.io"), "https://example.turso.io/v2/pipeline")

    def test_rejects_credential_leaks_and_other_hosts(self):
        for value in ("http://example.turso.io", "https://evil.test", "https://example.turso.io?token=secret",
                      "https://user:secret@example.turso.io", "https://example.turso.io/path", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                endpoint(value)
