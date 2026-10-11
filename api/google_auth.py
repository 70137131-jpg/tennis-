"""Google authorization-code flow, using state, PKCE, and verified OpenID claims."""

import base64
import hashlib
import os
from functools import partial
from urllib.parse import urlencode, urlsplit

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def settings():
    client_id = os.environ.get("COURTSIDE_GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("COURTSIDE_GOOGLE_CLIENT_SECRET", "").strip()
    origin = os.environ.get("COURTSIDE_ORIGIN", "").rstrip("/")
    if not client_id and not secret:
        return None
    parsed = urlsplit(origin)
    if not client_id or not secret or not parsed.hostname or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Set Google client ID, secret, and COURTSIDE_ORIGIN together")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Google sign-in requires HTTPS, except on localhost")
    return client_id, secret, origin


def authorize_url(config, state, verifier):
    client_id, _, origin = config
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": origin + "/api/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    })


def exchange_code(config, code, verifier):
    client_id, secret, origin = config
    response = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": secret,
        "redirect_uri": origin + "/api/auth/google/callback",
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }, timeout=10, allow_redirects=False)
    response.raise_for_status()
    token = response.json().get("id_token")
    if not isinstance(token, str) or len(token) > 20000:
        raise ValueError("Google did not return an identity token")
    claims = id_token.verify_oauth2_token(token, partial(Request(), timeout=10), client_id)
    if claims.get("email_verified") is not True or claims.get("azp", client_id) != client_id:
        raise ValueError("Google account identity could not be confirmed")
    if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("email"), str):
        raise ValueError("Google account identity is incomplete")
    return claims
