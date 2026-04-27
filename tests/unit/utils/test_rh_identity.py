"""Unit tests for utils/rh_identity module."""

from typing import Optional

import pytest
from pytest_mock import MockerFixture

from authentication.rh_identity import RHIdentityData
from utils.rh_identity import AUTH_DISABLED, get_rh_identity_context


def test_auth_disabled_constant() -> None:
    """Verify AUTH_DISABLED constant value."""
    assert AUTH_DISABLED == "auth_disabled"


@pytest.mark.parametrize(
    ("rh_identity_setup", "expected_org_id", "expected_system_id"),
    [
        pytest.param(
            {"org_id": "org123", "user_id": "sys456"},
            "org123",
            "sys456",
            id="identity_present",
        ),
        pytest.param(
            None,
            AUTH_DISABLED,
            AUTH_DISABLED,
            id="identity_absent",
        ),
        pytest.param(
            {"org_id": "", "user_id": "sys456"},
            AUTH_DISABLED,
            "sys456",
            id="empty_org_id",
        ),
        pytest.param(
            {"org_id": "org123", "user_id": ""},
            "org123",
            AUTH_DISABLED,
            id="empty_user_id",
        ),
    ],
)
def test_get_rh_identity_context(
    mocker: MockerFixture,
    rh_identity_setup: Optional[dict[str, str]],
    expected_org_id: str,
    expected_system_id: str,
) -> None:
    """Test get_rh_identity_context extracts or defaults org/system IDs."""
    mock_request = mocker.Mock()

    mock_rh_identity = None

    if rh_identity_setup is not None:
        mock_rh_identity = mocker.Mock(spec=RHIdentityData)
        mock_rh_identity.get_org_id.return_value = rh_identity_setup["org_id"]
        mock_rh_identity.get_user_id.return_value = rh_identity_setup["user_id"]
        mock_request.state = mocker.Mock()
        mock_request.state.rh_identity_data = mock_rh_identity
    else:
        mock_request.state = mocker.Mock(spec=[])

    org_id, system_id = get_rh_identity_context(mock_request)

    assert org_id == expected_org_id
    assert system_id == expected_system_id

    if rh_identity_setup is not None:
        assert mock_rh_identity is not None
        mock_rh_identity.get_org_id.assert_called_once()
        mock_rh_identity.get_user_id.assert_called_once()
