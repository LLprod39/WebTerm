from __future__ import annotations

KNOWN_MODEL_PROVIDERS = {"auto", "gemini", "openai", "fair", "grok", "claude", "ollama"}


def resolve_provider_and_model(
    provider: str | None = None,
    model: str | None = None,
    *,
    default_provider: str = "auto",
) -> tuple[str, str | None]:
    """
    Resolve an explicit provider/model pair.

    Supports:
    - explicit provider + model
    - provider-only
    - legacy model-only values where provider is encoded in the model id
    """

    provider_norm = (provider or "").strip().lower()
    model_norm = (model or "").strip() or None

    if provider_norm in KNOWN_MODEL_PROVIDERS:
        return provider_norm or default_provider, model_norm

    if model_norm:
        lower_model = model_norm.lower()
        if lower_model.startswith("models/gemini") or lower_model.startswith("gemini"):
            return "gemini", model_norm
        if lower_model.startswith("gpt-") or lower_model.startswith("o1") or lower_model.startswith("o3"):
            return "openai", model_norm
        if lower_model.startswith("qwen") or lower_model.startswith("fair-"):
            return "fair", model_norm
        if lower_model.startswith("grok-") or lower_model == "grok":
            return "grok", model_norm
        if "claude" in lower_model:
            return "claude", model_norm

    return default_provider, model_norm
