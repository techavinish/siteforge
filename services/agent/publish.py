"""deploy_site — publishes a rendered site to Firebase Hosting.

Each business gets its own Hosting site (sf-<slug>-<rand>.web.app) inside
our GCP project, created programmatically. The documents uploaded are the
output of render.py in "live" mode — byte-identical structure to what the
preview shows.

NOTE (from the design review): Firebase caps 36 sites per project. This
module is the SiteDeployer seam — swapping to GCS+CDN later changes only
this file.
"""

import gzip
import hashlib
import os
import re
import secrets

import google.auth
import requests
from google.auth.transport.requests import Request as GRequest

from render import build_site_html

PROJECT = os.environ.get("GCP_PROJECT", "siteforge-dev-3977")
API = "https://firebasehosting.googleapis.com/v1beta1"


def _headers() -> dict:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(GRequest())
    return {"Authorization": f"Bearer {creds.token}"}


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    base = re.sub(r"-+", "-", base)[:20].strip("-")  # 'ink--iron' breaks hosting
    return f"sf-{base or 'site'}-{secrets.token_hex(2)}"


def publish_site(spec: dict, pages: dict, site_id: str | None = None) -> tuple[str, str]:
    """Renders every page in live mode and releases it. Returns (site_id, url)."""
    h = _headers()

    if not site_id:
        site_id = _slug(spec.get("site_name", "site"))
        r = requests.post(
            f"{API}/projects/{PROJECT}/sites",
            params={"siteId": site_id},
            headers=h,
            timeout=30,
        )
        if r.status_code not in (200, 409):  # 409 = already exists, fine
            raise RuntimeError(f"site create failed: {r.status_code} {r.text[:200]}")

    site = f"projects/{PROJECT}/sites/{site_id}"

    # hosting wants /path/index.html layout for pretty urls
    files: dict[str, bytes] = {}
    for path in pages:
        html = build_site_html(spec, pages, path, mode="live").encode()
        fname = "/index.html" if path == "/" else f"{path}/index.html"
        files[fname] = gzip.compress(html, 9)
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}

    version = requests.post(f"{API}/{site}/versions", headers=h, timeout=30).json()["name"]

    pop = requests.post(
        f"{API}/{version}:populateFiles",
        headers=h,
        json={"files": hashes},
        timeout=60,
    ).json()

    upload_url = pop.get("uploadUrl")
    for name, digest in hashes.items():
        if digest in pop.get("uploadRequiredHashes", []):
            requests.post(
                f"{upload_url}/{digest}",
                headers={**h, "Content-Type": "application/octet-stream"},
                data=files[name],
                timeout=120,
            ).raise_for_status()

    requests.patch(
        f"{API}/{version}",
        params={"updateMask": "status"},
        headers=h,
        json={"status": "FINALIZED"},
        timeout=30,
    ).raise_for_status()

    requests.post(
        f"{API}/{site}/releases",
        params={"versionName": version},
        headers=h,
        timeout=30,
    ).raise_for_status()

    return site_id, f"https://{site_id}.web.app"
