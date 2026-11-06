import {
  App,
  DropdownComponent,
  Modal,
  Notice,
  PluginSettingTab,
  SecretComponent,
  Setting,
  SettingDefinitionItem,
  SliderComponent,
  TextComponent,
  requestUrl,
  requireApiVersion
} from "obsidian";
import LanguageToolPlugin from ".";
import { logs } from "./api";
import { fetchDictionaryStatus } from "./cm6/dictionaryHover";
import { describeDictionaryStatus } from "./dictionaryHelpers";
import { normalizeServerUrl } from "./helpers";

export const DICTIONARY_PAIRS = {
  "de-de": "German – German",
  "en-de": "English → German",
  "de-en": "German → English"
} as const;

export type DictionaryPair = keyof typeof DICTIONARY_PAIRS;

const MinuteInSeconds = 60;
const SecondToMillisecondConversion = 1000;
const StandardMaxRequestsPerMinute = 20;
const PremiumMaxRequestsPerMinute = 80;

const MaxAutoCheckDelay = 5000;
const AutoCheckDelayStep = 50;
const MinStandardAutoCheckDelay =
  (MinuteInSeconds / StandardMaxRequestsPerMinute) *
  SecondToMillisecondConversion;
const MinPremiumAutoCheckDelay =
  (MinuteInSeconds / PremiumMaxRequestsPerMinute) *
  SecondToMillisecondConversion;

export interface LanguageToolPluginSettings {
  shouldAutoCheck: boolean;
  autoCheckDelay: number;

  serverUrl: string;
  urlMode: "standard" | "premium" | "custom";
  showRibbonIcon: boolean;
  glassBg: boolean;
  apikey?: string;
  username?: string;
  // Where the API key lives: "local" = data.json (syncs across devices),
  // "secret" = Obsidian's encrypted SecretStorage (device-local). Undefined for
  // legacy installs; resolved on load by the plugin.
  apiKeyStorage?: "local" | "secret";
  // In "secret" mode, the name of the SecretStorage secret holding the API key
  // (the value itself is never stored here, only the reference).
  apikeySecretName?: string;
  staticLanguage?: string;
  motherTongue?: string;

  englishVeriety?:
    | undefined
    | "en-US"
    | "en-GB"
    | "en-CA"
    | "en-AU"
    | "en-ZA"
    | "en-NZ";
  germanVeriety?: undefined | "de-DE" | "de-AT" | "de-CH";
  portugueseVeriety?: undefined | "pt-BR" | "pt-PT" | "pt-AO" | "pt-MZ";
  catalanVeriety?: undefined | "ca-ES" | "ca-ES-valencia";

  pickyMode: boolean;

  ruleOtherCategories?: string;
  ruleOtherRules?: string;
  ruleOtherDisabledCategories?: string;
  ruleOtherDisabledRules?: string;

  // AI features are opt-in. Every AI command checks this flag first.
  enableAIFeatures?: boolean;
  // OpenAI-compatible endpoint chosen in the plugin. Empty means AI is off,
  // even when the gateway has an `.env` default.
  llmBaseUrl?: string;
  llmModel?: string;
  // Response budget and reasoning effort, sent per request. Undefined uses
  // the gateway's defaults.
  llmMaxTokens?: number;
  llmReasoningEffort?: "low" | "medium" | "high";
  // SecretStorage secret holding the LLM API key (value never stored here).
  llmApiKeySecretName?: string;
  aiAutoCheck?: boolean;
  /** Which AI suggestion categories are allowed. Missing means on. */
  aiGrammar?: boolean;
  aiStyle?: boolean;
  aiVocabulary?: boolean;
  writingMode?: WritingMode;

  // Hover dictionary. Independent of the AI switch; data is downloaded by
  // the gateway and lookup never calls a model.
  dictionaryHover?: boolean;
  dictionaryPair?: DictionaryPair;
}

export const WRITING_MODES = {
  neutral: "Neutral",
  formal: "Formal",
  casual: "Casual",
  academic: "Academic",
  business: "Business"
} as const;

export type WritingMode = keyof typeof WRITING_MODES;

export function isWritingMode(value: unknown): value is WritingMode {
  return (
    typeof value === "string" &&
    Object.keys(WRITING_MODES).includes(value)
  );
}

export const DEFAULT_SETTINGS: LanguageToolPluginSettings = {
  serverUrl: "https://api.languagetool.org",
  urlMode: "standard",

  showRibbonIcon: false,
  glassBg: false,
  shouldAutoCheck: false,
  autoCheckDelay: MinStandardAutoCheckDelay,

  pickyMode: false,

  enableAIFeatures: false,
  llmBaseUrl: "",
  llmModel: "",
  aiAutoCheck: false,
  aiGrammar: true,
  aiStyle: true,
  aiVocabulary: true,
  writingMode: "neutral",
  dictionaryHover: false,
  dictionaryPair: "de-de"
};

export function getServerUrl(value: string) {
  return value === "standard"
    ? "https://api.languagetool.org"
    : value === "premium"
    ? "https://api.languagetoolplus.com"
    : "";
}

function getMinAllowedAutoCheckDelay(value: string) {
  return value === "standard"
    ? MinStandardAutoCheckDelay
    : value === "premium"
    ? MinPremiumAutoCheckDelay
    : AutoCheckDelayStep;
}

interface LanguageToolLanguage {
  name: string;
  code: string;
  longCode: string;
}

// One setting row: name and desc feed Obsidian's settings search, render
// builds the controls. Rendered declaratively on Obsidian 1.13+ and by the
// imperative display() fallback on older versions.
interface RenderedSettingDefinition {
  name: string;
  desc?: string;
  render: (setting: Setting) => void;
}

interface SettingsSection {
  heading?: string;
  items: RenderedSettingDefinition[];
}

function appendRuleListLink(setting: Setting): void {
  setting.descEl.createEl("br");
  setting.descEl.createEl(
    "a",
    {
      text: "Click here for a list of rules and categories",
      href: "https://community.languagetool.org/rule/list"
    },
    a => {
      a.setAttr("target", "_blank");
    }
  );
}

export class LanguageToolSettingsTab extends PluginSettingTab {
  private readonly plugin: LanguageToolPlugin;
  private languagesPromise?: Promise<LanguageToolLanguage[]>;
  private dictionaryPoll: number | null = null;
  private aiModels: string[] = [];
  private aiModelsFetchedFor?: string;
  public constructor(app: App, plugin: LanguageToolPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  public hide(): void {
    if (this.dictionaryPoll !== null) {
      window.clearInterval(this.dictionaryPoll);
      this.dictionaryPoll = null;
    }
    super.hide();
  }

  private configureAutoCheckDelaySlider(
    value: string,
    delaySlider?: SliderComponent
  ) {
    const minAllowedAutoCheckDelay = getMinAllowedAutoCheckDelay(value);

    if (this.plugin.settings.autoCheckDelay < minAllowedAutoCheckDelay) {
      this.plugin.settings.autoCheckDelay = minAllowedAutoCheckDelay;
    }

    delaySlider?.setLimits(
      minAllowedAutoCheckDelay,
      MaxAutoCheckDelay,
      AutoCheckDelayStep
    );
    delaySlider?.setValue(this.plugin.settings.autoCheckDelay);
  }

  public requestLanguages(): Promise<LanguageToolLanguage[]> {
    if (!this.languagesPromise) {
      const promise = requestUrl({
        url: `${this.plugin.settings.serverUrl}/v2/languages`,
        throw: false
      }).then(res => {
        if (res.status < 200 || res.status >= 300) {
          throw new Error(`unexpected status ${res.status}`);
        }
        return res.json as LanguageToolLanguage[];
      });
      this.languagesPromise = promise;
      // A single notice per fetch attempt, shared by both language dropdowns.
      // A failed fetch is not cached, so reopening the settings retries.
      promise.catch(e => {
        console.error(e);
        new Notice(
          "Failed to fetch the list of languages from the LanguageTool server. Check the endpoint URL, then reopen the settings to retry. Auto-detect keeps working in the meantime.",
          8000
        );
        if (this.languagesPromise === promise) {
          this.languagesPromise = undefined;
        }
      });
    }
    return this.languagesPromise;
  }

  /**
   * Warn the user when an API key is set but the endpoint is not the premium
   * one. Shared by both the plaintext text input and the SecretComponent.
   */
  private maybeWarnNonPremium(
    hasKey: boolean,
    onAcknowledge: () => void,
    disableUrlPopup: boolean,
    urlDropdown?: DropdownComponent
  ): void {
    if (
      !hasKey ||
      this.plugin.settings.urlMode === "premium" ||
      disableUrlPopup
    ) {
      return;
    }
    const modal = new Modal(this.app);
    modal.titleEl.setText("Warning");
    modal.contentEl.addClass("lt-premium-warning");
    modal.contentEl.createEl("p", {
      text:
        "You have entered an API Key but you are not using the Premium Endpoint"
    });
    const container = modal.contentEl.createDiv({
      cls: "lt-premium-warning-buttons"
    });
    container.createEl("button", {
      text: "I know what I'm doing",
      cls: "lt-premium-warning-ack"
    }).onclick = () => {
      onAcknowledge();
      modal.close();
    };
    container.createEl("button", {
      text: "Change to Premium",
      cls: "lt-premium-warning-switch"
    }).onclick = async () => {
      this.plugin.settings.urlMode = "premium";
      urlDropdown?.setValue("premium");
      this.plugin.settings.serverUrl = getServerUrl("premium");
      await this.plugin.saveSettings();
      return modal.close();
    };
    modal.open();
  }

  // Re-render the tab after a change that swaps controls (e.g. the API key
  // storage mode). Obsidian 1.13+ re-renders declaratively via update();
  // older versions re-run the imperative fallback.
  private rerender(): void {
    if (requireApiVersion("1.13.0")) {
      this.update();
    } else {
      this.display();
    }
  }

  private ensureDictionaryPoll(
    update: () => Promise<boolean>
  ): void {
    if (this.dictionaryPoll !== null) {
      return;
    }
    this.dictionaryPoll = window.setInterval(() => {
      update()
        .then(building => {
          if (!building && this.dictionaryPoll !== null) {
            window.clearInterval(this.dictionaryPoll);
            this.dictionaryPoll = null;
          }
        })
        .catch(() => {
          if (this.dictionaryPoll !== null) {
            window.clearInterval(this.dictionaryPoll);
            this.dictionaryPoll = null;
          }
        });
    }, 2000);
  }

  private async refreshAiModels(): Promise<void> {
    const baseUrl = this.plugin.settings.llmBaseUrl?.trim();
    if (!baseUrl) {
      this.aiModels = [];
      return;
    }
    const secretName = this.plugin.settings.llmApiKeySecretName;
    let apiKey = "";
    if (requireApiVersion("1.11.4") && secretName) {
      apiKey = this.app.secretStorage.getSecret(secretName) ?? "";
    }
    try {
      const res = await requestUrl({
        url: `${this.plugin.settings.serverUrl}/llm/models`,
        method: "POST",
        contentType: "application/json",
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
        throw: false
      });
      if (res.status < 200 || res.status >= 300) {
        throw new Error(`gateway returned ${res.status}`);
      }
      const models = (res.json as { models?: unknown }).models;
      this.aiModels = Array.isArray(models)
        ? models.filter((model): model is string => typeof model === "string")
        : [];
    } catch (e) {
      this.aiModels = [];
      new Notice(
        `Could not load models: ${e instanceof Error ? e.message : String(e)}`,
        6000
      );
    }
  }

  private getSections(): SettingsSection[] {
    // Shared by the render callbacks of one render cycle: some settings
    // reconfigure others (endpoint changes clamp the delay slider and reset
    // the variety dropdowns). Optional properties rather than nullable
    // unions: the plugin review scanner lints without dependencies, where
    // imported types resolve to the error type and any union containing
    // them is flagged.
    const refs: {
      urlDropdown?: DropdownComponent;
      endpointInput?: TextComponent;
      autoCheckDelaySlider?: SliderComponent;
      staticLanguageComponent?: DropdownComponent;
      englishVarietyDropdown?: DropdownComponent;
      germanVarietyDropdown?: DropdownComponent;
      portugueseVarietyDropdown?: DropdownComponent;
      catalanVarietyDropdown?: DropdownComponent;
    } = {};
    let disableUrlPopup = false;

    const mainSection: SettingsSection = {
      items: [
        {
          name: "Failed request logs",
          desc: "Copy the logs of recent failed LanguageTool requests",
          render: setting => {
            setting.addButton(button => {
              button
                .setButtonText("Copy failed Request Logs")
                .onClick(async () => {
                  if (logs.length === 0) {
                    new Notice("No failed requests have been logged yet");
                    return;
                  }
                  await window.navigator.clipboard.writeText(logs.join("\n"));
                  new Notice("Logs copied to clipboard");
                });
            });
          }
        },
        {
          name: "Endpoint",
          desc: "Endpoint that will be used to make requests to",
          render: setting => {
            setting.controlEl.addClass("lt-settings-endpoint-control");
            setting.addDropdown(component => {
              refs.urlDropdown = component;
              component
                .addOptions({
                  standard: "(Standard) api.languagetool.org",
                  premium: "hosted LanguageTool API",
                  custom: "Custom URL"
                })
                .setValue(this.plugin.settings.urlMode)
                .onChange(async value => {
                  this.plugin.settings.urlMode = value as
                    | "standard"
                    | "premium"
                    | "custom";
                  this.plugin.settings.serverUrl = getServerUrl(value);
                  this.languagesPromise = undefined;
                  refs.endpointInput?.setValue(this.plugin.settings.serverUrl);
                  refs.endpointInput?.setDisabled(value !== "custom");

                  this.configureAutoCheckDelaySlider(
                    value,
                    refs.autoCheckDelaySlider
                  );

                  await this.plugin.saveSettings();
                });
            });
            setting.addText(text => {
              refs.endpointInput = text;
              text
                .setPlaceholder("https://your-custom-url.com")
                .setValue(this.plugin.settings.serverUrl)
                .setDisabled(this.plugin.settings.urlMode !== "custom")
                .onChange(async value => {
                  this.plugin.settings.serverUrl = normalizeServerUrl(value);
                  this.languagesPromise = undefined;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "API Username",
          desc: "Enter a username/email for API Access",
          render: setting => {
            setting.addText(text =>
              text
                .setPlaceholder("peterlustig@gmail.com")
                .setValue(this.plugin.settings.username ?? "")
                .onChange(async value => {
                  this.plugin.settings.username = value.replace(/\s+/g, "");
                  await this.plugin.saveSettings();
                })
            );
          }
        },
        {
          name: "API Key",
          desc: "Enter an API Key",
          render: setting => {
            const useSecretStorage =
              this.plugin.settings.apiKeyStorage === "secret" &&
              this.plugin.isSecretStorageAvailable();
            if (requireApiVersion("1.11.4") && useSecretStorage) {
              setting
                .setDesc(
                  "Select or create a secret in Obsidian's SecretStorage. Stored encrypted on this device only."
                )
                .addComponent(el =>
                  new SecretComponent(this.app, el)
                    .setValue(this.plugin.settings.apikeySecretName ?? "")
                    .onChange(async value => {
                      this.plugin.settings.apikeySecretName = value;
                      await this.plugin.saveSettings();
                      this.maybeWarnNonPremium(
                        value.length > 0,
                        () => {
                          disableUrlPopup = true;
                        },
                        disableUrlPopup,
                        refs.urlDropdown
                      );
                    })
                );
            } else {
              setting.addText(text => {
                text
                  .setValue(this.plugin.settings.apikey ?? "")
                  .onChange(async value => {
                    this.plugin.settings.apikey = value.replace(/\s+/g, "");
                    await this.plugin.saveSettings();
                  });
                // Warn when the user is done typing, not on every keystroke
                text.inputEl.addEventListener("blur", () => {
                  this.maybeWarnNonPremium(
                    Boolean(this.plugin.settings.apikey),
                    () => {
                      disableUrlPopup = true;
                    },
                    disableUrlPopup,
                    refs.urlDropdown
                  );
                });
              });
            }
          }
        },
        {
          name: "Store API key securely (this device only)",
          desc:
            "Store your API key in Obsidian's encrypted SecretStorage instead of in plaintext in data.json. Secrets are not synced across devices, so you'll need to set your key once on each device. Your username stays in your synced settings.",
          render: setting => {
            setting.addToggle(component => {
              const available = this.plugin.isSecretStorageAvailable();
              component
                .setValue(this.plugin.settings.apiKeyStorage === "secret")
                .setDisabled(!available)
                .onChange(async value => {
                  if (value) {
                    const hadPlaintextKey = Boolean(
                      this.plugin.settings.apikey
                    );
                    await this.plugin.enableSecretStorage();
                    new Notice(
                      hadPlaintextKey
                        ? "API key moved to secure storage on this device. It will not sync to your other devices."
                        : "Secure storage enabled. Select or create a secret for your API key in the setting above.",
                      5000
                    );
                  } else {
                    await this.plugin.disableSecretStorage();
                  }
                  // Re-render so the API key setting matches the storage mode
                  // that actually took effect (a disable may be refused when
                  // the secret is not set on this device).
                  this.rerender();
                });
            });
            setting.descEl.createEl("br");
            setting.descEl.createEl(
              "a",
              {
                text: "Read about the trade-offs of both storage options",
                href:
                  "https://github.com/Clemens-E/obsidian-languagetool-plugin#api-key-storage-synced-plaintext-vs-secure-storage"
              },
              a => {
                a.setAttr("target", "_blank");
              }
            );
            if (!this.plugin.isSecretStorageAvailable()) {
              setting.descEl.createEl("br");
              setting.descEl.createSpan({
                text:
                  "Not available on this device (requires Obsidian 1.11.4 or newer).",
                cls: "lt-settings-error-text"
              });
            }
          }
        },
        {
          name: "Autocheck Text",
          desc: "Check text as you type",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.shouldAutoCheck)
                .onChange(async value => {
                  this.plugin.settings.shouldAutoCheck = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "AutoCheck Delay (ms)",
          desc: "Length of time to wait for AutoCheck after last key press",
          render: setting => {
            setting.addSlider(component => {
              refs.autoCheckDelaySlider = component;
              this.configureAutoCheckDelaySlider(
                this.plugin.settings.urlMode,
                component
              );

              component
                .setValue(this.plugin.settings.autoCheckDelay)
                .onChange(async value => {
                  this.plugin.settings.autoCheckDelay = value;
                  await this.plugin.saveSettings();
                });

              component.setDynamicTooltip();
            });
          }
        },
        {
          name: "Ribbon Icon",
          desc:
            "Show an icon in the ribbon that checks the current document. You can also hide it later by right-clicking the ribbon",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.showRibbonIcon)
                .onChange(async value => {
                  this.plugin.settings.showRibbonIcon = value;
                  this.plugin.updateRibbonIcon();
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Glass Background",
          desc:
            "Use the secondary background color of the theme or a glass background",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.glassBg)
                .onChange(async value => {
                  this.plugin.settings.glassBg = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Static Language",
          desc:
            "Set a static language that will always be used (LanguageTool tries to auto detect the language, this is usually not necessary)",
          render: setting => {
            setting.addDropdown(component => {
              refs.staticLanguageComponent = component;
              component.addOption("auto", "Auto Detect");
              component.setValue(this.plugin.settings.staticLanguage ?? "auto");
              component.onChange(async value => {
                this.plugin.settings.staticLanguage = value;
                if (value !== "auto") {
                  this.plugin.settings.englishVeriety = undefined;
                  refs.englishVarietyDropdown?.setValue("default");
                  this.plugin.settings.germanVeriety = undefined;
                  refs.germanVarietyDropdown?.setValue("default");
                  this.plugin.settings.portugueseVeriety = undefined;
                  refs.portugueseVarietyDropdown?.setValue("default");
                  this.plugin.settings.catalanVeriety = undefined;
                  refs.catalanVarietyDropdown?.setValue("default");
                }
                await this.plugin.saveSettings();
              });
              this.requestLanguages()
                .then(languages => {
                  languages.forEach(v => {
                    component.addOption(v.longCode, v.name);
                  });
                  // Set again now that the stored language exists as an option
                  component.setValue(
                    this.plugin.settings.staticLanguage ?? "auto"
                  );
                })
                .catch(() => {
                  // requestLanguages already notified the user
                });
            });
          }
        },
        {
          name: "Mother Tongue",
          desc:
            "Set the language you are most comfortable with. This will be used to interpret the language you are writing in",
          render: setting => {
            setting.addDropdown(component => {
              component.addOption("default", "---");
              component.setValue(
                this.plugin.settings.motherTongue ?? "default"
              );
              component.onChange(async value => {
                this.plugin.settings.motherTongue =
                  value === "default" ? undefined : value;
                await this.plugin.saveSettings();
              });
              this.requestLanguages()
                .then(languages => {
                  languages.forEach(v => {
                    component.addOption(v.longCode, v.name);
                  });
                  // Set again now that the stored language exists as an option
                  component.setValue(
                    this.plugin.settings.motherTongue ?? "default"
                  );
                })
                .catch(() => {
                  // requestLanguages already notified the user
                });
            });
          }
        }
      ]
    };

    const varietySection: SettingsSection = {
      heading: "Language Varieties",
      items: [
        {
          name: "Interpret English as",
          render: setting => {
            setting.addDropdown(component => {
              refs.englishVarietyDropdown = component;
              component
                .addOptions({
                  default: "---",
                  "en-US": "English (US)",
                  "en-GB": "English (British)",
                  "en-CA": "English (Canada)",
                  "en-AU": "English (Australia)",
                  "en-ZA": "English (South Africa)",
                  "en-NZ": "English (New Zealand)"
                })
                .setValue(this.plugin.settings.englishVeriety ?? "default")
                .onChange(async value => {
                  if (value === "default") {
                    this.plugin.settings.englishVeriety = undefined;
                  } else {
                    this.plugin.settings.staticLanguage = "auto";
                    refs.staticLanguageComponent?.setValue("auto");
                    this.plugin.settings.englishVeriety = value as
                      | "en-US"
                      | "en-GB"
                      | "en-CA"
                      | "en-AU"
                      | "en-ZA"
                      | "en-NZ";
                  }
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Interpret German as",
          render: setting => {
            setting.addDropdown(component => {
              refs.germanVarietyDropdown = component;
              component
                .addOptions({
                  default: "---",
                  "de-DE": "German (Germany)",
                  "de-CH": "German (Switzerland)",
                  "de-AT": "German (Austria)"
                })
                .setValue(this.plugin.settings.germanVeriety ?? "default")
                .onChange(async value => {
                  if (value === "default") {
                    this.plugin.settings.germanVeriety = undefined;
                  } else {
                    this.plugin.settings.staticLanguage = "auto";
                    refs.staticLanguageComponent?.setValue("auto");
                    this.plugin.settings.germanVeriety = value as
                      | "de-DE"
                      | "de-CH"
                      | "de-AT";
                  }
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Interpret Portuguese as",
          render: setting => {
            setting.addDropdown(component => {
              refs.portugueseVarietyDropdown = component;
              component
                .addOptions({
                  default: "---",
                  "pt-BR": "Portuguese (Brazil)",
                  "pt-PT": "Portuguese (Portugal)",
                  "pt-AO": "Portuguese (Angola)",
                  "pt-MZ": "Portuguese (Mozambique)"
                })
                .setValue(this.plugin.settings.portugueseVeriety ?? "default")
                .onChange(async value => {
                  if (value === "default") {
                    this.plugin.settings.portugueseVeriety = undefined;
                  } else {
                    this.plugin.settings.staticLanguage = "auto";
                    refs.staticLanguageComponent?.setValue("auto");
                    this.plugin.settings.portugueseVeriety = value as
                      | "pt-BR"
                      | "pt-PT"
                      | "pt-AO"
                      | "pt-MZ";
                  }
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Interpret Catalan as",
          render: setting => {
            setting.addDropdown(component => {
              refs.catalanVarietyDropdown = component;
              component
                .addOptions({
                  default: "---",
                  "ca-ES": "Catalan",
                  "ca-ES-valencia": "Catalan (Valencian)"
                })
                .setValue(this.plugin.settings.catalanVeriety ?? "default")
                .onChange(async value => {
                  if (value === "default") {
                    this.plugin.settings.catalanVeriety = undefined;
                  } else {
                    this.plugin.settings.staticLanguage = "auto";
                    refs.staticLanguageComponent?.setValue("auto");
                    this.plugin.settings.catalanVeriety = value as
                      | "ca-ES"
                      | "ca-ES-valencia";
                  }
                  await this.plugin.saveSettings();
                });
            });
          }
        }
      ]
    };

    const writingSection: SettingsSection = {
      heading: "Writing",
      items: [
        {
          name: "Writing mode",
          desc:
            "Sent with grammar checks and AI rewrites. A note can override it with lt-mode frontmatter.",
          render: setting => {
            setting.addDropdown(component => {
              component
                .addOptions(WRITING_MODES)
                .setValue(this.plugin.settings.writingMode ?? "neutral")
                .onChange(async value => {
                  if (isWritingMode(value)) {
                    this.plugin.settings.writingMode = value;
                    await this.plugin.saveSettings();
                  }
                });
            });
          }
        }
      ]
    };

    const aiSection: SettingsSection = {
      heading: "AI features",
      items: [
        {
          name: "Enable AI features",
          desc:
            "Show and run AI commands. Off by default. Rewrites send the selection through the gateway to the configured LLM.",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.enableAIFeatures ?? false)
                .onChange(async value => {
                  this.plugin.settings.enableAIFeatures = value;
                  await this.plugin.saveSettings();
                  // The category and auto-check toggles follow the master.
                  this.rerender();
                });
            });
          }
        },
        {
          name: "AI base URL",
          desc:
            "OpenAI-compatible endpoint, usually ending in /v1. Leave it empty to keep AI off and use LanguageTool only.",
          render: setting => {
            setting.addText(text => {
              text
                .setPlaceholder("http://127.0.0.1:11434/v1")
                .setValue(this.plugin.settings.llmBaseUrl ?? "")
                .onChange(async value => {
                  this.plugin.settings.llmBaseUrl = value.trim();
                  this.plugin.settings.llmModel = "";
                  await this.plugin.saveSettings();
                });
              text.inputEl.addEventListener("blur", () => {
                this.aiModels = [];
                this.aiModelsFetchedFor = undefined;
                this.rerender();
              });
            });
          }
        },
        {
          name: "AI API key",
          desc:
            "Stored in Obsidian's SecretStorage on this device. Leave it empty when the endpoint needs no key.",
          render: setting => {
            if (
              requireApiVersion("1.11.4") &&
              this.plugin.isSecretStorageAvailable()
            ) {
              setting.addComponent(el =>
                new SecretComponent(this.app, el)
                  .setValue(this.plugin.settings.llmApiKeySecretName ?? "")
                  .onChange(async value => {
                    this.plugin.settings.llmApiKeySecretName = value;
                    this.aiModels = [];
                    this.aiModelsFetchedFor = undefined;
                    await this.plugin.saveSettings();
                  })
              );
            } else {
              setting.setDesc(
                "Requires Obsidian 1.11.4 or newer for SecretStorage."
              );
            }
          }
        },
        {
          name: "AI model",
          desc:
            "Loaded from the endpoint. Refresh after changing the URL or key. AI stays off until a model is selected.",
          render: setting => {
            const configured = Boolean(
              this.plugin.settings.llmBaseUrl?.trim()
            );
            if (
              configured &&
              this.aiModelsFetchedFor !== this.plugin.settings.llmBaseUrl
            ) {
              this.aiModelsFetchedFor = this.plugin.settings.llmBaseUrl;
              void this.refreshAiModels().then(() => this.rerender());
            }
            setting.addDropdown(dropdown => {
              const current = this.plugin.settings.llmModel ?? "";
              for (const model of this.aiModels) {
                dropdown.addOption(model, model);
              }
              if (current && !this.aiModels.includes(current)) {
                dropdown.addOption(current, current);
              }
              dropdown
                .setValue(current)
                .setDisabled(!configured)
                .onChange(async value => {
                  this.plugin.settings.llmModel = value;
                  await this.plugin.saveSettings();
                });
            });
            setting.addButton(button => {
              button
                .setButtonText("Refresh")
                .setDisabled(!configured)
                .onClick(async () => {
                  await this.refreshAiModels();
                  this.rerender();
                });
            });
          }
        },
        {
          name: "AI max response tokens",
          desc:
            "Response budget in tokens. 4096 is enough for short rewrites. Long text and reasoning models may need 8192-32768; if a rewrite says the model ran out of tokens, raise this. Leave empty to use the gateway default.",
          render: setting => {
            setting.addText(text => {
              const current = this.plugin.settings.llmMaxTokens;
              text
                .setPlaceholder("4096")
                .setValue(current ? String(current) : "")
                .onChange(async raw => {
                  const value = raw.trim();
                  const parsed = /^\d+$/.test(value) ? Number(value) : Number.NaN;
                  this.plugin.settings.llmMaxTokens =
                    Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
                  await this.plugin.saveSettings();
                });
              text.inputEl.type = "number";
              text.inputEl.min = "256";
              text.inputEl.max = "65536";
            });
          }
        },
        {
          name: "Reasoning effort",
          desc:
            "How much the model may reason before answering. Only reasoning models honour this; others ignore it. Higher effort needs a higher response-token budget.",
          render: setting => {
            setting.addDropdown(dropdown => {
              dropdown
                .addOption("", "Default (server decides)")
                .addOption("low", "Low")
                .addOption("medium", "Medium")
                .addOption("high", "High")
                .setValue(this.plugin.settings.llmReasoningEffort ?? "")
                .onChange(async value => {
                  this.plugin.settings.llmReasoningEffort =
                    value === "low" || value === "medium" || value === "high"
                      ? value
                      : undefined;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "AI grammar corrections",
          desc:
            "Let the model fix spelling, grammar, and punctuation. On by default.",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.aiGrammar ?? true)
                .setDisabled(!(this.plugin.settings.enableAIFeatures ?? false))
                .onChange(async value => {
                  this.plugin.settings.aiGrammar = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "AI style suggestions",
          desc:
            "Let the model suggest wording, tone, and register changes. On by default.",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.aiStyle ?? true)
                .setDisabled(!(this.plugin.settings.enableAIFeatures ?? false))
                .onChange(async value => {
                  this.plugin.settings.aiStyle = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "AI vocabulary suggestions",
          desc:
            "Suggest the text's language for a word written in another one, for example German for an English word. On by default.",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.aiVocabulary ?? true)
                .setDisabled(!(this.plugin.settings.enableAIFeatures ?? false))
                .onChange(async value => {
                  this.plugin.settings.aiVocabulary = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "AI auto-check current sentence",
          desc:
            "After 4 seconds without typing, check the sentence around the cursor. Off by default; AI features must be enabled. LT checks still run instantly.",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.aiAutoCheck ?? false)
                .setDisabled(!(this.plugin.settings.enableAIFeatures ?? false))
                .onChange(async value => {
                  this.plugin.settings.aiAutoCheck = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        }
      ]
    };

    const dictionarySection: SettingsSection = {
      heading: "Dictionary",
      items: [
        {
          name: "Word meanings on hover",
          desc:
            "Show a short definition after hovering over a word. Off by default. Uses the downloaded dictionary, not the LLM.",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.dictionaryHover ?? false)
                .onChange(async value => {
                  this.plugin.settings.dictionaryHover = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Dictionary pair",
          desc: "German – German shows German definitions; the other pairs show translations.",
          render: setting => {
            setting.addDropdown(component => {
              for (const [pair, label] of Object.entries(DICTIONARY_PAIRS)) {
                component.addOption(pair, label);
              }
              component
                .setValue(this.plugin.settings.dictionaryPair ?? "de-de")
                .onChange(async value => {
                  this.plugin.settings.dictionaryPair = value as DictionaryPair;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Dictionary data",
          desc:
            "Downloaded from FreeDict and Wiktionary by the gateway. About 400 MB while downloading; the result is kept under data/wordbook.",
          render: setting => {
            const statusEl = setting.descEl.createDiv({
              cls: "lt-dict-status",
              text: "Checking…"
            });
            const update = async (): Promise<boolean> => {
              const status = await fetchDictionaryStatus(
                this.plugin.settings.serverUrl
              );
              statusEl.setText(
                Object.entries(DICTIONARY_PAIRS)
                  .map(
                    ([pair, label]) =>
                      `${label}: ${describeDictionaryStatus(status, pair)}`
                  )
                  .join(" ")
              );
              if (status?.error) {
                statusEl.setText(`${statusEl.getText()} ${status.error}`);
              }
              return status?.building ?? false;
            };
            setting.addButton(button => {
              button.setButtonText("Download").onClick(async () => {
                const response = await requestUrl({
                  url: `${this.plugin.settings.serverUrl}/dictionary/install`,
                  method: "POST",
                  throw: false
                });
                if (response.status !== 202) {
                  new Notice("Could not start the dictionary download.");
                } else {
                  new Notice(
                    "Dictionary download started. This takes a few minutes."
                  );
                }
                if (await update()) {
                  this.ensureDictionaryPoll(update);
                }
              });
            });
            void update()
              .then(building => {
                if (building) {
                  this.ensureDictionaryPoll(update);
                }
              })
              .catch(() => undefined);
          }
        }
      ]
    };

    const ruleSection: SettingsSection = {
      heading: "Rule Categories",
      items: [
        {
          name: "Picky Mode",
          desc:
            "Provides more style and tonality suggestions, detects long or complex sentences, recognizes colloquialism and redundancies, proactively suggests synonyms for commonly overused words",
          render: setting => {
            setting.addToggle(component => {
              component
                .setValue(this.plugin.settings.pickyMode)
                .onChange(async value => {
                  this.plugin.settings.pickyMode = value;
                  await this.plugin.saveSettings();
                });
            });
          }
        },
        {
          name: "Other rule categories",
          desc: "Enter a comma-separated list of categories",
          render: setting => {
            setting.addText(text =>
              text
                .setPlaceholder("Eg. CATEGORY_1,CATEGORY_2")
                .setValue(this.plugin.settings.ruleOtherCategories ?? "")
                .onChange(async value => {
                  this.plugin.settings.ruleOtherCategories = value.replace(
                    /\s+/g,
                    ""
                  );
                  await this.plugin.saveSettings();
                })
            );
            appendRuleListLink(setting);
          }
        },
        {
          name: "Enable Specific Rules",
          desc: "Enter a comma-separated list of rules",
          render: setting => {
            setting.addText(text =>
              text
                .setPlaceholder("Eg. RULE_1,RULE_2")
                .setValue(this.plugin.settings.ruleOtherRules ?? "")
                .onChange(async value => {
                  this.plugin.settings.ruleOtherRules = value.replace(
                    /\s+/g,
                    ""
                  );
                  await this.plugin.saveSettings();
                })
            );
            appendRuleListLink(setting);
          }
        },
        {
          name: "Disable Specific Categories",
          desc: "Enter a comma-separated list of categories",
          render: setting => {
            setting.addText(text =>
              text
                .setPlaceholder("Eg. CATEGORY_1,CATEGORY_2")
                .setValue(this.plugin.settings.ruleOtherDisabledCategories ?? "")
                .onChange(async value => {
                  this.plugin.settings.ruleOtherDisabledCategories =
                    value.replace(/\s+/g, "");
                  await this.plugin.saveSettings();
                })
            );
            appendRuleListLink(setting);
          }
        },
        {
          name: "Disable Specific Rules",
          desc: "Enter a comma-separated list of rules",
          render: setting => {
            setting.addText(text =>
              text
                .setPlaceholder("Eg. RULE_1,RULE_2")
                .setValue(this.plugin.settings.ruleOtherDisabledRules ?? "")
                .onChange(async value => {
                  this.plugin.settings.ruleOtherDisabledRules = value.replace(
                    /\s+/g,
                    ""
                  );
                  await this.plugin.saveSettings();
                })
            );
            appendRuleListLink(setting);
          }
        }
      ]
    };

    return [
      mainSection,
      writingSection,
      aiSection,
      dictionarySection,
      varietySection,
      ruleSection
    ];
  }

  // Declarative settings (Obsidian 1.13+): rendering and settings search are
  // driven by these definitions
  public getSettingDefinitions(): SettingDefinitionItem[] {
    return this.getSections().map(section => ({
      type: "group" as const,
      heading: section.heading,
      items: section.items
    }));
  }

  // Imperative fallback for Obsidian versions older than 1.13, rendering the
  // same definitions
  public display(): void {
    const { containerEl } = this;
    containerEl.empty();
    for (const section of this.getSections()) {
      if (section.heading) {
        new Setting(containerEl).setName(section.heading).setHeading();
      }
      for (const def of section.items) {
        const setting = new Setting(containerEl).setName(def.name);
        if (def.desc) {
          setting.setDesc(def.desc);
        }
        def.render(setting);
      }
    }
  }
}
