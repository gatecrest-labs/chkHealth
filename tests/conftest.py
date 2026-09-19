import pytest
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-ok!")


@pytest.fixture
def app_ctx():
    """Minimal Flask app for tests that need an app context."""
    from flask import Flask
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok!"
    app.config["TESTING"] = True
    with app.app_context():
        yield app
