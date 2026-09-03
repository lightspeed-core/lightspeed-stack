"""Integration tests for the /v1/saved-prompts REST API endpoints."""

import pytest
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.endpoints.saved_prompts import (
    create_saved_prompts_handler,
    delete_saved_prompts_handler,
    get_saved_prompts_config_handler,
    list_saved_prompts_handler,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import SavedPromptCreateRequest
from models.api.responses.successful import SavedPromptResponse
from tests.integration.conftest import (
    TEST_NON_EXISTENT_ID,
    TEST_OTHER_USER_ID,
)


@pytest.fixture(name="other_auth")
def other_auth_fixture() -> AuthTuple:
    """Auth tuple for a different user than noop default auth."""
    return (TEST_OTHER_USER_ID, "other-user", True, "test_token")


async def create_prompt_via_handler(
    request: Request,
    auth: AuthTuple,
    name: str,
    content: str,
) -> SavedPromptResponse:
    """Create a saved prompt through the real create handler.

    Parameters:
        request: FastAPI request for authorization middleware.
        auth: Authenticated user tuple.
        name: Prompt display name.
        content: Prompt body.

    Returns:
        SavedPromptResponse from the create handler.
    """
    return await create_saved_prompts_handler(
        request=request,
        body=SavedPromptCreateRequest(name=name, content=content),
        auth=auth,
    )


@pytest.mark.asyncio
async def test_get_saved_prompts_config_returns_limits(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Config endpoint returns saved-prompts limits from loaded configuration."""
    expected = test_config.configuration.saved_prompts

    response = await get_saved_prompts_config_handler(
        auth=test_auth,
        request=test_request,
    )

    assert response.max_prompts_per_user == expected.max_prompts_per_user
    assert response.max_display_name_length == expected.max_display_name_length
    assert response.max_content_length == expected.max_content_length


@pytest.mark.asyncio
async def test_list_saved_prompts_empty_for_new_user(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """List returns an empty prompts array when the user has no saved prompts."""
    _ = test_config
    _ = patch_db_session

    response = await list_saved_prompts_handler(
        auth=test_auth,
        request=test_request,
    )

    assert response.prompts == []


@pytest.mark.asyncio
async def test_create_saved_prompt_persists_and_is_listable(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Create returns prompt fields and the owning user can list it."""
    _ = test_config
    _ = patch_db_session

    created = await create_prompt_via_handler(
        request=test_request,
        auth=test_auth,
        name="Deploy to staging",
        content="Help me write a deployment checklist",
    )

    assert created.id
    assert created.name == "Deploy to staging"
    assert created.content == "Help me write a deployment checklist"
    assert created.created_at is not None
    assert created.updated_at is not None

    listed = await list_saved_prompts_handler(
        auth=test_auth,
        request=test_request,
    )
    assert len(listed.prompts) == 1
    assert listed.prompts[0].id == created.id
    assert listed.prompts[0].name == "Deploy to staging"


@pytest.mark.asyncio
async def test_list_saved_prompts_isolates_users(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    other_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """List returns only the caller's prompts."""
    _ = test_config
    _ = patch_db_session

    owned = await create_prompt_via_handler(
        request=test_request,
        auth=test_auth,
        name="owned-prompt",
        content="owned body",
    )
    other = await create_prompt_via_handler(
        request=test_request,
        auth=other_auth,
        name="other-user-prompt",
        content="should not appear",
    )

    listed = await list_saved_prompts_handler(
        auth=test_auth,
        request=test_request,
    )

    ids = [p.id for p in listed.prompts]
    assert owned.id in ids
    assert other.id not in ids


@pytest.mark.asyncio
async def test_create_saved_prompt_returns_422_when_limit_exceeded(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    other_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Create returns 422 after the configured per-user maximum is reached."""
    _ = patch_db_session
    test_config.configuration.saved_prompts.max_prompts_per_user = 1

    await create_prompt_via_handler(
        request=test_request,
        auth=test_auth,
        name="one",
        content="body one",
    )

    other_created = await create_prompt_via_handler(
        request=test_request,
        auth=other_auth,
        name="other-user-one",
        content="other user body",
    )
    assert other_created.id

    with pytest.raises(HTTPException) as exc_info:
        await create_prompt_via_handler(
            request=test_request,
            auth=test_auth,
            name="two",
            content="body two",
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_delete_own_saved_prompt_removes_it_from_list(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Deleting an owned prompt returns deleted=True and removes it from list."""
    _ = test_config
    _ = patch_db_session

    created = await create_prompt_via_handler(
        request=test_request,
        auth=test_auth,
        name="to-delete",
        content="temporary",
    )

    deleted = await delete_saved_prompts_handler(
        request=test_request,
        prompt_id=created.id,
        auth=test_auth,
    )
    assert deleted.deleted is True
    assert deleted.prompt_id == created.id

    listed = await list_saved_prompts_handler(
        auth=test_auth,
        request=test_request,
    )
    assert listed.prompts == []


@pytest.mark.asyncio
async def test_delete_missing_saved_prompt_returns_deleted_false(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Deleting a non-existent valid id returns deleted=False (idempotent)."""
    _ = test_config
    _ = patch_db_session

    deleted = await delete_saved_prompts_handler(
        request=test_request,
        prompt_id=TEST_NON_EXISTENT_ID,
        auth=test_auth,
    )

    assert deleted.deleted is False
    assert deleted.prompt_id == TEST_NON_EXISTENT_ID


@pytest.mark.asyncio
async def test_delete_other_users_saved_prompt_returns_403(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
    other_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """Deleting another user's prompt raises HTTP 403."""
    _ = test_config
    _ = patch_db_session

    other_prompt = await create_prompt_via_handler(
        request=test_request,
        auth=other_auth,
        name="owned-by-other",
        content="secret",
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_saved_prompts_handler(
            request=test_request,
            prompt_id=other_prompt.id,
            auth=test_auth,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    remaining = await list_saved_prompts_handler(
        auth=other_auth,
        request=test_request,
    )
    assert any(prompt.id == other_prompt.id for prompt in remaining.prompts)
