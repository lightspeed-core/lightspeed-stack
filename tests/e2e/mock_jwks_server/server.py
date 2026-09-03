#!/usr/bin/env python3
"""Simple mock JWKS server for E2E RBAC tests.

Serves static pre-generated JWKS and test tokens.
No external dependencies - uses only Python stdlib.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

# Static JWKS - pre-generated RSA public key
JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "kid": "test-key-1",
            "use": "sig",
            "alg": "RS256",
            "n": "oYVHa2Map44Cbd32Ai_37P0CHnRqDU3U3MKNdHIBkkI9nl3VV1K-4GqyKmTHl6CfSDUh5_JrKJJblyY-u7MOB9kzrPn-7it2FBfmhnc8RNBRvvF2ti3_IC-an3-2t_qYP30ZtkTx4EtgbBhd6iCJFjDU6Rjl9fxtYG-jZR_91UDOyJSQnVCV9-1oRWhkA_5y6l1gNKu-Kc92Kmu39fhxOs4U8399MPI-RkGcJkGRP86xg9lNx1Linz7UzEENGvYhPf2peaUvCZSElSZcgy_EFI3Tag9-nSTDCZPmxv1ugAohMGIgtQtmBI-K30_1Mek_RPwMOXh2EX5ThVhvIbXXmw",
            "e": "AQAB",
        }
    ]
}

# Pre-generated test tokens (valid for 10 years from Jan 2026)
TOKENS = {
    "admin": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3NjgzNzkzMDcsImV4cCI6MjA4MzczOTMwNywic3ViIjoiYWRtaW4tdXNlci1pZCIsIm5hbWUiOiJBZG1pbiBVc2VyIiwiYWRtaW4iOnRydWUsInJvbGUiOiJhZG1pbiJ9.BFVQDG6Io59q3gYwt54c2NJEI5q3MUIXwRIlPhu3v1F9inrZOPtLKBUbjgkF6OpU5xe5ck09BsKwvuNX0gBS8iVHb4vetkd2hwqDljk8wHEOs_E8X4_3Yqoz5NFgs1Mx3fd66xuWy2TtwLaIZ3Mwx6aGERZBXBvY_5yP7HI2oUQ4jVHe6TZL4qa927YFXtNZv11DBq9FkrZRaFtACt6iikEA-UD-v4N1szWlBvn_JCsmB9gQc8txN8FfNH_h01qTJWfuqBbK-6pSpgjr9pS4dG3AuFpBucp-eaBDCGlC7kz085_I10hnZhGCoB7XD1VOTILtwdMvjB_6VFd4f-0EiQ",
    "user": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3NjgzNzkzMDcsImV4cCI6MjA4MzczOTMwNywic3ViIjoidXNlci1pZCIsIm5hbWUiOiJSZWd1bGFyIFVzZXIiLCJhZG1pbiI6ZmFsc2UsInJvbGUiOiJ1c2VyIn0.eocDRnf8Cbw1wEee3mmZGDyPlUGAFN8-dH9LmEChAYSSQ6g94vRhL4yoQCiDJA76Vuzmt9CJKGxHNlvmqZh82rEPezLDq0H_a3qgPZq_9uS_dzl3c-ityojbI0YBE1DWm_29vhEv9lfVaJc9EalSObN5xttq32GJ8-1kFWATgP--n5SP3omoljLxAmVMlQlU2gjB7trH7OyLLHp4-DqsUzUUXsNg1pj-BmWT7pkw36QjRfintX-GEcSMbHABX0g2CXUKuLAWsqbbyLPPtDPlPFQh6HmZna74-riWJqOYg6pL4XSUwl_DKxafjZ_wCysSULUjR_i2E6XlgBlIRAZC5A",
    "viewer": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3NjgzNzkzMDcsImV4cCI6MjA4MzczOTMwNywic3ViIjoidmlld2VyLWlkIiwibmFtZSI6IlZpZXdlciBVc2VyIiwiYWRtaW4iOmZhbHNlLCJyb2xlIjoidmlld2VyIn0.a_6FLiAw9cg-hUNNtdv1WyQtwkMJCmMnXXB1fOcGNyjgYSL-z3-bW12FOGH86MTxdcXKxsvfaw5FrUqOZVUitlo3AjqFdZJaZkKJO23-eMvWwaCME90wPkM6nW0L95nygkko8SkX4WWoccPBqqDRG3QxzsBxq6Lu7NdSnpz2iGlZcYwmCZdIhmBqgxuQbUPeMQlxJtoiv6AUXA8lMJbHAcftrwoQ2oWVKIRwjK4VHn-s8G5HzK3ezlDKz31kNxg74rQo4jZzlRkWVHQ2wByabyaRGCysoM7KrNuCJwjs4W_tShb9nM50zTc_jrcjeur3LbtDt3XOPNyKpVxElpAgYw",
    "query_only": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3NjgzNzkzMDcsImV4cCI6MjA4MzczOTMwNywic3ViIjoicXVlcnktaWQiLCJuYW1lIjoiUXVlcnkgVXNlciIsImFkbWluIjpmYWxzZSwicGVybWlzc2lvbnMiOlsicXVlcnkiXX0.fOEEnWhVajeBSGxxMhzmcHPJ1ZWoDrz-JgFGngoanbEA8NGoQcNnbZvnDGg_Jn6_4YtFwQ5NnVb50lZSw046HapLPRfbQsz2yxCzW1FaX2Jvc8-d8kciZPh_aWwxv2foAEii_8hG9ZisRvUIDoBUHmtJdxGcRcilgXywIc4BS15Cxi-Ib7RPkqsKN56vIy30-vTeV0bwcAXVjmpPiekIrFqZX-rLpFptjouSdBTF8PEvh_K1pmFteMfe1QJzonDYYNdMTOsQRy-c0KH9fX7oWhw9xJvvTlh0pDZbh1zAk6EYeiSCavq6myxRGyImNT0wQ7IuzWywsBUmLauRxf6W5Q",
    "no_role": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3NjgzNzkzMDcsImV4cCI6MjA4MzczOTMwNywic3ViIjoibm9yb2xlLWlkIiwibmFtZSI6Ik5vIFJvbGUgVXNlciIsImFkbWluIjpmYWxzZX0.jBpNj3HKfSwMNED8J-o3A847aJg7LBDiHJeEB_tRUYJZhd4U6wMv2iun7fpdkns6b-70qtVqOd8xd-BUOsiXNpldjVWI8GaXsqh0q63X622ZYGItMWX0BGgwg2LoQgmN2G1k0xQIs1unCQn0wDmSB6ZFBAMDDSYLpZ0KOLNknh5NUX4GJyMXYgz3FZj6my0ypxWOnmOmC4iL5HGUszq6GB-K7nu75TMOuMZh4FxhbxIvWoT59y-NVKzoTxrkU4w6s0_gfcbqjieJd0sJbp-T4xm3qap7PF4yuFjwkptfbT_hiwAgbOsguTE1LbZQXOz0tdzuORQq7J9skyt2LCjV7w",
}


class Handler(BaseHTTPRequestHandler):
    """Simple HTTP handler for JWKS and tokens."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/.well-known/jwks.json":
            self._json_response(JWKS)
        elif self.path == "/tokens":
            self._json_response(TOKENS)
        elif self.path == "/health":
            self._json_response({"status": "ok"})
        else:
            self.send_error(404)

    def _json_response(self, data: dict) -> None:
        """Send JSON response."""
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress request logging."""


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print("Mock JWKS server on :8000")
    server.serve_forever()
