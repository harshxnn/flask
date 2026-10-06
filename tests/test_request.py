from __future__ import annotations

import pytest
from werkzeug.exceptions import HTTPException

from flask import Flask
from flask import Request
from flask import request
from flask.testing import FlaskClient


def test_max_content_length(app: Flask, client: FlaskClient) -> None:
    app.config["MAX_CONTENT_LENGTH"] = 50

    @app.post("/")
    def index():
        request.form["myfile"]
        AssertionError()

    @app.errorhandler(413)
    def catcher(error):
        return "42"

    rv = client.post("/", data={"myfile": "foo" * 50})
    assert rv.data == b"42"


def test_limit_config(app: Flask):
    app.config["MAX_CONTENT_LENGTH"] = 100
    app.config["MAX_FORM_MEMORY_SIZE"] = 50
    app.config["MAX_FORM_PARTS"] = 3
    r = Request({})

    # no app context, use Werkzeug defaults
    assert r.max_content_length is None
    assert r.max_form_memory_size == 500_000
    assert r.max_form_parts == 1_000

    # in app context, use config
    with app.app_context():
        assert r.max_content_length == 100
        assert r.max_form_memory_size == 50
        assert r.max_form_parts == 3

    # regardless of app context, use override
    r.max_content_length = 90
    r.max_form_memory_size = 30
    r.max_form_parts = 4

    assert r.max_content_length == 90
    assert r.max_form_memory_size == 30
    assert r.max_form_parts == 4

    with app.app_context():
        assert r.max_content_length == 90
        assert r.max_form_memory_size == 30
        assert r.max_form_parts == 4


def test_trusted_hosts_config(app: Flask) -> None:
    app.config["TRUSTED_HOSTS"] = ["example.test", ".other.test"]

    @app.get("/")
    def index() -> str:
        return ""

    client = app.test_client()
    r = client.get(base_url="http://example.test")
    assert r.status_code == 200
    r = client.get(base_url="http://a.other.test")
    assert r.status_code == 200
    r = client.get(base_url="http://bad.test")
    assert r.status_code == 400


@pytest.mark.parametrize(
    ("accept", "expect"),
    [
        ("application/json", True),
        ("text/html", False),
        # a browser puts text/html ahead of its */* catch-all
        ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", False),
        ("application/json;q=0.9,text/html;q=0.8", True),
        ("text/html;q=0.9,application/json;q=0.8", False),
        ("application/*", True),
    ],
)
def test_wants_json_accept(accept: str, expect: bool) -> None:
    r = Request.from_values(headers={"Accept": accept})
    assert r.wants_json is expect


@pytest.mark.parametrize("accept", [None, "*/*"])
def test_wants_json_no_preference(accept: str | None) -> None:
    headers = {} if accept is None else {"Accept": accept}

    # without a preference, prefer HTML, what a browser should get
    r = Request.from_values(headers=headers)
    assert r.wants_json is False

    # a JSON body shows the client is not a browser
    r = Request.from_values(method="POST", json={"a": 1}, headers=headers)
    assert r.wants_json is True


def test_wants_json_error_handler(app: Flask, client: FlaskClient) -> None:
    """One handler can serve both representations of an error, the pattern
    documented in docs/errorhandling.rst.
    """

    @app.errorhandler(HTTPException)
    def handle(e: HTTPException):
        if request.wants_json:
            return {"code": e.code, "name": e.name}, e.code

        return f"<h1>{e.name}</h1>", e.code

    rv = client.get("/missing", headers={"Accept": "application/json"})
    assert rv.status_code == 404
    assert rv.mimetype == "application/json"
    assert rv.json == {"code": 404, "name": "Not Found"}

    rv = client.get("/missing", headers={"Accept": "text/html"})
    assert rv.status_code == 404
    assert rv.mimetype == "text/html"
    assert rv.data == b"<h1>Not Found</h1>"
