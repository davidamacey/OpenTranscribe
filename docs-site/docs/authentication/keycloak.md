---
sidebar_label: Keycloak / OIDC
sidebar_position: 3
---

# Keycloak OIDC Authentication Setup

This guide covers setting up Keycloak for OpenID Connect (OIDC) authentication with OpenTranscribe.

## Overview

Keycloak provides enterprise-grade identity and access management. OpenTranscribe integrates with Keycloak via OIDC, allowing:
- Single Sign-On (SSO) with your organization's identity provider
- Role-based access control synchronized from Keycloak
- Support for LDAP/AD federation through Keycloak
- Social login providers (Google, GitHub, etc.) via Keycloak
- Full OIDC discovery support (endpoints auto-populated from provider metadata)
- Federated logout — when a user's OpenTranscribe session ends, the logout is propagated to Keycloak

> **v0.4.0 Change**: Keycloak configuration is now managed via the Super Admin UI (Settings → Authentication → Keycloak/OIDC). Settings are stored encrypted (AES-256-GCM) in the database. Environment variables continue to work as an initial fallback but database config takes precedence.
>
> **MFA Note**: Keycloak users bypass local MFA — their identity provider is responsible for multi-factor authentication. Configure MFA enforcement directly in Keycloak.

## Development Environment Setup

### Step 1: Start Keycloak

```bash
# Start OpenTranscribe with Keycloak test container
./opentr.sh start dev --with-keycloak-test
```

Access the admin console at http://localhost:8180

Default credentials: `admin` / `admin`

### Step 2: Create Realm

1. Log in to Keycloak admin console
2. Click the dropdown at the top-left (shows "master")
3. Click "Create Realm"
4. Realm name: `opentranscribe`
5. Click "Create"

### Step 3: Create Client

1. Navigate to **Clients** in the left sidebar
2. Click **Create client**
3. Configure the client:
   - **Client type**: OpenID Connect
   - **Client ID**: `opentranscribe-app`
   - Click **Next**
4. Capability config:
   - **Client authentication**: ON (confidential client)
   - **Authorization**: OFF
   - Click **Next**
5. Login settings:
   - **Valid redirect URIs**:
     - `http://localhost:5173/login` (local dev)
     - `http://your-server-ip/login` (LAN access)
     - `https://yourdomain.com/login` (production)
   - **Valid post logout redirect URIs**: `+`
   - **Web origins**: `+`

   > **IMPORTANT**: Redirect URIs must point to the FRONTEND login page, not the backend API endpoint.

6. Click **Save**

### Step 4: Get Client Secret

1. Navigate to **Clients** → **opentranscribe-app**
2. Go to the **Credentials** tab
3. Copy the **Client secret** value

### Step 5: Create Roles

1. Navigate to **Realm roles** in the left sidebar
2. Create role: `user`
3. Create role: `admin`

### Step 6: Create Test User

1. Navigate to **Users** → **Add user**
2. Fill in username, email, first/last name; set **Email verified**: ON
3. Go to **Credentials** tab → **Set password** (Temporary: OFF)
4. Go to **Role mapping** tab → **Assign role** → select `user` or `admin`

### Step 7: Configure OpenTranscribe

**Recommended Method: Via Admin UI** (stores config encrypted in database)

1. Log in to OpenTranscribe as a super admin
2. Go to **Settings** → **Authentication** → **Keycloak/OIDC**
3. Enable **Keycloak/OIDC** and configure:
   - **Server URL**: `http://localhost:8180` (must be accessible from user's browser)
   - **Internal URL**: `http://transcribe-app-keycloak-1:8080` (backend-to-Keycloak)
   - **Realm**: `opentranscribe`
   - **Client ID**: `opentranscribe-app`
   - **Client Secret**: Paste the secret from Step 4
   - **Callback URL**: `http://localhost:5173/login` (FRONTEND login page, NOT backend API)
   - **Admin Role**: `admin`
4. Click **Save**

> **For LAN Access**: Use your server's IP address for both Server URL and Callback URL:
> - **Server URL**: `http://192.168.x.x:8180`
> - **Callback URL**: `http://192.168.x.x/login`

**Alternative Method: Via .env file** (initial seed fallback)

```bash
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=http://localhost:8180
KEYCLOAK_INTERNAL_URL=http://transcribe-app-keycloak-1:8080
KEYCLOAK_REALM=opentranscribe
KEYCLOAK_CLIENT_ID=opentranscribe-app
KEYCLOAK_CLIENT_SECRET=<paste-client-secret>
KEYCLOAK_CALLBACK_URL=http://localhost:5173/login
KEYCLOAK_ADMIN_ROLE=admin
KEYCLOAK_TIMEOUT=30
```

## Testing the Integration

1. Open http://localhost:5173 (OpenTranscribe frontend)
2. Click "Sign in with Keycloak"
3. You'll be redirected to Keycloak login
4. Enter test user credentials
5. After successful login, you'll be redirected back to OpenTranscribe

## Production Configuration

```bash
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=https://keycloak.yourdomain.com
KEYCLOAK_REALM=opentranscribe
KEYCLOAK_CLIENT_ID=opentranscribe-app
KEYCLOAK_CLIENT_SECRET=<secure-secret>
KEYCLOAK_CALLBACK_URL=https://yourdomain.com/login
KEYCLOAK_ADMIN_ROLE=admin
```

### Security Considerations

1. **HTTPS Required**: Always use HTTPS in production
2. **Client Secret**: Stored encrypted (AES-256-GCM) in database when configured via Admin UI
3. **Token Validation**: Uses Keycloak's JWKS endpoint (auto-discovered via OIDC metadata)
4. **MFA**: Keycloak users bypass OpenTranscribe's local MFA — configure MFA in your Keycloak realm
5. **Federated Logout**: Logout is propagated to Keycloak to terminate the SSO session

### LDAP/AD Federation

To use Keycloak with your existing Active Directory:

1. Go to **User Federation** in Keycloak admin
2. Add **LDAP** provider
3. Configure your AD connection settings
4. Users can then log in to OpenTranscribe using their AD credentials via Keycloak

## Troubleshooting

**"Keycloak authentication is not enabled"**
- Verify Keycloak/OIDC is enabled in Settings → Authentication → Keycloak/OIDC
- Database config takes precedence — an explicit `enabled=false` overrides `true` in .env

**"Invalid or expired state parameter"**
- Try the login again (state tokens expire after 10 minutes)
- Clear browser cookies and try again

**"Failed to exchange authorization code"**
- Verify client secret is correct
- Check Keycloak logs: `docker compose logs keycloak`
- Ensure callback URL matches exactly

**Keycloak login page doesn't load**
- Check that `KEYCLOAK_SERVER_URL` is accessible from your browser (not just the server)
- For LAN access, use server IP address instead of `localhost`
- Verify: `curl http://your-server-ip:8180/realms/opentranscribe/.well-known/openid-configuration`

**Browser shows raw JSON instead of logging in**
- Callback URL is pointing to the backend API instead of frontend
- Callback URL MUST be: `http://your-domain/login` (frontend page)
- NOT: `http://your-domain/api/auth/keycloak/callback` (backend API)

## Architecture

```
 OpenTranscribe  ────▶  Keycloak (OIDC IdP)  ────▶  LDAP/AD / Social Login
    Frontend                    │
        │                       │
        ▼                       ▼
 OpenTranscribe  ◀────  Token Validation (JWKS/JWT)
    Backend
```

1. User clicks "Sign in with Keycloak"
2. Frontend requests authorization URL from backend
3. User is redirected to Keycloak login
4. After login, Keycloak redirects back with authorization code
5. Backend exchanges code for tokens
6. Backend validates tokens using Keycloak's JWKS
7. User is created/updated in OpenTranscribe database
8. OpenTranscribe issues its own JWT for session management
