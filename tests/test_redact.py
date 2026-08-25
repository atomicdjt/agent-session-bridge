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
