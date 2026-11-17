from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, bearer, sign_in


def test_sign_in_and_me(client):
    body = sign_in(client, email="  ADA@acme.test ")
    assert body["must_set_password"] is False
    me = client.get("/me", headers=bearer(body["token"])).json()
    assert me["email"] == ADMIN_EMAIL
    assert me["role"] == "admin"


def test_wrong_password_and_unknown_email(client):
    sign_in(client, password="nope", expect=401)
    sign_in(client, email="who@acme.test", expect=401)


def test_requests_without_valid_token_are_rejected(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=bearer("garbage")).status_code == 401


def test_rate_limit_allows_five_tries_a_minute(client, clock):
    for _ in range(5):
        sign_in(client, password="wrong", expect=401)
    sign_in(client, expect=429)
    clock.advance(seconds=59)
    sign_in(client, expect=429)
    clock.advance(seconds=1)
    sign_in(client)


def test_rate_limit_is_per_address(client):
    for _ in range(5):
        sign_in(client, email="other@acme.test", password="x", expect=401)
    sign_in(client)


def test_sign_out_ends_session(client):
    token = sign_in(client)["token"]
    assert client.post("/auth/sign-out", headers=bearer(token)).status_code == 204
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_session_slides_while_used_and_expires_when_idle(client, clock):
    token = sign_in(client)["token"]
    clock.advance(hours=11)
    assert client.get("/me", headers=bearer(token)).status_code == 200
    clock.advance(hours=11)
    assert client.get("/me", headers=bearer(token)).status_code == 200
    clock.advance(hours=13)
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_list_and_revoke_own_sessions(client):
    first = sign_in(client)["token"]
    second = sign_in(client)["token"]
    listed = client.get("/me/sessions", headers=bearer(first)).json()
    assert len(listed) == 2
    newest = listed[0]["id"]
    assert client.delete(f"/me/sessions/{newest}", headers=bearer(first)).status_code == 204
    assert client.get("/me", headers=bearer(second)).status_code == 401
    assert client.get("/me", headers=bearer(first)).status_code == 200


def test_change_own_password_needs_current_one(client):
    token = sign_in(client)["token"]
    other = sign_in(client)["token"]
    bad = client.post("/me/password", json={"current_password": "nope", "new_password": "an even longer one"}, headers=bearer(token))
    assert bad.status_code == 401
    weak = client.post("/me/password", json={"current_password": ADMIN_PASSWORD, "new_password": "short"}, headers=bearer(token))
    assert weak.status_code == 422

    ok = client.post("/me/password", json={"current_password": ADMIN_PASSWORD, "new_password": "an even longer one"}, headers=bearer(token))
    assert ok.status_code == 204
    assert client.get("/me", headers=bearer(token)).status_code == 200
    assert client.get("/me", headers=bearer(other)).status_code == 401
    sign_in(client, password="an even longer one")
