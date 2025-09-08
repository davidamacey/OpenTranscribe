/**
 * API client for LLM settings management
 */

import axiosInstance from '../axios';

export interface LLMProvider {
  OPENAI: 'openai';
  VLLM: 'vllm';
  OLLAMA: 'ollama';
  CLAUDE: 'claude';
  ANTHROPIC: 'anthropic';
  OPENROUTER: 'openrouter';
  CUSTOM: 'custom';
}

export interface ConnectionStatus {
  SUCCESS: 'success';
  FAILED: 'failed';
  PENDING: 'pending';
  UNTESTED: 'untested';
}

export interface UserLLMSettings {
  id: number;
  user_id: number;
  name: string;
  provider: keyof LLMProvider;
  model_name: string;
  base_url?: string;
  max_tokens: number;
  temperature: string;
  timeout: number;
  is_active: boolean;
  last_tested?: string;
  test_status?: keyof ConnectionStatus;
  test_message?: string;
  has_api_key: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserLLMSettingsCreate {
  name: string;
  provider: keyof LLMProvider;
  model_name: string;
  api_key?: string;
  base_url?: string;
  max_tokens?: number;
  temperature?: string;
  timeout?: number;
  is_active?: boolean;
}

export interface UserLLMSettingsUpdate {
  name?: string;
  provider?: keyof LLMProvider;
  model_name?: string;
  api_key?: string;
  base_url?: string;
  max_tokens?: number;
  temperature?: string;
  timeout?: number;
  is_active?: boolean;
}

export interface ConnectionTestRequest {
  provider: keyof LLMProvider;
  model_name: string;
  api_key?: string;
  base_url?: string;
  timeout?: number;
}

export interface ConnectionTestResponse {
  success: boolean;
  status: keyof ConnectionStatus;
  message: string;
  response_time_ms?: number;
  model_info?: any;
}

export interface ProviderDefaults {
  provider: keyof LLMProvider;
  default_model: string;
  default_base_url?: string;
  requires_api_key: boolean;
  supports_custom_url: boolean;
  max_context_length?: number;
  description: string;
}

export interface SupportedProvidersResponse {
  providers: ProviderDefaults[];
}

export interface UserLLMConfigurationsList {
  configurations: UserLLMSettings[];
  active_configuration_id?: number;
  total: number;
}

export interface SetActiveConfigRequest {
  configuration_id: number;
}

export interface LLMSettingsStatus {
  has_settings: boolean;
  active_configuration?: UserLLMSettings;
  total_configurations: number;
  using_system_default: boolean;
}

export class LLMSettingsApi {
  private static readonly BASE_PATH = '/llm-settings';

  /**
   * Get supported LLM providers with their default configurations
   */
  static async getSupportedProviders(): Promise<SupportedProvidersResponse> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/providers`);
    return response.data;
  }

  /**
   * Get status information about user's LLM settings
   */
  static async getStatus(): Promise<LLMSettingsStatus> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/status`);
    return response.data;
  }

  /**
   * Get all user's LLM configurations
   */
  static async getUserConfigurations(): Promise<UserLLMConfigurationsList> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/`);
    return response.data;
  }


  /**
   * Create new LLM configuration for the current user
   */
  static async createSettings(settings: UserLLMSettingsCreate): Promise<UserLLMSettings> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/`, settings);
    return response.data;
  }

  /**
   * Update an existing LLM configuration
   */
  static async updateSettings(configId: number, settings: UserLLMSettingsUpdate): Promise<UserLLMSettings> {
    const response = await axiosInstance.put(`${this.BASE_PATH}/config/${configId}`, settings);
    return response.data;
  }

  /**
   * Delete a specific LLM configuration
   */
  static async deleteConfiguration(configId: number): Promise<{ detail: string }> {
    const response = await axiosInstance.delete(`${this.BASE_PATH}/config/${configId}`);
    return response.data;
  }

  /**
   * Delete all user's LLM configurations (revert to system defaults)
   */
  static async deleteSettings(): Promise<{ detail: string }> {
    const response = await axiosInstance.delete(`${this.BASE_PATH}/all`);
    return response.data;
  }

  /**
   * Set active LLM configuration
   */
  static async setActiveConfiguration(configId: number): Promise<UserLLMSettings> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/set-active`, {
      configuration_id: configId
    });
    return response.data;
  }

  /**
   * Test connection to LLM provider without saving settings
   */
  static async testConnection(testRequest: ConnectionTestRequest): Promise<ConnectionTestResponse> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/test`, testRequest);
    return response.data;
  }

  /**
   * Test connection using current user's active LLM configuration
   */
  static async testCurrentSettings(): Promise<ConnectionTestResponse> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/test-current`);
    return response.data;
  }

  /**
   * Test connection using a specific configuration
   */
  static async testConfiguration(configId: number): Promise<ConnectionTestResponse> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/test-config/${configId}`);
    return response.data;
  }

  /**
   * Get available models from an Ollama instance
   */
  static async getOllamaModels(baseUrl: string): Promise<{
    success: boolean;
    models: Array<{
      name: string;
      size: number;
      modified_at: string;
      digest: string;
      details: any;
      display_name: string;
    }>;
    total: number;
    message: string;
  }> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/ollama/models`, {
      params: { base_url: baseUrl }
    });
    return response.data;
  }

  /**
   * Test the encryption system
   */
  static async testEncryption(): Promise<{ status: string; message: string }> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/encryption-test`);
    return response.data;
  }

  /**
   * Get provider-specific default configuration
   */
  static getProviderDefaults(provider: keyof LLMProvider): Partial<UserLLMSettingsCreate> {
    const providerDefaults: Record<keyof LLMProvider, Partial<UserLLMSettingsCreate>> = {
      openai: {
        provider: 'openai',
        model_name: 'gpt-4o-mini',
        base_url: 'https://api.openai.com/v1',
        max_tokens: 16000,
        temperature: '0.3',
        timeout: 60
      },
      vllm: {
        provider: 'vllm',
        model_name: 'gpt-oss',
        base_url: 'http://localhost:8012/v1',
        max_tokens: 8192,
        temperature: '0.3',
        timeout: 60
      },
      ollama: {
        provider: 'ollama',
        model_name: 'llama2:7b-chat',
        base_url: 'http://localhost:11434/v1',
        max_tokens: 4096,
        temperature: '0.3',
        timeout: 60
      },
      claude: {
        provider: 'claude',
        model_name: 'claude-3-haiku-20240307',
        base_url: 'https://api.anthropic.com/v1',
        max_tokens: 4096,
        temperature: '0.3',
        timeout: 60
      },
      anthropic: {
        provider: 'anthropic',
        model_name: 'claude-3-haiku-20240307',
        base_url: 'https://api.anthropic.com/v1',
        max_tokens: 4096,
        temperature: '0.3',
        timeout: 60
      },
      openrouter: {
        provider: 'openrouter',
        model_name: 'anthropic/claude-3-haiku',
        base_url: 'https://openrouter.ai/api/v1',
        max_tokens: 4096,
        temperature: '0.3',
        timeout: 60
      },
      custom: {
        provider: 'custom',
        model_name: '',
        base_url: '',
        max_tokens: 4096,
        temperature: '0.3',
        timeout: 60
      }
    };

    return providerDefaults[provider] || {};
  }

  /**
   * Get user-friendly provider name
   */
  static getProviderDisplayName(provider: keyof LLMProvider): string {
    const displayNames: Record<keyof LLMProvider, string> = {
      openai: 'OpenAI',
      vllm: 'vLLM',
      ollama: 'Ollama',
      claude: 'Claude (Anthropic)',
      anthropic: 'Anthropic Claude',
      openrouter: 'OpenRouter',
      custom: 'Custom Provider'
    };

    return displayNames[provider] || provider;
  }

  /**
   * Get connection status display information
   */
  static getStatusDisplay(status?: keyof ConnectionStatus): { text: string; class: string; icon: string } {
    switch (status) {
      case 'success':
        return { text: 'Connected', class: 'success', icon: '✓' };
      case 'failed':
        return { text: 'Failed', class: 'error', icon: '✗' };
      case 'pending':
        return { text: 'Testing...', class: 'pending', icon: '...' };
      case 'untested':
      default:
        return { text: 'Untested', class: 'neutral', icon: '?' };
    }
  }
}