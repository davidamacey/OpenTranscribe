<script lang="ts">
  import { locale, SUPPORTED_LANGUAGES, t } from "$stores/locale";
  import { toastStore } from "$stores/toast";

  // Current language selection
  let selectedLanguage = $locale;

  // Update selection when locale changes externally
  $: selectedLanguage = $locale;

  function handleLanguageChange() {
    if (selectedLanguage !== $locale) {
      locale.set(selectedLanguage);
      toastStore.success($t("settings.language.changed"));
    }
  }

  // Get current language info
  $: currentLanguage = SUPPORTED_LANGUAGES.find((l) => l.code === $locale);
</script>

<div class="language-settings">
  <div class="form-group">
    <label for="ui-language" class="form-label">
      {$t("settings.language.selectLabel")}
    </label>
    <select
      id="ui-language"
      class="form-select"
      bind:value={selectedLanguage}
      on:change={handleLanguageChange}
    >
      {#each SUPPORTED_LANGUAGES as lang}
        <option value={lang.code}>
          {lang.nativeName} ({lang.name})
        </option>
      {/each}
    </select>
    <p class="input-hint">{$t("settings.language.hint")}</p>
  </div>

  <div class="language-preview">
    <div class="preview-item">
      <span class="preview-label">{$t("settings.language.selectLabel")}:</span>
      <span class="preview-value">
        {currentLanguage?.nativeName || SUPPORTED_LANGUAGES[0].nativeName} ({currentLanguage?.name ||
          SUPPORTED_LANGUAGES[0].name})
      </span>
    </div>
  </div>
</div>

<style>
  .language-settings {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .form-label {
    font-weight: 500;
    color: var(--text-color);
    font-size: 0.875rem;
  }

  .form-select {
    padding: 0.625rem 0.75rem;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background-color: var(--surface-color);
    color: var(--text-color);
    font-size: 0.875rem;
    transition:
      border-color 0.15s,
      box-shadow 0.15s;
    cursor: pointer;
    max-width: 300px;
  }

  .form-select:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px var(--primary-light);
  }

  .form-select:hover {
    border-color: var(--primary-color);
  }

  .input-hint {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0;
  }

  .language-preview {
    background-color: var(--background-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
  }

  .preview-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .preview-label {
    font-size: 0.8125rem;
    color: var(--text-secondary);
  }

  .preview-value {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-color);
  }
</style>
