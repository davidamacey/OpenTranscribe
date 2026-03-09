import { axiosInstance } from '../axios';

export interface MediaSource {
  id: string;
  hostname: string;
  provider_type: string;
  username: string;
  password: string;
  verify_ssl: boolean;
  label: string;
}

export interface MediaSourceCreate {
  hostname: string;
  provider_type?: string;
  username?: string;
  password?: string;
  verify_ssl?: boolean;
  label?: string;
}

export interface MediaSourceUpdate {
  hostname?: string;
  provider_type?: string;
  username?: string;
  password?: string;
  verify_ssl?: boolean;
  label?: string;
}

export async function getMediaSources(): Promise<MediaSource[]> {
  const resp = await axiosInstance.get<{ sources: MediaSource[] }>('/admin/settings/media-sources');
  return resp.data.sources;
}

export async function addMediaSource(source: MediaSourceCreate): Promise<MediaSource> {
  const resp = await axiosInstance.post<MediaSource>('/admin/settings/media-sources', source);
  return resp.data;
}

export async function updateMediaSource(
  id: string,
  update: MediaSourceUpdate
): Promise<MediaSource> {
  const resp = await axiosInstance.put<MediaSource>(`/admin/settings/media-sources/${id}`, update);
  return resp.data;
}

export async function deleteMediaSource(id: string): Promise<void> {
  await axiosInstance.delete(`/admin/settings/media-sources/${id}`);
}
