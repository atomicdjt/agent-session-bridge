import pytest

from security.redact import _redact_text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "API_KEY=synthetic_api_key_12345",
            'API_KEY = "[REDACTED]"',
        ),
        (
            "TOKEN=synthetic_token_value_12345",
            'TOKEN = "[REDACTED]"',
        ),
        (
            "Authorization: Bearer synthetic-bearer-token-12345",
            "Authorization: Bearer [REDACTED]",
        ),
        (
            "github_pat=ghp_synthetic_github_token_12345",
            "github_pat=[REDACTED]",
        ),
        (
            "github_pat=github_pat_synthetic_token_12345",
            "github_pat=[REDACTED]",
        ),
        (
            "openai=sk-synthetic-openai-key-12345",
            "openai=[REDACTED]",
        ),
    ],
)
def test_redacts_common_synthetic_token_shapes(value, expected):
    assert _redact_text(value) == expected


def test_preserves_short_and_prose_near_matches():
    value = "The token=short value is intentionally visible in this example."

    assert _redact_text(value) == value


def test_redacts_structured_dictionary_sensitive_keys():
    from security.redact import _redact_value

    payload = {
        "api_key": "raw_secret_key_12345",
        "password": "super_secret_password",
        "access_token": "token_abc123456789",
        "nested": {
            "secret_key": "nested_secret_12345",
            "safe_field": "keep_this_intact",
        },
        "path": "/dev/workspace/README.md",
    }
    redacted = _redact_value(payload)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["nested"]["secret_key"] == "[REDACTED]"
    assert redacted["nested"]["safe_field"] == "keep_this_intact"
    assert redacted["path"] == "/dev/workspace/README.md"


def test_redacts_json_quoted_sensitive_key_value_pairs():
    json_str = '{"api_key": "mysecretvalue1234567890", "safe": "normal"}'
    assert _redact_text(json_str) == '{"api_key": "[REDACTED]", "safe": "normal"}'

    compact_json = '{"password":"mysecretpassword123","safe":"normal"}'
    assert _redact_text(compact_json) == '{"password":"[REDACTED]","safe":"normal"}'


def test_redacts_sensitive_key_variations_and_preserves_false_positives():
    from security.redact import _redact_value

    payload = {
        "api.key": "raw_secret_dot_key",
        "authorization": "raw_auth_token_value",
        "passwd": "my_raw_password",
        "credential_type": "oauth2",
        "pwd": "/home/user/project",
    }
    redacted = _redact_value(payload)

    assert redacted["api.key"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["passwd"] == "[REDACTED]"
    assert redacted["credential_type"] == "oauth2"
    assert redacted["pwd"] == "/home/user/project"
