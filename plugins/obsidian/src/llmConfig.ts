import { App, requireApiVersion } from "obsidian";
import { LanguageToolPluginSettings } from "./SettingsTab";

/**
 * AI commands run only when the user configured an endpoint and a model.
 * The gateway's `.env` is deliberately not used as a fallback here: an empty
 * plugin configuration means "LanguageTool only".
 */
export function isLlmConfigured(settings: LanguageToolPluginSettings): boolean {
  return Boolean(settings.llmBaseUrl?.trim() && settings.llmModel?.trim());
}

/** Per-request LLM settings; the gateway falls back to `.env` when absent. */
export function llmHeaders(
  app: App,
  settings: LanguageToolPluginSettings
): Record<string, string> {
  if (!isLlmConfigured(settings)) {
    return {};
  }
  const headers: Record<string, string> = {
    "X-LLM-Base-URL": settings.llmBaseUrl!.trim(),
    "X-LLM-Model": settings.llmModel!.trim()
  };
  const secretName = settings.llmApiKeySecretName;
  if (requireApiVersion("1.11.4") && secretName) {
    const apiKey = app.secretStorage.getSecret(secretName);
    if (apiKey) {
      headers["X-LLM-API-Key"] = apiKey;
    }
  }
  return headers;
}