import unittest
import httpx
from desktop.sync_transport import SyncTransport


class TransportTests(unittest.TestCase):
    def test_requires_secure_origin(self):
        for origin in ('http://example.org', 'https://user:pass@example.org', 'https://example.org/path', 'https://example.org?token=x'):
            with self.assertRaises(ValueError):
                SyncTransport(origin, 'device-token')

    def test_redirect_does_not_forward_credentials(self):
        transport = SyncTransport('https://sync.example.org', 'device-token')
        self.addCleanup(transport.close)
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(307, headers={'location': 'https://other.example.org/'})
        transport._client.close()
        transport._client = httpx.Client(transport=httpx.MockTransport(respond), base_url='https://sync.example.org', follow_redirects=False)
        with self.assertRaises(httpx.HTTPStatusError):
            transport({'operation_id': 'test'})
        self.assertEqual(len(calls), 1)
