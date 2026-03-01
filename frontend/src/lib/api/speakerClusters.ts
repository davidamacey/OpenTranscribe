/**
 * API client for speaker clustering operations
 */
import axiosInstance from '../axios';
import type {
  SpeakerCluster,
  SpeakerClusterDetail,
  SpeakerInboxItem,
  PaginatedResponse,
  BatchVerifyResponse,
  ReclusterResponse,
} from '$lib/types/speakerCluster';

export async function listClusters(
  page = 1,
  perPage = 20,
  search?: string,
  hasLabel?: boolean
): Promise<PaginatedResponse<SpeakerCluster>> {
  const params: Record<string, string | number | boolean> = { page, per_page: perPage };
  if (search) params.search = search;
  if (hasLabel !== undefined) params.has_label = hasLabel;
  const response = await axiosInstance.get('/speaker-clusters', { params });
  return response.data;
}

export async function getClusterDetail(uuid: string): Promise<SpeakerClusterDetail> {
  const response = await axiosInstance.get(`/speaker-clusters/${uuid}`);
  return response.data;
}

export async function updateCluster(
  uuid: string,
  data: { label?: string; description?: string }
): Promise<SpeakerCluster> {
  const response = await axiosInstance.put(`/speaker-clusters/${uuid}`, data);
  return response.data;
}

export async function deleteCluster(uuid: string): Promise<void> {
  await axiosInstance.delete(`/speaker-clusters/${uuid}`);
}

export async function mergeClusters(
  sourceUuid: string,
  targetUuid: string
): Promise<SpeakerCluster> {
  const response = await axiosInstance.post(`/speaker-clusters/${sourceUuid}/merge/${targetUuid}`);
  return response.data;
}

export async function splitCluster(uuid: string, speakerUuids: string[]): Promise<SpeakerCluster> {
  const response = await axiosInstance.post(`/speaker-clusters/${uuid}/split`, {
    speaker_uuids: speakerUuids,
  });
  return response.data;
}

export async function promoteCluster(
  uuid: string,
  name: string,
  description?: string
): Promise<{ profile_uuid: string; profile_name: string; message: string }> {
  const response = await axiosInstance.post(`/speaker-clusters/${uuid}/promote`, {
    name,
    description,
  });
  return response.data;
}

export async function triggerRecluster(
  force = false,
  threshold?: number
): Promise<ReclusterResponse> {
  const response = await axiosInstance.post('/speaker-clusters/recluster', {
    force,
    threshold,
  });
  return response.data;
}

export async function getUnverifiedSpeakers(
  page = 1,
  perPage = 20
): Promise<PaginatedResponse<SpeakerInboxItem>> {
  const response = await axiosInstance.get('/speaker-clusters/unverified/inbox', {
    params: { page, per_page: perPage },
  });
  return response.data;
}

export async function batchVerifySpeakers(
  speakerUuids: string[],
  action: 'accept' | 'assign' | 'name',
  profileUuid?: string,
  displayName?: string
): Promise<BatchVerifyResponse> {
  const response = await axiosInstance.post('/speaker-clusters/batch-verify', {
    speaker_uuids: speakerUuids,
    action,
    profile_uuid: profileUuid,
    display_name: displayName,
  });
  return response.data;
}

export function getAudioClipUrl(speakerUuid: string): string {
  return `/api/speaker-clusters/speakers/${speakerUuid}/audio-clip`;
}
