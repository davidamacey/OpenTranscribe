# Frontend Authentication & Admin UI Implementation Plan

This document contains a detailed implementation plan for the frontend authentication and admin UI components. It can be used as a prompt to continue development in a separate session.

---

## Related Documentation

### Plan Files
- **Main Security Plan**: `~/.claude/plans/joyful-meandering-ripple.md` - Comprehensive authentication security fixes plan (111KB)
- **This is Initiative 2 & 3** from the main plan - Super Admin Configuration UI & FedRAMP Control Remediation

### Reference Documentation
| Document | Purpose |
|----------|---------|
| `docs/FIPS_140_3_COMPLIANCE.md` | FIPS 140-3 cryptographic standards |
| `docs/FIPS_COMPLIANCE.md` | General FIPS compliance guide |
| `docs/SECURITY.md` | Security policy and controls |
| `docs/SUPER_ADMIN_GUIDE.md` | Super admin role documentation |
| `docs/PKI_SETUP.md` | PKI/X.509 certificate setup |
| `docs/KEYCLOAK_SETUP.md` | Keycloak/OIDC configuration |
| `docs/LDAP_AUTH.md` | LDAP/Active Directory setup |
| `example_env.txt` | Environment variable reference (includes new security settings) |

### Backend Files Created (Security Fixes)
| File | Status |
|------|--------|
| `backend/alembic/versions/v070_add_pki_security_enhancements.py` | ✅ Migration created |
| `backend/tests/test_admin_security.py` | ✅ Tests created |
| `backend/tests/test_mfa_security.py` | ✅ Tests created |
| `backend/tests/test_fedramp_controls.py` | ✅ Tests created |
| `backend/tests/test_pki_auth.py` | ✅ Tests created |

### Frontend Files Created (Partial - Need Fixes)
| File | Status | Notes |
|------|--------|-------|
| `frontend/src/lib/api/authConfig.ts` | ⚠️ Created but backend not ready | Database-backed config not implemented |
| `frontend/src/lib/api/admin.ts` | ⚠️ Created | Needs import path fix |
| `frontend/src/components/settings/AuthenticationSettings.svelte` | ⚠️ Created but backend not ready | Depends on authConfig.ts |
| `frontend/src/components/LoginBanner.svelte` | ✅ Can be used | Backend endpoint exists |

---

## Context & Prerequisites

### What's Already Done (Backend)

The following backend work has been completed:

1. **Security Fixes Applied:**
   - Password reset moved to request body (not query params)
   - MFA blacklist fail-secure mode (`MFA_REQUIRE_REDIS` setting)
   - Token rotation atomic (create before revoke)
   - Admin check includes `super_admin` role
   - Concurrent session atomic locking
   - JWT key length validation
   - PKI certificate expiration validation
   - Audit log fallback to file
   - Configurable TOTP window
   - Algorithm fallback audit logging
   - Lockout Redis transaction fix

2. **New Backend Endpoints Available:**
   - `POST /api/admin/users/{uuid}/reset-password` - Body: `{new_password, force_change}`
   - `POST /api/admin/users/{uuid}/lock` - Lock user account
   - `POST /api/admin/users/{uuid}/unlock` - Unlock user account
   - `DELETE /api/admin/users/{uuid}/sessions` - Terminate all user sessions
   - `GET /api/admin/users/{uuid}/sessions` - View user's active sessions
   - `GET /api/auth/banner` - Get login banner (public)
   - `POST /api/auth/banner/acknowledge` - Acknowledge banner

3. **New Configuration Settings:**
   - `TOTP_VALID_WINDOW` - Configurable TOTP clock drift
   - `MFA_REQUIRE_REDIS` - Fail-secure MFA mode
   - `AUDIT_LOG_FALLBACK_ENABLED` - File fallback for audit
   - `CONCURRENT_SESSION_POLICY` - terminate_oldest or reject
   - `FIPS_VERSION` - 140-2 or 140-3 mode

### Existing Frontend Structure

```
frontend/src/
├── components/
│   ├── settings/
│   │   ├── SecuritySettings.svelte    # Existing - needs enhancement
│   │   └── ... other settings
│   ├── Navbar.svelte
│   ├── SettingsModal.svelte           # Existing - needs new sections
│   └── ...
├── lib/
│   ├── api/
│   │   └── ... existing API clients
│   └── i18n/locales/                  # Translation files
├── routes/
│   └── login/+page.svelte             # Existing login page
└── stores/
    ├── auth.ts                        # Auth store
    └── settingsModalStore.ts          # Settings modal state
```

---

## Implementation Tasks

### Phase 1: Login Banner (FedRAMP AC-8)

**Priority: HIGH** - Required for FedRAMP compliance

#### 1.1 Create LoginBanner Component

**File:** `/frontend/src/components/LoginBanner.svelte`

```svelte
<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { t } from '$lib/i18n';

  const dispatch = createEventDispatcher();

  interface BannerResponse {
    enabled: boolean;
    text: string;
    classification: string;
    requires_acknowledgment: boolean;
  }

  let banner: BannerResponse | null = null;
  let loading = true;
  let error: string | null = null;

  // Classification colors per government standards
  const classificationColors: Record<string, string> = {
    'UNCLASSIFIED': '#007a33',      // Green
    'CUI': '#502b85',               // Purple
    'CONFIDENTIAL': '#0033a0',      // Blue
    'SECRET': '#c8102e',            // Red
    'TOP SECRET': '#ff8c00',        // Orange
    'TOP SECRET//SCI': '#fce83a'    // Yellow
  };

  onMount(async () => {
    try {
      const response = await fetch('/api/auth/banner');
      if (response.ok) {
        banner = await response.json();
      }
    } catch (e) {
      error = 'Failed to load banner';
    } finally {
      loading = false;
    }
  });

  function handleAcknowledge() {
    dispatch('acknowledge');
  }

  function handleDecline() {
    window.location.href = 'about:blank';
  }

  $: bannerColor = banner?.classification
    ? classificationColors[banner.classification] || '#666'
    : '#666';
</script>

{#if !loading && banner?.enabled}
  <div class="banner-overlay">
    <div class="banner-modal">
      <!-- Classification Header -->
      <div class="classification-bar" style="background-color: {bannerColor}">
        {banner.classification}
      </div>

      <!-- Banner Content -->
      <div class="banner-content">
        <h2>{$t('auth.systemUseNotification')}</h2>
        <div class="banner-text">
          {banner.text}
        </div>

        <p class="legal-notice">
          {$t('auth.bannerAcknowledgmentNotice')}
        </p>
      </div>

      <!-- Actions -->
      <div class="banner-actions">
        <button class="btn-decline" on:click={handleDecline}>
          {$t('common.decline')}
        </button>
        <button class="btn-acknowledge" on:click={handleAcknowledge}>
          {$t('auth.iAcknowledge')}
        </button>
      </div>

      <!-- Classification Footer -->
      <div class="classification-bar" style="background-color: {bannerColor}">
        {banner.classification}
      </div>
    </div>
  </div>
{/if}

<style>
  .banner-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
  }

  .banner-modal {
    background: var(--bg-primary);
    max-width: 800px;
    max-height: 90vh;
    overflow-y: auto;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  }

  .classification-bar {
    padding: 8px 16px;
    text-align: center;
    font-weight: bold;
    color: white;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-size: 0.875rem;
  }

  .banner-content {
    padding: 24px;
  }

  .banner-content h2 {
    margin: 0 0 16px 0;
    font-size: 1.5rem;
  }

  .banner-text {
    white-space: pre-wrap;
    font-size: 0.875rem;
    line-height: 1.6;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 4px;
    max-height: 400px;
    overflow-y: auto;
  }

  .legal-notice {
    margin-top: 16px;
    font-size: 0.875rem;
    color: var(--text-secondary);
  }

  .banner-actions {
    display: flex;
    gap: 16px;
    justify-content: center;
    padding: 16px 24px;
    border-top: 1px solid var(--border-color);
  }

  .btn-acknowledge {
    background: var(--color-primary);
    color: white;
    padding: 12px 32px;
    border: none;
    border-radius: 4px;
    font-weight: 600;
    cursor: pointer;
  }

  .btn-decline {
    background: var(--bg-secondary);
    color: var(--text-primary);
    padding: 12px 32px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    cursor: pointer;
  }
</style>
```

#### 1.2 Integrate into Login Page

**File:** `/frontend/src/routes/login/+page.svelte`

Modify to show banner before login form:

```svelte
<script>
  import LoginBanner from '$components/LoginBanner.svelte';

  let bannerAcknowledged = false;

  onMount(() => {
    // Check session storage for acknowledgment
    bannerAcknowledged = sessionStorage.getItem('banner_acknowledged') === 'true';
  });

  function handleBannerAcknowledge() {
    bannerAcknowledged = true;
    sessionStorage.setItem('banner_acknowledged', 'true');
  }
</script>

{#if !bannerAcknowledged}
  <LoginBanner on:acknowledge={handleBannerAcknowledge} />
{:else}
  <!-- Existing login form -->
{/if}
```

#### 1.3 Add Translations

Add to all locale files (`en.json`, `es.json`, etc.):

```json
{
  "auth": {
    "systemUseNotification": "System Use Notification",
    "bannerAcknowledgmentNotice": "By clicking \"I Acknowledge\", you consent to the terms above and confirm that you are authorized to access this system.",
    "iAcknowledge": "I Acknowledge"
  }
}
```

---

### Phase 2: Enhanced User Management Table

**Priority: HIGH** - Required for admin functionality

#### 2.1 Update Admin API Client

**File:** `/frontend/src/lib/api/admin.ts`

Add new methods:

```typescript
export interface UserSession {
  id: string;
  user_agent: string;
  ip_address: string;
  created_at: string;
  last_activity: string;
}

export interface AccountStatusReport {
  total_users: number;
  active_users: number;
  locked_users: number;
  expired_users: number;
  mfa_enabled_users: number;
  password_expired_users: number;
}

export class AdminApi {
  // Existing methods...

  static async resetUserPassword(
    userUuid: string,
    newPassword: string,
    forceChange: boolean = true
  ): Promise<{ success: boolean }> {
    const response = await axiosInstance.post(
      `/admin/users/${userUuid}/reset-password`,
      { new_password: newPassword, force_change: forceChange }
    );
    return response.data;
  }

  static async lockAccount(
    userUuid: string,
    reason: string
  ): Promise<{ success: boolean }> {
    const response = await axiosInstance.post(
      `/admin/users/${userUuid}/lock`,
      null,
      { params: { reason } }
    );
    return response.data;
  }

  static async unlockAccount(
    userUuid: string
  ): Promise<{ success: boolean; was_locked: boolean }> {
    const response = await axiosInstance.post(
      `/admin/users/${userUuid}/unlock`
    );
    return response.data;
  }

  static async getUserSessions(
    userUuid: string
  ): Promise<{ sessions: UserSession[] }> {
    const response = await axiosInstance.get(
      `/admin/users/${userUuid}/sessions`
    );
    return response.data;
  }

  static async terminateUserSessions(
    userUuid: string
  ): Promise<{ success: boolean }> {
    const response = await axiosInstance.delete(
      `/admin/users/${userUuid}/sessions`
    );
    return response.data;
  }

  static async resetUserMFA(
    userUuid: string
  ): Promise<{ success: boolean }> {
    const response = await axiosInstance.post(
      `/admin/users/${userUuid}/mfa/reset`
    );
    return response.data;
  }

  static async getAccountStatusReport(): Promise<AccountStatusReport> {
    const response = await axiosInstance.get('/admin/reports/account-status');
    return response.data;
  }
}
```

#### 2.2 Create Account Status Dashboard

**File:** `/frontend/src/components/settings/AccountStatusDashboard.svelte`

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { AdminApi, type AccountStatusReport } from '$lib/api/admin';
  import { t } from '$lib/i18n';

  let stats: AccountStatusReport | null = null;
  let loading = true;
  let error: string | null = null;

  onMount(async () => {
    try {
      stats = await AdminApi.getAccountStatusReport();
    } catch (e) {
      error = 'Failed to load account status';
    } finally {
      loading = false;
    }
  });

  $: mfaPercentage = stats && stats.total_users > 0
    ? Math.round((stats.mfa_enabled_users / stats.total_users) * 100)
    : 0;
</script>

<div class="dashboard">
  <h3>{$t('admin.accountStatusOverview')}</h3>

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if error}
    <div class="error">{error}</div>
  {:else if stats}
    <div class="stats-grid">
      <div class="stat-card">
        <span class="stat-value">{stats.total_users}</span>
        <span class="stat-label">{$t('admin.totalUsers')}</span>
      </div>

      <div class="stat-card success">
        <span class="stat-value">{stats.active_users}</span>
        <span class="stat-label">{$t('admin.activeUsers')}</span>
      </div>

      <div class="stat-card warning">
        <span class="stat-value">{stats.locked_users}</span>
        <span class="stat-label">{$t('admin.lockedUsers')}</span>
      </div>

      <div class="stat-card">
        <span class="stat-value">{stats.expired_users}</span>
        <span class="stat-label">{$t('admin.expiredUsers')}</span>
      </div>

      <div class="stat-card info">
        <span class="stat-value">{mfaPercentage}%</span>
        <span class="stat-label">{$t('admin.mfaEnabled')}</span>
      </div>

      <div class="stat-card warning">
        <span class="stat-value">{stats.password_expired_users}</span>
        <span class="stat-label">{$t('admin.passwordExpired')}</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .dashboard {
    padding: 16px;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 16px;
    margin-top: 16px;
  }

  .stat-card {
    background: var(--bg-secondary);
    padding: 16px;
    border-radius: 8px;
    text-align: center;
    border-left: 4px solid var(--border-color);
  }

  .stat-card.success { border-left-color: var(--color-success); }
  .stat-card.warning { border-left-color: var(--color-warning); }
  .stat-card.info { border-left-color: var(--color-info); }

  .stat-value {
    display: block;
    font-size: 2rem;
    font-weight: bold;
    color: var(--text-primary);
  }

  .stat-label {
    display: block;
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin-top: 4px;
  }
</style>
```

#### 2.3 Enhance User Table with Actions

Add to existing user management table:

- Lock/Unlock account buttons
- View sessions button
- Terminate sessions button
- Reset MFA button
- Reset password button
- Account status badges (active, locked, expired)
- Last login timestamp
- MFA enabled indicator
- Auth type badge (local, ldap, keycloak, pki)

---

### Phase 3: Audit Log Viewer (FedRAMP AU-6)

**Priority: MEDIUM** - For compliance reporting

#### 3.1 Create AuditLogViewer Component

**File:** `/frontend/src/components/settings/AuditLogViewer.svelte`

Features:
- Date range filter
- Event type filter (dropdown)
- User filter
- Outcome filter (success/failure)
- Pagination
- Export to CSV/JSON
- Real-time refresh

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';

  interface AuditEvent {
    timestamp: string;
    event_type: string;
    username: string;
    outcome: string;
    source_ip: string;
    details: Record<string, any>;
  }

  let events: AuditEvent[] = [];
  let loading = true;
  let filters = {
    startDate: '',
    endDate: '',
    eventType: '',
    outcome: '',
    limit: 50,
    offset: 0
  };

  const eventTypes = [
    'AUTH_LOGIN_SUCCESS',
    'AUTH_LOGIN_FAILURE',
    'AUTH_LOGOUT',
    'AUTH_MFA_SETUP',
    'AUTH_MFA_VERIFY',
    'AUTH_PASSWORD_CHANGE',
    'AUTH_ACCOUNT_LOCKOUT',
    'ADMIN_USER_CREATE',
    'ADMIN_USER_UPDATE',
    'ADMIN_SETTINGS_CHANGE'
  ];

  async function loadEvents() {
    loading = true;
    try {
      const params = new URLSearchParams();
      if (filters.startDate) params.set('start_date', filters.startDate);
      if (filters.endDate) params.set('end_date', filters.endDate);
      if (filters.eventType) params.set('event_type', filters.eventType);
      if (filters.outcome) params.set('outcome', filters.outcome);
      params.set('limit', String(filters.limit));
      params.set('offset', String(filters.offset));

      const response = await fetch(`/api/admin/audit-logs?${params}`);
      if (response.ok) {
        const data = await response.json();
        events = data.events || [];
      }
    } finally {
      loading = false;
    }
  }

  async function exportLogs(format: 'csv' | 'json') {
    const params = new URLSearchParams();
    params.set('format', format);
    if (filters.startDate) params.set('start_date', filters.startDate);
    if (filters.endDate) params.set('end_date', filters.endDate);

    const response = await fetch(`/api/admin/audit-logs/export?${params}`);
    if (response.ok) {
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-${Date.now()}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  onMount(loadEvents);
</script>

<div class="audit-viewer">
  <div class="filters">
    <input
      type="date"
      bind:value={filters.startDate}
      placeholder="Start Date"
    />
    <input
      type="date"
      bind:value={filters.endDate}
      placeholder="End Date"
    />
    <select bind:value={filters.eventType}>
      <option value="">All Events</option>
      {#each eventTypes as type}
        <option value={type}>{type}</option>
      {/each}
    </select>
    <select bind:value={filters.outcome}>
      <option value="">All Outcomes</option>
      <option value="SUCCESS">Success</option>
      <option value="FAILURE">Failure</option>
    </select>
    <button on:click={loadEvents}>Apply</button>
    <button on:click={() => exportLogs('csv')}>Export CSV</button>
  </div>

  <table class="audit-table">
    <thead>
      <tr>
        <th>Timestamp</th>
        <th>Event</th>
        <th>User</th>
        <th>Outcome</th>
        <th>IP</th>
        <th>Details</th>
      </tr>
    </thead>
    <tbody>
      {#each events as event}
        <tr class:failure={event.outcome === 'FAILURE'}>
          <td>{new Date(event.timestamp).toLocaleString()}</td>
          <td>{event.event_type}</td>
          <td>{event.username || 'System'}</td>
          <td>
            <span class="badge {event.outcome.toLowerCase()}">
              {event.outcome}
            </span>
          </td>
          <td>{event.source_ip}</td>
          <td>
            <details>
              <summary>View</summary>
              <pre>{JSON.stringify(event.details, null, 2)}</pre>
            </details>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
```

---

### Phase 4: Certificate Info Display (PKI Users)

**Priority: LOW** - Only needed for PKI deployments

#### 4.1 Create CertificateInfo Component

**File:** `/frontend/src/components/settings/CertificateInfo.svelte`

Display for PKI-authenticated users:
- Certificate badge in header
- Subject DN
- Issuer DN
- Serial number
- Validity period (with expiration warning)
- Organization/OU
- SHA-256 fingerprint

---

### Phase 5: Super Admin Authentication Config UI

**Priority: FUTURE** - Database-backed configuration (not yet implemented in backend)

This phase requires backend implementation of:
- `auth_config` database table
- `AuthConfigService`
- API endpoints for config CRUD

Components to create when backend is ready:
- `AuthenticationSettings.svelte` - Main container with tabs
- `LDAPSettings.svelte` - LDAP/AD configuration
- `KeycloakSettings.svelte` - OIDC configuration
- `PKISettings.svelte` - Certificate configuration
- `LocalAuthSettings.svelte` - Password policy, MFA
- `SessionSettings.svelte` - Token expiration, timeouts

---

## Translation Keys Required

Add to all locale files:

```json
{
  "auth": {
    "systemUseNotification": "System Use Notification",
    "bannerAcknowledgmentNotice": "By clicking \"I Acknowledge\", you consent to the terms above and confirm that you are authorized to access this system.",
    "iAcknowledge": "I Acknowledge",
    "loginWithKeycloak": "Login with Keycloak",
    "loginWithCertificate": "Login with Certificate",
    "certificateAuthentication": "Certificate Authentication",
    "certificateExpiresSoon": "Your certificate expires in {days} days"
  },
  "admin": {
    "accountStatusOverview": "Account Status Overview",
    "totalUsers": "Total Users",
    "activeUsers": "Active Users",
    "lockedUsers": "Locked Users",
    "expiredUsers": "Expired Users",
    "mfaEnabled": "MFA Enabled",
    "passwordExpired": "Password Expired",
    "lockAccount": "Lock Account",
    "unlockAccount": "Unlock Account",
    "resetPassword": "Reset Password",
    "resetMFA": "Reset MFA",
    "viewSessions": "View Sessions",
    "terminateSessions": "Terminate All Sessions",
    "auditLogs": "Audit Logs",
    "exportCSV": "Export CSV",
    "exportJSON": "Export JSON"
  }
}
```

---

## Testing Checklist

After implementation, verify:

- [ ] Login banner displays before login form when enabled
- [ ] Banner requires acknowledgment before proceeding
- [ ] Classification colors display correctly
- [ ] Admin can view account status dashboard
- [ ] Admin can lock/unlock user accounts
- [ ] Admin can reset user passwords (via request body, not URL)
- [ ] Admin can view user sessions
- [ ] Admin can terminate user sessions
- [ ] Admin can reset user MFA
- [ ] Audit log viewer shows events with filtering
- [ ] Audit log export works (CSV/JSON)
- [ ] PKI users see certificate info (when PKI enabled)
- [ ] All components support light/dark mode
- [ ] All text uses i18n translations

---

## Files to Create/Modify Summary

### New Files
| File | Description |
|------|-------------|
| `components/LoginBanner.svelte` | FedRAMP AC-8 login banner |
| `components/settings/AccountStatusDashboard.svelte` | Admin dashboard |
| `components/settings/AuditLogViewer.svelte` | Audit log viewer |
| `components/settings/CertificateInfo.svelte` | PKI cert display |
| `lib/api/admin.ts` | Admin API client (new methods) |

### Files to Modify
| File | Changes |
|------|---------|
| `routes/login/+page.svelte` | Add banner integration |
| `components/SettingsModal.svelte` | Add new admin sections |
| `lib/i18n/locales/*.json` | Add translation keys |
| `stores/auth.ts` | Add certificate info types |

---

## Prompt for Continuation

Use this prompt to continue implementation:

```
Continue implementing the frontend authentication and admin UI components for OpenTranscribe based on the plan in docs/FRONTEND_AUTH_IMPLEMENTATION_PLAN.md

The backend security fixes are complete. Now implement the frontend components in this order:

1. LoginBanner.svelte - FedRAMP AC-8 compliance (required)
2. Admin API client updates in lib/api/admin.ts
3. AccountStatusDashboard.svelte
4. Enhanced user management with lock/unlock/session actions
5. AuditLogViewer.svelte - FedRAMP AU-6 compliance
6. CertificateInfo.svelte - For PKI users

Follow the existing Svelte patterns in the codebase. Ensure all components:
- Support light/dark mode
- Use i18n for all text
- Follow existing styling patterns
- Handle loading and error states

Start with Phase 1: Login Banner implementation.
```
