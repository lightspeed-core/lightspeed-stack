import pytest
from shields.redaction_shield import (
    RedactionShield,
    get_redaction_shield,
    redact_query,
    redact_attachments,
)
from models.requests import Attachment


class TestRedactionShield:
    def test_basic_patterns(self):
        shield = RedactionShield()
        assert shield.redact_text("Deploy foo app", "test") == "Deploy deployment app"
        assert shield.redact_text("Connect to bar", "test") == "Connect to openshift"
        assert shield.redact_text("Enter password", "test") == "Enter [REDACTED]"
        assert shield.redact_text("API secret key", "test") == "API [REDACTED] key"

    def test_multiple_patterns_in_text(self):
        shield = RedactionShield()
        result = (
            shield.redact_text("Deploy foo to bar with password and secret", "test")
            or ""
        )
        assert all(word not in result for word in ["foo", "bar", "password", "secret"])
        assert all(word in result for word in ["deployment", "openshift", "[REDACTED]"])

    def test_case_insensitivity(self):
        shield = RedactionShield()
        result = shield.redact_text("FOO and PASSWORD", "test") or ""
        assert "deployment" in result
        assert "[REDACTED]" in result

    def test_word_boundaries(self):
        shield = RedactionShield()
        result = shield.redact_text("food foobar foo", "test") or ""
        assert "food" in result
        assert "foobar" in result
        assert "deployment" in result

    def test_no_matches(self):
        shield = RedactionShield()
        text = "Clean sentence without keywords"
        assert shield.redact_text(text, "test") == text

    def test_empty_and_none_input(self):
        shield = RedactionShield()
        assert shield.redact_text("", "test") == ""
        assert shield.redact_text(None, "test") is None

    def test_custom_patterns(self):
        shield = RedactionShield(
            [
                {"pattern": r"\btest\b", "replacement": "TESTED"},
                {"pattern": r"\bsample\b", "replacement": "EXAMPLE"},
            ]
        )
        assert shield.redact_text("test sample", "test") == "TESTED EXAMPLE"

    def test_invalid_patterns(self, mocker):
        mock_logger = mocker.patch("shields.redaction_shield.logger")
        patterns = [
            {"pattern": "[invalid", "replacement": "oops"},
            {"pattern": r"\bvalid\b", "replacement": "ok"},
        ]
        shield = RedactionShield(patterns)
        assert len(shield.compiled_patterns) == 1
        mock_logger.error.assert_called_once()


@pytest.mark.parametrize(
    "query, expected",
    [
        ("Deploy foo to bar", "Deploy deployment to openshift"),
        ("Normal input", "Normal input"),
    ],
)
def test_redact_query(query, expected):
    assert redact_query("test", query) == expected


def test_redact_attachments():
    attachments = [
        Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="foo with password",
        ),
        Attachment(
            attachment_type="conf", content_type="text/plain", content="non-sensitive"
        ),
    ]
    redacted = redact_attachments("test", attachments)

    assert len(redacted) == 2
    assert "deployment" in redacted[0].content
    assert "[REDACTED]" in redacted[0].content
    assert redacted[1].content == "non-sensitive"


def test_redact_attachments_exception(mocker):
    mock_logger = mocker.patch("shields.redaction_shield.logger")
    attachment = Attachment(
        attachment_type="log", content_type="text/plain", content="some content"
    )
    mock_shield = mocker.patch("shields.redaction_shield.get_redaction_shield")
    mock_shield.return_value.redact_text.side_effect = Exception("boom")
    assert redact_attachments("test", [attachment]) == [attachment]
    mock_logger.error.assert_called_once()


def test_redaction_shield_singleton_behavior():
    assert get_redaction_shield() is get_redaction_shield()


def test_get_redaction_shield_with_override():
    patterns = [{"pattern": r"\babc\b", "replacement": "XYZ"}]
    shield = get_redaction_shield(patterns)
    assert shield.patterns[0]["pattern"] == r"\babc\b"
