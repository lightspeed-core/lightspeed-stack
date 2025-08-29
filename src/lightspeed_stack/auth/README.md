# List of source files stored in `src/auth` directory

## [__init__.py](__init__.py)
This package contains authentication code and modules.

## [interface.py](interface.py)
Abstract base class for all authentication method implementations.

## [jwk_token.py](jwk_token.py)
Manage authentication flow for FastAPI endpoints with JWK based JWT auth.

## [k8s.py](k8s.py)
Manage authentication flow for FastAPI endpoints with K8S/OCP.

## [noop.py](noop.py)
Manage authentication flow for FastAPI endpoints with no-op auth.

## [noop_with_token.py](noop_with_token.py)
Manage authentication flow for FastAPI endpoints with no-op auth and provided user token.

## [utils.py](utils.py)
Authentication utility functions.

