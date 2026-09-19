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
