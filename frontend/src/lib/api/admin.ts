/**
 * Admin API client for user and account management.
 */
import { axiosInstance } from '../axios';

export interface UserSession {
  id: string;
  created_at: string;
  expires_at: string;
  ip_address: string;
  user_agent: string;
}

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  event_type: string;
  user_id: number | null;
  username: string | null;
  outcome: string;
  source_ip: string;
  user_agent: string;
  details: Record<string, any>;
}

export interface AccountStatusReport {
  total_users: number;
  active_users: number;
  inactive_users: number;
  mfa_enabled_users: number;
  password_expired_users: number;
}

export interface UserSearchResult {
  uuid: string;
  email: string;
  full_name: string;
  role: string;
  auth_type: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export class AdminApi {
  // Account Management
  static async resetUserPassword(
    userUuid: string,
    newPassword: string,
    forceChange: boolean = true
  ): Promise<void> {
    await axiosInstance.post(`/admin/users/${userUuid}/reset-password`, null, {
      params: { new_password: newPassword, force_change: forceChange },
    });
  }

  static async unlockAccount(userUuid: string): Promise<void> {
    await axiosInstance.post(`/admin/users/${userUuid}/unlock`);
  }

  static async lockAccount(userUuid: string, reason: string): Promise<void> {
    await axiosInstance.post(`/admin/users/${userUuid}/lock`, null, {
      params: { reason },
    });
  }

  static async terminateUserSessions(userUuid: string): Promise<{ sessions_terminated: number }> {
    const response = await axiosInstance.delete(`/admin/users/${userUuid}/sessions`);
    return response.data;
  }

  static async getUserSessions(userUuid: string): Promise<{ sessions: UserSession[] }> {
    const response = await axiosInstance.get(`/admin/users/${userUuid}/sessions`);
    return response.data;
  }

  static async changeUserRole(userUuid: string, newRole: string): Promise<void> {
    await axiosInstance.put(`/admin/users/${userUuid}/role`, null, {
      params: { new_role: newRole },
    });
  }

  static async resetUserMFA(userUuid: string): Promise<void> {
    await axiosInstance.post(`/admin/users/${userUuid}/mfa/reset`);
  }

  // User Search
  static async searchUsers(params: {
    query?: string;
    role?: string;
    auth_type?: string;
    is_active?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<{ total: number; users: UserSearchResult[] }> {
    const response = await axiosInstance.get('/admin/users/search', { params });
    return response.data;
  }

  // Audit Logs
  static async getAuditLogs(params: {
    start_date?: string;
    end_date?: string;
    event_type?: string;
    user_id?: number;
    outcome?: string;
    limit?: number;
    offset?: number;
  }): Promise<AuditLogEntry[]> {
    const response = await axiosInstance.get('/admin/audit-logs', { params });
    const data = response.data;
    return Array.isArray(data) ? data : data.logs ?? [];
  }

  static async exportAuditLogs(
    format: 'csv' | 'json',
    startDate?: string,
    endDate?: string
  ): Promise<Blob> {
    const response = await axiosInstance.get('/admin/audit-logs/export', {
      params: { export_format: format, start_date: startDate, end_date: endDate },
      responseType: 'blob',
    });
    return response.data;
  }

  // Reports
  static async getAccountStatusReport(): Promise<AccountStatusReport> {
    const response = await axiosInstance.get('/admin/reports/account-status');
    return response.data;
  }
}
