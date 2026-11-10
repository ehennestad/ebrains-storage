"""ClientHttpError carries the response of a request that failed, and its body in the message."""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from ebrains_storage.client import ERROR_BODY_LIMIT, BucketApiClient
from ebrains_storage.exceptions import ClientHttpError

# The data-proxy's answer to a request without a token, as data-proxy.ebrains.eu sends it.
NOT_AUTHENTICATED = (
    '{"status_code":401,"detail":"You are not authenticated. This resource might require authenticated access '
    '- please retry with providing an authentication header."}'
)


def _response(status_code, body):
    """A requests.Response with this status and body, as the session returns it."""
    response = requests.Response()
    response.status_code = status_code
    response._content = body.encode()
    response.encoding = "utf-8"
    return response


def _bucket_client_answering(response):
    """A BucketApiClient whose HTTP session answers every request with ``response``."""
    claims = base64.b64encode(json.dumps({"exp": time.time() + 3600}).encode()).decode().rstrip("=")
    client = BucketApiClient(token=f"header.{claims}.signature")
    client.session.request = MagicMock(return_value=response)
    return client


def test_an_unexpected_status_raises_with_the_response_and_its_body():
    response = _response(401, NOT_AUTHENTICATED)
    with pytest.raises(ClientHttpError) as info:
        _bucket_client_answering(response).get("/v1/buckets/foo/stat")
    assert info.value.code == 401
    assert info.value.response is response
    assert info.value.message == f"Expected (200,), but got 401: {NOT_AUTHENTICATED}"
    assert "You are not authenticated" in str(info.value)


def test_the_message_holds_the_start_of_a_long_body():
    with pytest.raises(ClientHttpError) as info:
        _bucket_client_answering(_response(500, "x" * 1000)).get("/v1/buckets/foo/stat")
    assert info.value.message == f"Expected (200,), but got 500: {'x' * ERROR_BODY_LIMIT}"


def test_an_empty_body_leaves_the_status_alone_in_the_message():
    with pytest.raises(ClientHttpError) as info:
        _bucket_client_answering(_response(404, "")).get("/v1/buckets/foo/stat")
    assert info.value.message == "Expected (200,), but got 404"


def test_a_failed_login_raises_client_http_error_with_the_status():
    # An OAuth 2.0 token endpoint answers a failed request with "error" and "error_description" (RFC 6749, 5.2).
    response = _response(400, '{"error": "invalid_request", "error_description": "Missing parameter: username"}')
    with patch("ebrains_storage.client.requests.post", return_value=response):
        with pytest.raises(ClientHttpError) as info:
            BucketApiClient(username="someone", password="secret")
    assert info.value.code == 400
    assert info.value.message == "Missing parameter: username"
    assert info.value.response is response
