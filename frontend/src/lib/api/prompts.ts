/**
 * API client for prompts management
 */

import axiosInstance from "../axios";

export interface SummaryPrompt {
  uuid: string; // UUID - primary identifier from backend
  name: string;
  description: string | null;
  prompt_text: string;
  is_system_default: boolean;
  user_id: string | null; // UUID
  content_type: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SummaryPromptCreate {
  name: string;
  description?: string;
  prompt_text: string;
  content_type?: string;
  is_active?: boolean;
}

export interface SummaryPromptUpdate {
  name?: string;
  description?: string;
  prompt_text?: string;
  content_type?: string;
  is_active?: boolean;
}

export interface SummaryPromptList {
  prompts: SummaryPrompt[];
  total: number;
  page: number;
  size: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ActivePromptResponse {
  active_prompt_id: string | null; // UUID
  active_prompt: SummaryPrompt | null;
}

export interface ActivePromptSelection {
  prompt_id: string; // UUID
}

export class PromptsApi {
  private static readonly BASE_PATH = "/prompts";

  /**
   * Get all prompts with filtering options
   */
  static async getPrompts(
    params: {
      include_system?: boolean;
      include_user?: boolean;
      limit?: number;
      content_type?: string;
    } = {},
  ): Promise<SummaryPromptList> {
    const queryParams = new URLSearchParams();

    if (params.include_system !== undefined) {
      queryParams.append("include_system", params.include_system.toString());
    }
    if (params.include_user !== undefined) {
      queryParams.append("include_user", params.include_user.toString());
    }
    if (params.limit !== undefined) {
      queryParams.append("limit", params.limit.toString());
    }
    if (params.content_type) {
      queryParams.append("content_type", params.content_type);
    }

    const response = await axiosInstance.get(
      `${this.BASE_PATH}/?${queryParams.toString()}`,
    );
    return response.data;
  }

  /**
   * Get currently active prompt
   */
  static async getActivePrompt(): Promise<ActivePromptResponse> {
    const response = await axiosInstance.get(
      `${this.BASE_PATH}/active/current`,
    );
    return response.data;
  }

  /**
   * Set active prompt
   */
  static async setActivePrompt(
    selection: ActivePromptSelection,
  ): Promise<void> {
    await axiosInstance.post(`${this.BASE_PATH}/active/set`, selection);
  }

  /**
   * Create a new prompt
   */
  static async createPrompt(
    prompt: SummaryPromptCreate,
  ): Promise<SummaryPrompt> {
    const response = await axiosInstance.post(`${this.BASE_PATH}/`, prompt);
    return response.data;
  }

  /**
   * Update an existing prompt
   */
  static async updatePrompt(
    id: string,
    prompt: SummaryPromptUpdate,
  ): Promise<SummaryPrompt> {
    const response = await axiosInstance.put(`${this.BASE_PATH}/${id}`, prompt);
    return response.data;
  }

  /**
   * Delete a prompt
   */
  static async deletePrompt(id: string): Promise<void> {
    await axiosInstance.delete(`${this.BASE_PATH}/${id}`);
  }

  /**
   * Get a single prompt by ID
   */
  static async getPrompt(id: string): Promise<SummaryPrompt> {
    const response = await axiosInstance.get(`${this.BASE_PATH}/${id}`);
    return response.data;
  }
}
