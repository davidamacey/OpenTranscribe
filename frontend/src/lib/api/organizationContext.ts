/**
 * API service for organization context settings
 */

import axiosInstance from '../axios';

export interface OrganizationContextSettings {
  context_text: string;
  include_in_default_prompts: boolean;
  include_in_custom_prompts: boolean;
}

export interface OrganizationContextUpdate {
  context_text?: string;
  include_in_default_prompts?: boolean;
  include_in_custom_prompts?: boolean;
}

export async function getOrganizationContext(): Promise<OrganizationContextSettings> {
  const response = await axiosInstance.get('/user-settings/organization-context');
  return response.data;
}

export async function updateOrganizationContext(
  settings: OrganizationContextUpdate
): Promise<OrganizationContextSettings> {
  const response = await axiosInstance.put('/user-settings/organization-context', settings);
  return response.data;
}

export async function resetOrganizationContext(): Promise<{
  message: string;
  default_settings: OrganizationContextSettings;
}> {
  const response = await axiosInstance.delete('/user-settings/organization-context');
  return response.data;
}
