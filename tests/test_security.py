def test_internal_api_error_returns_500(app_ctx):
    from app.security import internal_api_error
    with app_ctx.test_request_context("/"):
        response, status = internal_api_error("test", ValueError("boom"))
        assert status == 500
        data = response.get_json()
        assert "error" in data
        assert "error_id" in data


def test_upstream_api_error_returns_502(app_ctx):
    from app.security import upstream_api_error
    with app_ctx.test_request_context("/"):
        response, status = upstream_api_error("test", ConnectionError("timeout"))
        assert status == 502


def test_csrf_token_generated(app_ctx):
    from app.security import ensure_csrf_token
    with app_ctx.test_request_context("/"):
        token = ensure_csrf_token()
        assert len(token) > 10


def test_validate_csrf_accepts_matching_header(app_ctx):
    from app.security import validate_csrf_request
    with app_ctx.test_request_context("/", method="POST",
                                      headers={"X-CSRF-Token": "abc123"}):
        from flask import session
        session["_csrf_token"] = "abc123"
        assert validate_csrf_request() is True


def test_validate_csrf_accepts_matching_form_field(app_ctx):
    from app.security import validate_csrf_request
    with app_ctx.test_request_context("/", method="POST",
                                      data={"csrf_token": "abc123"}):
        from flask import session
        session["_csrf_token"] = "abc123"
        assert validate_csrf_request() is True


def test_validate_csrf_rejects_wrong_token(app_ctx):
    from app.security import validate_csrf_request
    with app_ctx.test_request_context("/", method="POST",
                                      headers={"X-CSRF-Token": "wrong"}):
        from flask import session
        session["_csrf_token"] = "abc123"
        assert validate_csrf_request() is False


def test_validate_csrf_rejects_missing_token(app_ctx):
    from app.security import validate_csrf_request
    with app_ctx.test_request_context("/", method="POST"):
        from flask import session
        session["_csrf_token"] = "abc123"
        assert validate_csrf_request() is False


def test_validate_csrf_rejects_missing_session_token(app_ctx):
    from app.security import validate_csrf_request
    with app_ctx.test_request_context("/", method="POST",
                                      headers={"X-CSRF-Token": "abc123"}):
        assert validate_csrf_request() is False


def test_csrf_error_response_json_for_api_path(app_ctx):
    from app.security import csrf_error_response
    with app_ctx.test_request_context("/api/some/endpoint", method="POST"):
        response, status = csrf_error_response()
        assert status == 400
        assert response.get_json()["error"] == "CSRF validation failed"


def test_csrf_error_response_plain_text_for_non_api(app_ctx):
    from app.security import csrf_error_response
    with app_ctx.test_request_context("/dashboard", method="POST"):
        response, status = csrf_error_response()
        assert status == 400
        assert response == "CSRF validation failed"


def test_csrf_error_response_json_for_admin_api_path(app_ctx):
    from app.security import csrf_error_response
    with app_ctx.test_request_context("/admin/api/users", method="POST"):
        response, status = csrf_error_response()
        assert status == 400
        assert response.get_json()["error"] == "CSRF validation failed"
