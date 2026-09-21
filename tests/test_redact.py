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


FAKE = "Zx9synthetic0Value1234567"
PEM_BEGIN = "-----BEGIN " + "RSA PRIVATE KEY-----"
PEM_END = "-----END " + "RSA PRIVATE KEY-----"
FAKE_AWS_ID = "AKIA" + "SYNTHETICFAKE000"
FAKE_JWT = ".".join(["eyJ" + "hbGciOiJub25lIn0", "eyJ" + "zeW50aGV0aWMifQ", "c3ludGhldGljc2ln"])


@pytest.mark.parametrize(
    "command",
    [
        f"OPENAI_API_KEY={FAKE} python app.py",
        f"export GITHUB_TOKEN={FAKE} && gh api /user",
        f"DB_PASSWORD={FAKE} psql -h localhost",
        f"AWS_SECRET_ACCESS_KEY={FAKE}",
        f'MY_SERVICE_TOKEN="{FAKE}" ./run.sh',
        f"client_secret={FAKE}",
        f"refresh_token: {FAKE}",
        f'curl -H "Authorization: Basic {FAKE}==" https://example.test',
        f'curl -H "Authorization: token {FAKE}" https://example.test',
        f'curl -H "authorization: {FAKE}" https://example.test',
        f'curl -H "X-API-Key: {FAKE}" https://example.test',
        f'curl -H "Cookie: session={FAKE}; theme=dark" https://example.test',
        f"curl -u admin:{FAKE} https://example.test",
        f"cli --token {FAKE} run",
        f'cli --api-key "{FAKE}" run',
        f"cli --password={FAKE}",
        f"https://example.test/cb?access_token={FAKE}&x=1",
        f"https://user:{FAKE}@example.test/path",
        f'{{"cmd": "curl -H \\"Authorization: Bearer {FAKE}\\" x"}}',
        f'{{\\"api_key\\": \\"{FAKE}\\"}}',
        f'{{"id_token": "{FAKE}"}}',
        f'{{"token":"{FAKE}"}}',
        f"{PEM_BEGIN}\nMIIsynthetic{FAKE}\n{PEM_END}",
        f"{PEM_BEGIN}\nMIIsynthetic{FAKE} (truncated, no end marker)",
        f"aws id {FAKE_AWS_ID} in text",
        f"jwt {FAKE_JWT} in text",
    ],
)
def test_redacts_realistic_credential_forms_without_leaking_the_value(command):
    redacted = _redact_text(command)

    assert FAKE not in redacted
    assert FAKE_AWS_ID not in redacted
    assert FAKE_JWT not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_keeps_command_structure_around_the_secret():
    redacted = _redact_text(f'curl -H "Authorization: Bearer {FAKE}" https://example.test/a?b=1')

    assert redacted == 'curl -H "Authorization: Bearer [REDACTED]" https://example.test/a?b=1'
    escaped = _redact_text('{"cmd": "curl -H \\"Authorization: Bearer ' + FAKE + '\\" x"}')
    assert escaped == '{"cmd": "curl -H \\"Authorization: Bearer [REDACTED]\\" x"}'


@pytest.mark.parametrize(
    "benign",
    [
        "max_tokens=1000000000 and tokenizer=bert-base-uncased-model",
        "token_count: 12345678901234",
        "credential_type=oauth2-device-flow-long",
        "secret_name=my-secret-config-map-name",
        "password_file=/etc/app/password.txt",
        "docker run -u 1000:1000 image",
        "curl https://example.test/a:b/c -o out",
        "ssh://git@example.test:22/org/repo.git",
        "git@example.test:org/repo.git",
        "http://localhost:8080/path",
        "export TOKEN=$MY_TOKEN_FROM_ENV",
        "password: $(cat /run/secrets/pw_file_name)",
        "cli --token --verbose",
        "Authorization header is required for this endpoint",
        "next_page_token is opaque",
    ],
)
def test_redaction_leaves_benign_lookalikes_untouched(benign):
    assert _redact_text(benign) == benign


def test_structured_redaction_matches_prefixed_names_and_keeps_non_secret_scalars():
    from security.redact import _redact_value

    payload = {
        "env": {
            "OPENAI_API_KEY": FAKE,
            "GITHUB_TOKEN": FAKE,
            "client_secret": FAKE,
            "refresh_token": FAKE,
            "token": FAKE,
            "secret": FAKE,
        },
        "headers": {"Cookie": FAKE, "Set-Cookie": FAKE, "X-Auth-Token": FAKE},
        "is_secret": True,
        "token_note": None,
        "credential_type": "oauth2",
        "max_tokens": 4096,
    }

    redacted = _redact_value(payload)

    assert set(redacted["env"].values()) == {"[REDACTED]"}
    assert set(redacted["headers"].values()) == {"[REDACTED]"}
    assert redacted["is_secret"] is True
    assert redacted["token_note"] is None
    assert redacted["credential_type"] == "oauth2"
    assert redacted["max_tokens"] == 4096


def test_redaction_is_idempotent():
    once = _redact_text(f"OPENAI_API_KEY={FAKE} curl -H 'Authorization: Basic {FAKE}' --token {FAKE}")

    assert _redact_text(once) == once


def test_redaction_stays_fast_on_adversarial_repetition():
    import time

    started = time.perf_counter()
    for blob in ("curl -u " * 20_000, "token_" * 30_000, "-" * 200_000, "k=" * 50_000):
        _redact_text(blob)

    assert time.perf_counter() - started < 10
