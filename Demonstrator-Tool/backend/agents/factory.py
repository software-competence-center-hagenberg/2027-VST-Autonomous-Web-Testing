# agents/factory.py
import os
import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from agents.agent_configurations import (
    AgentConfiguration,
    BrowserOnlyConfiguration,
    FourAgentConfiguration,
    FourAgentConfiguration_STATE,
)
from agents.autogen_playwright_configuration import AutoGenPlaywrightConfiguration
from agents.model_configuration import AzureModelConfiguration, ModelConfiguration, OpenAIModelConfiguration

logger = logging.getLogger(__name__)

# Configurations that can be selected through the API/CLI.
CONFIGURATIONS: dict[str, type[AgentConfiguration]] = {
    "BrowserOnlyConfiguration": BrowserOnlyConfiguration,
    "FourAgentConfiguration": FourAgentConfiguration,
    "FourAgentConfiguration_STATE": FourAgentConfiguration_STATE,
    "AutoGenPlaywrightConfiguration": AutoGenPlaywrightConfiguration,
}

# Human-readable metadata describing each configuration, used by the API to
# tell clients what each configuration is and which agents take part in it.
CONFIGURATION_METADATA: dict[str, dict] = {
    "BrowserOnlyConfiguration": {
        "display_name": "Browser Only",
        "description": (
            "A single browser-use agent receives the whole Gherkin test case "
            "as its task and executes it autonomously end-to-end, without any "
            "other agents overseeing it."
        ),
        "agents": ["browser"],
    },
    "FourAgentConfiguration": {
        "display_name": "Four Agent (shared history)",
        "description": (
            "Four agents collaborate over a shared conversation history: an "
            "analyst decides the next high-level intent, a coordinator turns "
            "that intent into a single atomic browser action, a browser agent "
            "executes it, and an observer checks whether execution is still "
            "on track."
        ),
        "agents": ["analyst", "coordinator", "browser", "observer"],
    },
    "FourAgentConfiguration_STATE": {
        "display_name": "Four Agent (state-based)",
        "description": (
            "Four agents use state-based interactions: the analyst proposes "
            "the next intent, the coordinator executes one browser action, "
            "the browser agent performs it, and the observer evaluates the "
            "latest result against the original test goal."
        ),
        "agents": ["analyst", "coordinator", "browser", "observer"],
    },
    "AutoGenPlaywrightConfiguration": {
        "display_name": "AutoGen Playwright",
        "description": (
            "An experimental AutoGen workflow where a coordinator delegates "
            "one Playwright action at a time to a coder and executor, with an analyst "
            "checking the resulting page."
        ),
        "agents": ["coordinator", "coder", "executor", "analyst"],
    },
}


PROVIDERS = ("vllm", "azure", "openai")


def _allowed_models() -> dict[str, set[str]] | None:
    """Load the optional demo model allowlist from the configured JSON file."""
    path = os.getenv("DEMO_ALLOWED_MODELS_FILE", "").strip()
    if not path:
        return None

    try:
        with Path(path).open(encoding="utf-8") as file:
            value = json.load(file)
    except OSError as exc:
        raise ValueError(f"Could not read model allowlist '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model allowlist '{path}' is not valid JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise ValueError("Model allowlist must be a JSON object keyed by provider")

    allowlist: dict[str, set[str]] = {}
    for provider, models in value.items():
        if provider not in PROVIDERS:
            raise ValueError(
                f"Model allowlist contains unknown provider {provider!r}. "
                f"Available: {list(PROVIDERS)}"
            )
        if not isinstance(models, list) or not all(isinstance(model, str) for model in models):
            raise ValueError(f"Model allowlist entry for provider {provider!r} must be a list of strings")
        allowlist[provider] = {model.strip() for model in models if model.strip()}
    return allowlist


def _ensure_model_allowed(provider: str, model: str) -> None:
    allowlist = _allowed_models()
    if allowlist is not None and model not in allowlist.get(provider, set()):
        raise ValueError(
            f"Model {model!r} is not enabled for provider {provider!r} by the demo model allowlist"
        )


def _provider_configuration(provider: str, model: str) -> ModelConfiguration:
    if provider == "vllm":
        base_url = _vllm_base_url()
        if not base_url:
            raise ValueError("Provider 'vllm' is not configured (VLLM_BASE_URL is missing)")
        return OpenAIModelConfiguration(
            base_url=base_url,
            model=model,
            api_key=os.getenv("VLLM_API_KEY", "").strip(),
        )
    if provider == "azure":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
        if not endpoint or not os.getenv("AZURE_OPENAI_API_KEY") or not api_version:
            raise ValueError("Provider 'azure' is not fully configured")
        return AzureModelConfiguration(
            base_url=endpoint,
            model=model,
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            api_version=api_version,
        )
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Provider 'openai' is not configured (OPENAI_API_KEY is missing)")
        return OpenAIModelConfiguration(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=model,
            api_key=api_key,
        )
    raise ValueError(f"Unknown model provider: {provider!r}. Available: {list(PROVIDERS)}")


def _vllm_base_url() -> str:
    """Normalize a vLLM host URL to the OpenAI-compatible API base path."""
    value = os.getenv("VLLM_BASE_URL", "").strip().rstrip("/")
    if value and urlsplit(value).path in ("", "/"):
        return f"{value}/v1"
    return value


def build_model_configuration(provider: str, model: str) -> ModelConfiguration:
    """Build a provider client using the explicitly selected model."""
    if not provider.strip():
        raise ValueError("Model provider must not be blank")
    if not model.strip():
        raise ValueError(f"No model was supplied for provider '{provider}'")
    _ensure_model_allowed(provider, model.strip())
    return _provider_configuration(provider, model)


async def _discover_provider(provider: str) -> dict:
    configured = bool(
        (provider == "vllm" and os.getenv("VLLM_BASE_URL")) or
        (provider == "azure" and os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_API_VERSION")) or
        (provider == "openai" and os.getenv("OPENAI_API_KEY"))
    )
    result = {"models": [], "configured": configured, "reachable": False, "error": None}
    if not configured:
        logger.info("Model discovery skipped for provider=%s: not configured", provider)
        return result
    endpoint = _safe_endpoint(provider)
    logger.info("Starting model discovery: provider=%s endpoint=%s", provider, endpoint)
    try:
        configuration = _provider_configuration(provider, "model-discovery")
        page = await configuration.connect_generic_llm().models.list()
        discovered_models = sorted({item.id for item in page.data})
        allowlist = _allowed_models()
        if allowlist is not None:
            discovered_models = [
                model for model in discovered_models if model in allowlist.get(provider, set())
            ]
        result["models"] = discovered_models
        result["reachable"] = True
        logger.info(
            "Model discovery succeeded: provider=%s endpoint=%s models=%d",
            provider,
            endpoint,
            len(result["models"]),
        )
    except Exception as exc:  # discovery should not make one provider hide others
        error_message = _safe_error_message(exc)
        logger.exception(
            "Model discovery failed: provider=%s endpoint=%s error=%s",
            provider,
            endpoint,
            error_message,
        )
        result["error"] = f"{type(exc).__name__}: {error_message}"
    return result


def _safe_endpoint(provider: str) -> str:
    """Return a log-safe endpoint without query strings or credentials."""
    if provider == "vllm":
        value = _vllm_base_url()
    elif provider == "azure":
        value = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    else:
        value = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def _safe_error_message(exc: Exception) -> str:
    """Expose useful provider errors without returning credentials to clients."""
    message = str(exc).strip() or "unknown provider error"
    for name in ("VLLM_API_KEY", "AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"):
        secret = os.getenv(name)
        if secret:
            message = message.replace(secret, "***")
    return message


async def discover_models() -> dict:
    """Discover all configured providers concurrently, grouped by provider id."""
    values = await asyncio.gather(*(_discover_provider(provider) for provider in PROVIDERS))
    return dict(zip(PROVIDERS, values))


def list_configurations() -> list[dict]:
    """
    Return metadata for every agent configuration exposed through the API,
    e.g. for a "which configuration do you want to use?" endpoint.
    """
    return [
        {
            "id": name,
            "display_name": CONFIGURATION_METADATA.get(name, {}).get("display_name", name),
            "description": CONFIGURATION_METADATA.get(name, {}).get("description", ""),
            "agents": CONFIGURATION_METADATA.get(name, {}).get("agents", []),
        }
        for name in CONFIGURATIONS
    ]


def build_configuration(
    name: str,
    provider: str,
    model: str,
    num_task_executions: int = 10,
    max_iterations: int = 50,
    vision_enabled: bool = True,
) -> AgentConfiguration:
    """
    Instantiate an AgentConfiguration by name, wired up with the LLM connection
    from the environment. The task itself is passed later, to `.run(task=...)`.
    """
    config_cls = CONFIGURATIONS.get(name)
    if config_cls is None:
        raise ValueError(f"Unknown agent configuration: {name!r}. Available: {sorted(CONFIGURATIONS)}")

    return config_cls(
        llm=build_model_configuration(provider=provider, model=model),
        num_task_executions=num_task_executions,
        max_iterations=max_iterations,
        vision_enabled=vision_enabled,
    )
