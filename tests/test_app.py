

def test_app_creates(app_ctx):
    assert app_ctx is not None


def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"login" in response.data.lower()


def test_root_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code in (302, 301)
    assert "/login" in response.headers.get("Location", "")


def test_login_bad_credentials(client):
    response = client.post("/login", data={"username": "nobody", "password": "wrong"})
    assert response.status_code == 401


def test_logout_clears_session(client, authed_client):
    response = authed_client.post("/logout")
    assert response.status_code in (302, 301)
