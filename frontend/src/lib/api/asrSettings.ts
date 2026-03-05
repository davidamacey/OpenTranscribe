/**
 * API client for ASR settings management
 */

import axiosInstance from '../axios';
import { get } from 'svelte/store';
import { t } from '$stores/locale';

export type ASRProvider = 'deepgram' | 'whisperx';

export type ConnectionStatus = 'success' | 'failed' | 'pending' | 'untested';

export interface UserASRSettings {
  uuid: string;
  user_id: string;
  name: string;
  provider: ASRProvider;
  model_name: string;
  is_active: boolean;
  last_tested?: string;
  test_status?: ConnectionStatus;
  test_message?: string;
  has_api_key: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserASRSettingsCreate {
  name: string;
  provider: ASRProvider;
  model_name: string;
  api_key?: string;
  is_active?: boolean;
}

export interface UserASRSettingsUpdate {
  name?: string;
  provider?: ASRProvider;
  model_name?: string;
  api_key?: string;
  is_active?: boolean;
}

export interface ASRConnectionTestRequest {
  provider: ASRProvider;
  model_name: string;
  api_key?: string;
  config_id?: string;
}

export interface ASRConnectionTestResponse {
  success: boolean;
  status: ConnectionStatus;
  message: string;
  response_time_ms?: number;
}

export interface ASRProviderDefaults {
  provider: ASRProvider;
  default_model: string;
  requires_api_key: boolean;
  description: string;
}

export interface SupportedASRProvidersResponse {
  providers: ASRProviderDefaults[];
}

export interface UserASRConfigurationsList {
  configurations: UserASRSettings[];
  active_configuration_id?: string;
  total: number;
}

export interface ASRSettingsStatus {
  has_settings: boolean;
  active_configuration?: UserASRSettings;
  total_configurations: number;
  using_env_default: boolean;
}

export class ASRSettingsApi {
  private static readonly BASE_PATH = '/asr-settings';

  /**
   * Get supported ASR providers with their default configurations
   */
  static async getSupportedProviders(): Promise<SupportedASRProvidersResponse> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/providers`);
    return response.data;
  }

  /**
   * Get status information about user's ASR settings
   */
  static async getStatus(): Promise<ASRSettingsStatus> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/status`);
    return response.data;
  }

  /**
   * Get all user's ASR configurations
   */
  static async getUserConfigurations(): Promise<UserASRConfigurationsList> {
    const response = await axiosInstance.get(`${this.BASE_PATH}`);
    return response.data;
  }

  /**
   * Create new ASR configuration for the current user
   */
  static async createSettings(settings: UserASRSettingsCreate): Promise<UserASRSettings> {
    const response = await axiosInstance.post(`${this.BASE_PATH}`, settings);
    return response.data;
  }

  /**
   * Update an existing ASR configuration
   */
  static async updateSettings(
    configId: string,
    settings: UserASRSettingsUpdate
  ): Promise<UserASRSettings> {
    const response = await axiosInstance.put(`${this.BASE_PATH}/config/${configId}`, settings);
    return response.data;
  }

  /**
   * Delete a specific ASR configuration
   */
  static async deleteConfiguration(configId: string): Promise<{ detail: string }> {
    const response = await axiosInstance.delete(`${this.BASE_PATH}/config/${configId}`);
    return response.data;
  }

  /**
   * Set active ASR configuration
   */
  static async setActiveConfiguration(configId: string): Promise<UserASRSettings> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/set-active`, {
      configuration_id: configId,
    });
    return response.data;
  }

  /**
   * Test connection to ASR provider without saving settings
   */
  static async testConnection(testRequest: ASRConnectionTestRequest): Promise<ASRConnectionTestResponse> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/test`, testRequest);
    return response.data;
  }

  /**
   * Test connection using a specific stored configuration
   */
  static async testConfiguration(configId: string): Promise<ASRConnectionTestResponse> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/test-config/${configId}`);
    return response.data;
  }

  /**
   * Get the decrypted API key for a specific configuration
   */
  static async getConfigApiKey(configId: string): Promise<{ api_key: string | null }> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/config/${configId}/api-key`);
    return response.data;
  }

  /**
   * Get provider-specific default configuration
   */
  static getProviderDefaults(provider: ASRProvider): Partial<UserASRSettingsCreate> {
    const providerDefaults: Record<string, Partial<UserASRSettingsCreate>> = {
      deepgram: {
        provider: 'deepgram',
        model_name: 'nova-3-medical',
      },
      whisperx: {
        provider: 'whisperx',
        model_name: 'large-v2',
      },
    };

    return providerDefaults[provider] || {};
  }

  /**
   * Get user-friendly provider name
   */
  static getProviderDisplayName(provider: ASRProvider | string): string {
    const displayNames: Record<string, string> = {
      deepgram: 'Deepgram',
      whisperx: 'WhisperX',
    };

    return displayNames[provider] || provider;
  }

  /**
   * Get connection status display information
   */
  static getStatusDisplay(status?: ConnectionStatus): {
    text: string;
    class: string;
    icon: string;
  } {
    const tFunc = get(t);
    switch (status) {
      case 'success':
        return {
          text: tFunc('settings.asrProvider.status.connected') || 'Connected',
          class: 'success',
          icon: '✓',
        };
      case 'failed':
        return {
          text: tFunc('settings.asrProvider.status.failed') || 'Failed',
          class: 'error',
          icon: '✗',
        };
      case 'pending':
        return {
          text: tFunc('settings.asrProvider.status.testing') || 'Testing...',
          class: 'pending',
          icon: '...',
        };
      case 'untested':
      default:
        return {
          text: tFunc('settings.asrProvider.status.untested') || 'Not tested',
          class: 'neutral',
          icon: '?',
        };
    }
  }
}
