"""Steps for /models endpoint."""

import requests

from behave import when, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context


def model_rest_api_call(context: Context, parameters: dict) -> None:
    # initial value
    context.response = None

    # perform REST API call
    endpoint = "models"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    response = requests.get(url, headers=headers, params=parameters)
    context.response = response


@when("I retrieve list of available models")
def request_models_endpoint(context: Context) -> None:
    """Perform a request using /models endpoint."""
    model_rest_api_call(context, {})


@when('I retrieve list of available models with type set to "{model_type}"')
def request_models_with_type_endpoint(context: Context, model_type: str) -> None:
    """Perform a request using /models endpoint using model type query parameter."""
    model_rest_api_call(context, {"model_type": model_type})


@then("The models list should not be empty")
def check_model_list_is_not_empty(context: Context) -> None:
    """Check that list of models is not empty."""
    models = get_model_list_from_response(context)
    assert len(models) > 0, "Response has empty list of models"


@then("The models list should be empty")
def check_model_list_is_empty(context: Context) -> None:
    """Check that list of models is empty."""
    models = get_model_list_from_response(context)
    assert len(models) == 0, "Expected empty list of models"


@then('The models list should contain only models of type "{model_type}"')
def check_all_models_are_of_expected_type(context: Context, model_type: str) -> None:
    models = get_model_list_from_response(context)
    for model in models:
        assert (
            "api_model_type" in model
        ), "Model does not contain 'api_model_type' attribute"
        model = model["api_model_type"]
        assert model == model_type, f"Unexpected model returned: {model}"


def get_model_list_from_response(context: Context) -> list:
    """Retrieve model list from response."""
    response_json = context.response.json()
    assert response_json is not None, "Response is not valid JSON"

    assert "models" in response_json, "Response missing 'models' field"
    return response_json["models"]


@then("The body of the response has proper model structure")
def check_model_structure(context: Context) -> None:
    """Check that the expected LLM model has the correct structure and required fields."""
    models = get_model_list_from_response(context)
    assert len(models) > 0, "Response has empty list of models"

    # Get expected values from context (detected in before_all)
    expected_model = context.default_model
    expected_provider = context.default_provider

    # Search for the specific model that was detected in before_all
    llm_model = None
    for model in models:
        if (
            model.get("api_model_type") == "llm"
            and model.get("provider_id") == expected_provider
            and model.get("provider_resource_id") == expected_model
        ):
            llm_model = model
            break

    assert llm_model is not None, (
        f"Expected LLM model not found in response. "
        f"Looking for provider_id='{expected_provider}' and provider_resource_id='{expected_model}'"
    )

    # Validate structure and values
    assert (
        llm_model["type"] == "model"
    ), f"type should be 'model', but is {llm_model["type"]}"
    assert (
        llm_model["api_model_type"] == "llm"
    ), f"api_model_type should be 'llm', but is {llm_model["api_model_type"]}"
    assert (
        llm_model["model_type"] == "llm"
    ), f"model_type should be 'llm', but is {llm_model["model_type"]}"
    assert (
        llm_model["provider_id"] == expected_provider
    ), f"provider_id should be '{expected_provider}', but is '{llm_model["provider_id"]}'"
    assert (
        llm_model["provider_resource_id"] == expected_model
    ), f"provider_resource_id should be '{expected_model}', but is '{llm_model["provider_resource_id"]}'"
    assert (
        llm_model["identifier"] == f"{expected_provider}/{expected_model}"
    ), f"identifier should be '{expected_provider}/{expected_model}', but is '{llm_model["identifier"]}'"
