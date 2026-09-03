#!/usr/bin/env python3
"""One-time script to generate JWKS and test tokens.

Run this once to generate the static values for server.py.
Requires: pip install cryptography PyJWT
"""

import base64
import json
import time

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Generate RSA key pair
private_key = rsa.generate_private_key(
    public_exponent=65537, key_size=2048, backend=default_backend()
)
public_key = private_key.public_key()

# Convert to PEM for JWT signing
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

# Create JWK from public key
public_numbers = public_key.public_numbers()


def int_to_base64url(n: int, length: int) -> str:
    """Convert an integer to base64url-encoded string."""
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


jwk = {
    "kty": "RSA",
    "kid": "test-key-1",
    "use": "sig",
    "alg": "RS256",
    "n": int_to_base64url(public_numbers.n, 256),
    "e": int_to_base64url(public_numbers.e, 3),
}

# Token claims for each role
now = int(time.time())
exp = now + (10 * 365 * 24 * 3600)  # 10 years

roles = {
    "admin": {
        "sub": "admin-user-id",
        "name": "Admin User",
        "admin": True,
        "role": "admin",
    },
    "user": {"sub": "user-id", "name": "Regular User", "admin": False, "role": "user"},
    "viewer": {
        "sub": "viewer-id",
        "name": "Viewer User",
        "admin": False,
        "role": "viewer",
    },
    "query_only": {
        "sub": "query-id",
        "name": "Query User",
        "admin": False,
        "permissions": ["query"],
    },
    "no_role": {"sub": "norole-id", "name": "No Role User", "admin": False},
}

tokens = {}
for role, claims in roles.items():
    payload = {"iat": now, "exp": exp, **claims}
    tokens[role] = jwt.encode(
        payload, private_pem, algorithm="RS256", headers={"kid": "test-key-1"}
    )

print("=== JWKS ===")
print(json.dumps({"keys": [jwk]}, indent=2))
print("\n=== TOKENS ===")
print(json.dumps(tokens, indent=2))
