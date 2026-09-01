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
            "n": "z02KGhSys-53buuo9yyNIpkqXs1vbbpb63RSdkCTr-U4UPdkr60Y_mhHzIT9BIbwTnHr4nc6B088PxsMf8-mjAfFnmZEMRYJ1wNDLkZpmcCklqK4wRxiohTaiyNCblb9aKNvAw9kZ9UDTcndCv6JaABaYlCO-uUW226fc514N-x34azoAIgQl6JvwIofTddRjorGVpXJ_2wnpcNYQdjxVXsAPpCJttNUxm85SRe-IsBWoZC2t9v8TpxVyUe8b2FvUolgbeJ5w2-mBZG2DSGrTka6SZrdLyLRGp2PM3iltWIlhIMPtSkiMQ1-Ydc0q44wJml1HZgsVOb6MrDDW9Sn-Q",
            "e": "AQAB",
        }
    ]
}

# Pre-generated test tokens (valid for 10 years from Aug 2026)
TOKENS = {
    "admin": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3ODU4NzY5NzYsImV4cCI6MjEwMTIzNjk3Niwic3ViIjoiYWRtaW4tdXNlci1pZCIsIm5hbWUiOiJBZG1pbiBVc2VyIiwiYWRtaW4iOnRydWUsInJvbGUiOiJhZG1pbiJ9.Uk6zMwMXySVNQ3Cn4mAKAYVjJevVYh7zCi9VDojffmhYc0R0-3mZrhwhOQfg76s-zE1r2UZNqaYJAMdfozuDqWa_bn4Y9GDrtpXrCs2XM_N-oEIeSLag1Ki6MG-nQfPzW1vvwJ10JjPRcOk-qjM46OrRgotT4gmfWe9i7xm3l26EtygPaiS4Kux7XJy5LVSIqycRrLMdKwJRKaKJ6vXD8_NnFJKRQQyQCyULRjHRthIUGdiQ-jZDVLt9ZySuLBMzxUKfPSSCiibJct0yZNPjVdWc54t_aUu1jXx--lX5qlY5giwtnVG5Ww0jeD6kMXdmhqI9CWHJfuamznSlYQvgoA",
    "user": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3ODU4NzY5NzYsImV4cCI6MjEwMTIzNjk3Niwic3ViIjoidXNlci1pZCIsIm5hbWUiOiJSZWd1bGFyIFVzZXIiLCJhZG1pbiI6ZmFsc2UsInJvbGUiOiJ1c2VyIn0.GdCavkm5inxF4KA45dhvrCoyhe04qkK14wKhluF4-mktCsPtD4A-lw-M5Oz76QAqMMeS9Kr56BOGuDh0kXOaOiEO6V_7IAqZOlR_34fP_taIBPv3NA753Ql35EgeblC-ohQH_ZzUUJCMvepiuFw1jP1bGDvoqPKlrjYHbwedFEWjrxMJhZo7hM91qU738NnVkaEvAOAOGBkeA_Ho8asR7-5e1XxUS3Z7bXY9o_nqmwnQ-pWWf0litugHfIsgsJ9VLqWWpdlytfScqIMKbhWZuJ7Hgk1zXjW7EHLEkgCGUL-fmDTI4-BxQqSPn8vgNd9HqBNWzBFXcV3XQpgr3AgfHw",
    "viewer": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3ODU4NzY5NzYsImV4cCI6MjEwMTIzNjk3Niwic3ViIjoidmlld2VyLWlkIiwibmFtZSI6IlZpZXdlciBVc2VyIiwiYWRtaW4iOmZhbHNlLCJyb2xlIjoidmlld2VyIn0.tFRd7KDs_ZtNOS3Xnr6eE2dJEqY-MWpJaVH8A8W55gxpvoytp3-EBh1XHpKb3k0Q0qBazJMsss6eat-B7RymlsRaeqAapPiZ3QJssi_sxZcu4JSk-typEDM70rakhYss8JgrYbw5fAQNcpu6y3AqzOQr3MCVcW_sGp-ghTMC0qIbvx8Tcw0wS6Qtlj5hdDyKOxH9IJzlDivU58QCASR_qkc-RySzUQu7dxTGoDmG9UN4XZF1I490TxcQsBDGM9qf7uLm4MnbjFaJJYP86nB-j2166VWVyUyyEN1SIwB3sZ51KUDGpIiTXAld0dPPr2Sqv1lz1qqIGxEpaE1xrzRk7g",
    "query_only": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3ODU4NzY5NzYsImV4cCI6MjEwMTIzNjk3Niwic3ViIjoicXVlcnktaWQiLCJuYW1lIjoiUXVlcnkgVXNlciIsImFkbWluIjpmYWxzZSwicGVybWlzc2lvbnMiOlsicXVlcnkiXX0.oKwNnjiepUzfWxDoVeto9XL96K5uWX_DWMBIb8cde7k8ujU-RUSiGArnmhXfGxOLD0jIqJsJkwVyjeQUNDLGa1hD49v__dWCeDdEbemPI-K3i5jeE1W96igk0MxtOBlkj4SKnDcerY4y93J3lSjDVZsx4nOzJU8jI0T8jT20K0Si-zRtDdcwEtGbu-LFGHHbCea3fRSUls8Vd6NL1rI7-v0m6ztljxEjE2GJSLCKCbngtsJ8ni_lvJBG28Ys7VVOmNiZVF2NdIpFQzmKVCWM_-_A0uH4yXh2JsHGapMJyaleqHzO7bAzLXsUx2mF-U1wJQXBwnpv2kKeuawMXlwJuw",
    "no_role": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3ODU4NzY5NzYsImV4cCI6MjEwMTIzNjk3Niwic3ViIjoibm9yb2xlLWlkIiwibmFtZSI6Ik5vIFJvbGUgVXNlciIsImFkbWluIjpmYWxzZX0.s6aJBlINEiryWJlLuQzObGKNhMapEVNLZAmh6Qxrx8s_KHeyJpzBLedF7qFxDMMJD7M7zuGpPKTvWo1OT4yxl-XLi94QMkfx4-_UlH6bTa1Kq-gWW4xM6q8BpuV2uEAzfSONpX-Cqdys5ywyc9CraiWdkfVVZcy_Z-7mu-D9vs9-3_OIyibqT4P1eKJwrZsICvqdQtRvdcVTwn6ETzJ8jekup-4b5tDcSulj04S1zlCUEKpuYFSs15mviLCAYX2nW_AaOnvQz-fIOA6Q2S8ifm1L85jwef3BWIeLf4ZWwUO_wN_od2pyCkxqiGQxyd3WnBVS-BJxfjdEl10sj2ypog",
    "user2": "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LTEiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3ODU4NzY5NzYsImV4cCI6MjEwMTIzNjk3Niwic3ViIjoidXNlcjItaWQiLCJuYW1lIjoiUmVndWxhciBVc2VyIDIiLCJhZG1pbiI6ZmFsc2UsInJvbGUiOiJ1c2VyIn0.D_rGmLkOjDyFm4NIOdL3eI1dlDbA4nZ7lEpXCGHQF2FGCmkfiyMeBggxihVeC0WOwZbk1PLD2h-9LgpX-g8PhsYPC6c6aG8pFOvUgV8mjn4xKr5Hi7-IopQuOXDd4N7Ea1zW__WTzwciGUNOFTT4c1GrAa2ZQyPibCErCrxtju6Zan_UzUr8tU0wT031HgcYv3JqE33AT6u0RhO94MHQABo0Zl02vkvacTz3EVIfICR_v_LmOxRraIyrzS5-w7UInaBep2EnaY5su2scAcYqpGERVE600SuZUbjLXYfxc7zTFpL0Bub8VqvwLe48QyilH-ylvCopUp4OJ6uIhWHUzw",
}


class Handler(BaseHTTPRequestHandler):
    """Simple HTTP handler for JWKS and tokens."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        match self.path:
            case "/.well-known/jwks.json":
                self._json_response(JWKS)
            case "/tokens":
                self._json_response(TOKENS)
            case "/health":
                self._json_response({"status": "ok"})
            case _:
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
