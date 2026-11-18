"""HTTPS transport for the v1 protocol; tokens stay outside journal payloads."""
from urllib.parse import urlsplit

import httpx


class SyncTransport:
    def __init__(self, origin: str, token: str):
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('An HTTPS origin without credentials or path is required')
        if not token or any(c.isspace() for c in token):
            raise ValueError('Invalid device token')
        self._client = httpx.Client(
            base_url=origin.rstrip('/'), timeout=15, follow_redirects=False,
            trust_env=False, headers={'Authorization': 'Bearer ' + token},
        )

    def __call__(self, operation: dict) -> dict:
        response = self._client.post('/api/sync/v1/batch', json={'operations': [operation]})
        response.raise_for_status()
        results = response.json().get('results')
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise ValueError('Invalid sync response')
        return results[0]

    def set_snapshot_operations(self, operation_ids):
        self._snapshot_operations = list(operation_ids)

    def snapshot(self, cursor=None):
        response = self._client.get('/api/sync/v1/snapshot', params={'cursor': cursor or '', 'operation_ids': ','.join(getattr(self, '_snapshot_operations', []))})
        response.raise_for_status()
        return response.json()

    def close(self):
        self._client.close()
