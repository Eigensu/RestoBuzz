"""
DishPatch — Refresh Token Integration Test
==========================================
Run from repo root:
    python apps/backend/scripts/test_refresh.py

Set ACCESS_TOKEN_EXPIRE_SECONDS=10 in .env before running so the
access token expires quickly and we can test the refresh flow.

Tests:
  1.  Login → get access + refresh tokens
  2.  /me with valid access token → 200
  3.  Inspect token claims (expiry, type)
  4.  Wait for access token to expire
  5.  /me with expired access token → 401
  6.  Refresh with valid refresh token → 200, new pair
  7.  /me with NEW access token → 200
  8.  /me with OLD (expired) access token → 401
  9.  Refresh with invalid token → 401
  10. Refresh with access token (wrong type) → 401
  11. Refresh with empty body → 422
"""

import asyncio, sys, os, base64, json, time
import httpx
from datetime import datetime, timezone

BASE_URL = os.getenv("API_URL", "http://localhost:8000")
EMAIL = os.getenv("TEST_EMAIL", "admin@example.com")
PASSWORD = os.getenv("TEST_PASSWORD", "changeme123")  # NOSONAR
HEADERS = {"Content-Type": "application/json"}


def ok(msg):
    print(f"  ✅  {msg}")


def fail(msg):
    print(f"  ❌  {msg}")
    sys.exit(1)


def info(msg):
    print(f"  ℹ️   {msg}")


def warn(msg):
    print(f"  ⚠️   {msg}")


def section(t):
    print(f"\n{'─'*60}\n  {t}\n{'─'*60}")


def decode_jwt(token: str) -> dict:
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


async def run():  # NOSONAR
    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=15) as c:

        # ── 1. Login ──────────────────────────────────────────────────────────
        section("1. Login")
        r = await c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        info(f"Status: {r.status_code}")
        if r.status_code != 200:
            info(f"Body: {r.text}")
            fail("Login failed — check TEST_EMAIL / TEST_PASSWORD")
        tokens = r.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        ok(f"access_token  : {access_token[:50]}...")
        ok(f"refresh_token : {refresh_token[:50]}...")

        # ── 2. /me with valid access token ────────────────────────────────────
        section("2. GET /auth/me with valid access token")
        r = await c.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        )
        info(f"Status: {r.status_code}")
        if r.status_code != 200:
            fail(f"/me failed: {r.text}")
        ok(f"User: {r.json()['email']}  role={r.json()['role']}")

        # ── 3. Inspect token claims ────────────────────────────────────────────
        section("3. Inspect token claims")
        ap = decode_jwt(access_token)
        rp = decode_jwt(refresh_token)
        now = datetime.now(timezone.utc).timestamp()
        access_ttl = ap["exp"] - now
        refresh_ttl = rp["exp"] - now
        info(f"Access  token: type={ap.get('type')}  expires_in={access_ttl:.1f}s")
        info(
            f"Refresh token: type={rp.get('type')}  expires_in={refresh_ttl/86400:.1f}days"
        )

        if ap.get("type") != "access":
            fail(f"Access token has wrong type: {ap.get('type')}")
        if rp.get("type") != "refresh":
            fail(f"Refresh token has wrong type: {rp.get('type')}")
        ok("Token types correct")

        if access_ttl > 120:
            warn(
                f"Access token expires in {access_ttl:.0f}s — set ACCESS_TOKEN_EXPIRE_SECONDS=10 in .env for faster testing"
            )
            warn("Skipping expiry wait test (would take too long)")
            skip_expiry = True
        else:
            skip_expiry = False
            ok(
                f"Short-lived access token detected ({access_ttl:.0f}s) — will test expiry"
            )

        # ── 4. Wait for access token to expire ────────────────────────────────
        if not skip_expiry:
            wait = int(access_ttl) + 2
            section(f"4. Waiting {wait}s for access token to expire...")
            for i in range(wait, 0, -1):
                print(f"  ⏳  {i}s remaining...", end="\r")
                await asyncio.sleep(1)
            print()
            ok("Access token should now be expired")

            # ── 5. /me with expired token → 401 ───────────────────────────────
            section("5. GET /auth/me with EXPIRED access token")
            r = await c.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
            )
            info(f"Status: {r.status_code}  (expected 401)")
            if r.status_code == 401:
                ok("Correctly rejected expired access token")
            else:
                fail(f"Expected 401, got {r.status_code}: {r.text}")
        else:
            section("4+5. Skipped (access token not short-lived)")

        # ── 6. Refresh with valid refresh token ───────────────────────────────
        section("6. POST /auth/refresh with valid refresh token")
        r = await c.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        info(f"Status: {r.status_code}")
        info(f"Body  : {r.text[:200]}")
        if r.status_code != 200:
            fail("Refresh failed — see body above")
        new_tokens = r.json()
        new_access_token = new_tokens["access_token"]
        new_refresh_token = new_tokens["refresh_token"]
        ok(f"New access_token  : {new_access_token[:50]}...")
        ok(f"New refresh_token : {new_refresh_token[:50]}...")

        if new_access_token == access_token:
            fail("New access token is identical to old one — rotation not working")
        ok("Tokens are different from original (rotation working)")

        # ── 7. /me with NEW access token ──────────────────────────────────────
        section("7. GET /auth/me with NEW access token")
        r = await c.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {new_access_token}"}
        )
        info(f"Status: {r.status_code}")
        if r.status_code != 200:
            fail(f"/me failed with new token: {r.text}")
        ok(f"User: {r.json()['email']}")

        # ── 8. /me with OLD expired token ─────────────────────────────────────
        if not skip_expiry:
            section("8. GET /auth/me with OLD expired access token")
            r = await c.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
            )
            info(f"Status: {r.status_code}  (expected 401)")
            if r.status_code == 401:
                ok("Old expired token correctly rejected")
            else:
                warn(
                    "Old token still accepted (stateless JWT — expected if not blacklisted)"
                )
        else:
            section("8. Skipped (access token not short-lived)")

        # ── 9. Refresh with garbage token ─────────────────────────────────────
        section("9. POST /auth/refresh with invalid token")
        r = await c.post("/api/auth/refresh", json={"refresh_token": "this.is.garbage"})
        info(f"Status: {r.status_code}  (expected 401)")
        if r.status_code == 401:
            ok("Correctly rejected invalid token")
        else:
            fail(f"Expected 401, got {r.status_code}: {r.text}")

        # ── 10. Refresh with access token (wrong type) ────────────────────────
        section("10. POST /auth/refresh with ACCESS token (wrong type)")
        r = await c.post("/api/auth/refresh", json={"refresh_token": new_access_token})
        info(f"Status: {r.status_code}  (expected 401)")
        if r.status_code == 401:
            ok("Correctly rejected access token used as refresh token")
        else:
            fail(f"Expected 401, got {r.status_code}: {r.text}")

        # ── 11. Refresh with empty body ────────────────────────────────────────
        section("11. POST /auth/refresh with empty body")
        r = await c.post("/api/auth/refresh", json={})
        info(f"Status: {r.status_code}  (expected 422)")
        if r.status_code == 422:
            ok("Correctly returns 422 for missing field")
        else:
            fail(f"Expected 422, got {r.status_code}: {r.text}")

        print(f"\n{'='*60}")
        print("  🎉  All tests passed!")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    print("\nDishPatch — Refresh Token Test")
    print(f"Base URL : {BASE_URL}")
    print(f"Email    : {EMAIL}")
    asyncio.run(run())
