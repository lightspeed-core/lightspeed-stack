"""Store operations for the versioned prompt catalog."""

from typing import Optional
from uuid import uuid4

from app.database import get_session
from log import get_logger
from models.database.prompts import Prompt, PromptVersion
from prompts.exceptions import PromptNotFoundError
from prompts.template import validate_template

logger = get_logger(__name__)


def create_prompt(name: str, template: str, variables: list[str]) -> PromptVersion:
    """Create a new prompt with its initial version.

    Parameters:
        name: Display name for the prompt.
        template: Mustache template text.
        variables: Declared variable names for the template.

    Returns:
        PromptVersion: The initial version row.

    Raises:
        PromptValidationError: If the template is empty, contains invalid
            placeholder names, has duplicate or invalid variable names,
            or has undeclared placeholders.

    """
    validate_template(template, variables)

    prompt_id = f"pmpt_{uuid4()}"
    version = 1

    with get_session() as session:
        prompt = Prompt(id=prompt_id, name=name, default_version=version)
        prompt_version = PromptVersion(
            prompt_id=prompt_id, version=version, template=template, variables=variables
        )

        session.add(prompt)
        session.add(prompt_version)
        session.commit()
        logger.debug("Created prompt id=%s with version %s", prompt_id, version)
        session.refresh(prompt_version)

        return prompt_version


def get_prompt(prompt_id: str, version: Optional[int] = None) -> PromptVersion:
    """Retrieve a prompt version by identifier.

    When version is None the prompt's default version is used.

    Parameters:
        prompt_id: The prompt identifier.
        version: Specific version number, or None for the default.

    Returns:
        PromptVersion: The matching version row.

    Raises:
        PromptNotFoundError: If the prompt or requested version does not exist.

    """
    with get_session() as session:

        # Grab default version from Prompt if version is not provided
        if version is None:
            prompt = session.query(Prompt).filter_by(id=prompt_id).first()
            if prompt is None:
                logger.debug("Prompt id=%s not found", prompt_id)
                raise PromptNotFoundError(f"Prompt id={prompt_id} not found")

            version = prompt.default_version

        prompt_version = (
            session.query(PromptVersion)
            .filter_by(prompt_id=prompt_id, version=version)
            .first()
        )

        if prompt_version is None:
            logger.debug("Version %s of prompt id=%s not found", version, prompt_id)
            raise PromptNotFoundError(
                f"Version {version} of prompt id={prompt_id} not found"
            )

        return prompt_version


def list_prompts() -> list[Prompt]:
    """List all prompts in the catalog.

    Returns:
        list[Prompt]: All prompt identity rows.

    """
    with get_session() as session:
        prompts = session.query(Prompt).all()
        return prompts


def update_prompt(
    prompt_id: str, template: str, variables: list[str], *, default: bool = False
) -> PromptVersion:
    """Create a new immutable version for an existing prompt.

    Parameters:
        prompt_id: The prompt identifier.
        template: Mustache template text for the new version.
        variables: Declared variable names for the template.
        default: If True, set the new version as the prompt's default.

    Returns:
        PromptVersion: The newly created version row.

    Raises:
        PromptNotFoundError: If the prompt does not exist.
        PromptValidationError: If the template is empty, contains invalid
            placeholder names, has duplicate or invalid variable names,
            or has undeclared placeholders.

    """
    validate_template(template, variables)

    with get_session() as session:
        max_prompt_version = (
            session.query(PromptVersion)
            .filter_by(prompt_id=prompt_id)
            .order_by(PromptVersion.version.desc())
            .first()
        )
        if max_prompt_version is None:
            logger.debug("No available version found for prompt id=%s", prompt_id)
            raise PromptNotFoundError(
                f"No available version found for prompt id={prompt_id}"
            )

        max_version = max_prompt_version.version

        prompt_version = PromptVersion(
            prompt_id=prompt_id,
            version=max_version + 1,
            template=template,
            variables=variables,
        )
        session.add(prompt_version)
        logger.debug(
            "Created version %s for prompt id=%s", prompt_version.version, prompt_id
        )

        if default:
            prompt = session.query(Prompt).filter_by(id=prompt_id).first()
            if prompt is None:
                logger.debug("Prompt id=%s not found", prompt_id)
                raise PromptNotFoundError(f"Prompt id={prompt_id} not found")

            prompt.default_version = prompt_version.version

        session.commit()
        session.refresh(prompt_version)

        return prompt_version


def delete_prompt(prompt_id: str) -> None:
    """Delete a prompt and all its versions.

    Parameters:
        prompt_id: The prompt identifier.

    Raises:
        PromptNotFoundError: If the prompt does not exist.

    """
    with get_session() as session:
        prompt = session.query(Prompt).filter_by(id=prompt_id).first()
        if prompt is None:
            raise PromptNotFoundError(f"Prompt id={prompt_id} not found")

        # This cover the situation when FK enforcement is not on
        session.query(PromptVersion).filter_by(prompt_id=prompt_id).delete()
        session.delete(prompt)
        session.commit()
        logger.debug("Deleted prompt id=%s", prompt_id)
