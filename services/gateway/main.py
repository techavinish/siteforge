"""SiteForge gateway — the only door to the backend.

Every request must carry a Firebase ID token. We verify its signature
against Google's public keys (via firebase-admin), so a forged or expired
token is rejected before any business logic runs.
"""

import firebase_admin
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import auth

# On GCP this picks up the service account automatically (ADC);
# locally it uses your `gcloud auth application-default login`.
firebase_admin.initialize_app(options={"projectId": "siteforge-dev-3977"})

app = FastAPI(title="siteforge-gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://siteforge-dev-3977.web.app"],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


def current_user(request: Request) -> dict:
    """FastAPI dependency: extracts and verifies the Bearer ID token."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return auth.verify_id_token(header.removeprefix("Bearer "))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@app.get("/healthz")
def healthz():
    import os

    return {"ok": True, "rev": os.environ.get("GIT_SHA", "local")}


@app.get("/api/me")
def me(claims: dict = Depends(current_user)):
    return {
        "uid": claims["uid"],
        "email": claims.get("email", ""),
        "name": claims.get("name", ""),
        "picture": claims.get("picture", ""),
        "verified_by": "siteforge-gateway (signature checked server-side)",
    }
