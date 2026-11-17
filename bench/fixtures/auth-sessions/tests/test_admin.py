from conftest import bearer, invite, join, sign_in


def test_invite_then_first_sign_in_requires_new_password(client, admin_token):
    inv = invite(client, admin_token)
    assert inv["invite"]["status"] == "pending"
    first = sign_in(client, "bo@acme.test", inv["temporary_password"])
    assert first["must_set_password"] is True

    token = first["token"]
    assert client.get("/me", headers=bearer(token)).json()["status"] == "active"
    assert client.get("/me/sessions", headers=bearer(token)).status_code == 403

    assert client.post("/me/password", json={"new_password": "my own long passphrase"}, headers=bearer(token)).status_code == 204
    assert client.get("/me/sessions", headers=bearer(token)).status_code == 200
    sign_in(client, "bo@acme.test", inv["temporary_password"], expect=401)
    sign_in(client, "bo@acme.test", "my own long passphrase")


def test_inviting_an_existing_member_is_refused(client, admin_token):
    join(client, admin_token)
    resp = client.post("/admin/invites", json={"email": "BO@acme.test", "display_name": "Bo"}, headers=bearer(admin_token))
    assert resp.status_code == 409


def test_revoke_pending_invite(client, admin_token):
    inv = invite(client, admin_token)
    resp = client.post(f"/admin/invites/{inv['invite']['id']}/revoke", headers=bearer(admin_token))
    assert resp.json()["status"] == "revoked"
    again = client.post(f"/admin/invites/{inv['invite']['id']}/revoke", headers=bearer(admin_token))
    assert again.status_code == 409


def test_expired_invite_cannot_be_used(client, admin_token, clock):
    inv = invite(client, admin_token)
    clock.advance(days=8)
    sign_in(client, "bo@acme.test", inv["temporary_password"], expect=403)


def test_admin_reset_signs_user_out_and_forces_new_password(client, admin_token):
    user_id, bo_token = join(client, admin_token)
    reset = client.post(f"/admin/users/{user_id}/reset-password", headers=bearer(admin_token))
    temp = reset.json()["temporary_password"]

    assert client.get("/me", headers=bearer(bo_token)).status_code == 401
    sign_in(client, "bo@acme.test", "a long new password", expect=401)
    fresh = sign_in(client, "bo@acme.test", temp)
    assert fresh["must_set_password"] is True
    assert client.post("/me/password", json={"new_password": "another long password"}, headers=bearer(fresh["token"])).status_code == 204


def test_reset_of_invited_user_is_refused(client, admin_token):
    inv = invite(client, admin_token)
    resp = client.post(f"/admin/users/{inv['invite']['user_id']}/reset-password", headers=bearer(admin_token))
    assert resp.status_code == 409


def test_disable_user(client, admin_token):
    user_id, bo_token = join(client, admin_token)
    resp = client.post(f"/admin/users/{user_id}/disable", headers=bearer(admin_token))
    assert resp.json()["status"] == "disabled"
    assert client.get("/me", headers=bearer(bo_token)).status_code == 401
    sign_in(client, "bo@acme.test", "a long new password", expect=401)


def test_admin_cannot_disable_self(client, admin_token):
    me = client.get("/me", headers=bearer(admin_token)).json()
    assert client.post(f"/admin/users/{me['id']}/disable", headers=bearer(admin_token)).status_code == 409


def test_members_cannot_use_admin_routes(client, admin_token):
    _, bo_token = join(client, admin_token)
    assert client.get("/admin/users", headers=bearer(bo_token)).status_code == 403
    assert client.post("/admin/invites", json={"email": "x@acme.test", "display_name": "X"}, headers=bearer(bo_token)).status_code == 403


def test_admin_lists_users(client, admin_token):
    join(client, admin_token)
    emails = [u["email"] for u in client.get("/admin/users", headers=bearer(admin_token)).json()]
    assert emails == ["ada@acme.test", "bo@acme.test"]
