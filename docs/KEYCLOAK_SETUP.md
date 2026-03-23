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

**Recommended Method (using opentr.sh):**
```bash
# Start OpenTranscribe with Keycloak test container
./opentr.sh start dev --with-keycloak-test

# Or for production mode (testing before push)
./opentr.sh start prod --build --with-keycloak-test
```

**Advanced Method (manual docker compose):**
```bash
# Start Keycloak dev server (from OpenTranscribe root directory)
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up -d keycloak

# Check status
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml ps keycloak

# View logs
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml logs -f keycloak
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
     - `http://your-server-ip/login` (LAN access - replace with your IP)
     - `https://yourdomain.com/login` (production)
   - **Valid post logout redirect URIs**: `+`
   - **Web origins**: `+` (allows all origins from redirect URIs)

   > **IMPORTANT**: Redirect URIs must point to the FRONTEND login page, not the backend API endpoint.
6. Click **Save**

### Step 4: Get Client Secret

1. Navigate to **Clients** → **opentranscribe-app**
2. Go to the **Credentials** tab
3. Copy the **Client secret** value

### Step 5: Create Roles

1. Navigate to **Realm roles** in the left sidebar
2. Click **Create role**
3. Create role with name: `user`
4. Click **Save**
5. Repeat to create role: `admin`

### Step 6: Create Test User

1. Navigate to **Users** in the left sidebar
2. Click **Add user**
3. Fill in the details:
   - **Username**: `testuser`
   - **Email**: `testuser@example.com`
   - **Email verified**: ON
   - **First name**: `Test`
   - **Last name**: `User`
4. Click **Create**
5. Go to the **Credentials** tab
6. Click **Set password**
   - Enter a password
   - **Temporary**: OFF
   - Click **Save**
7. Go to the **Role mapping** tab
8. Click **Assign role**
9. Select `user` role (or `admin` for admin access)
10. Click **Assign**

### Step 7: Configure OpenTranscribe

**Recommended Method: Via Admin UI** (stores config encrypted in database — takes precedence over .env)

1. Log in to OpenTranscribe as a super admin
2. Go to **Settings** → **Authentication** → **Keycloak/OIDC**
3. Enable **Keycloak/OIDC**
4. Configure the following settings:
   - **Server URL**: `http://localhost:8180` (must be accessible from user's browser)
   - **Internal URL**: `http://transcribe-app-keycloak-1:8080` (for backend-to-Keycloak communication)
   - **Realm**: `opentranscribe`
   - **Client ID**: `opentranscribe-app`
   - **Client Secret**: Paste the secret from Step 4
   - **Callback URL**: `http://localhost:5173/login` (FRONTEND login page, NOT backend API)
   - **Admin Role**: `admin`
5. Click **Save**

> **CRITICAL - For LAN Access**: If accessing OpenTranscribe from other devices on your network (e.g., from Mac on local network), use your server's IP address:
> - **Server URL**: `http://192.168.x.x:8180` (replace with your server IP)
> - **Callback URL**: `http://192.168.x.x/login` (match your server IP)
>
> The callback URL must be accessible from the user's browser and must point to the frontend login page.

**Alternative Method: Via .env file** (initial seed fallback — only used when no database config exists)

If the Admin UI is not yet accessible (e.g., first-time setup), environment variables can seed the initial configuration:

```bash
# Keycloak/OIDC Configuration
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=http://localhost:8180           # Must be accessible from browser
KEYCLOAK_INTERNAL_URL=http://transcribe-app-keycloak-1:8080
KEYCLOAK_REALM=opentranscribe
KEYCLOAK_CLIENT_ID=opentranscribe-app
KEYCLOAK_CLIENT_SECRET=<paste-client-secret-from-step-4>
KEYCLOAK_CALLBACK_URL=http://localhost:5173/login   # Frontend login page, NOT backend API
KEYCLOAK_ADMIN_ROLE=admin
KEYCLOAK_TIMEOUT=30
```

> **Note**: Database configuration (via admin UI) takes precedence over .env variables.

### Step 8: Apply Configuration

**If configured via Admin UI**: Changes take effect immediately — no restart required.

**If configured via .env only**: Restart the backend to load the new environment variables:

```bash
./opentr.sh stop
./opentr.sh start dev
```

## Testing the Integration

1. Open http://localhost:5173 (OpenTranscribe frontend)
2. Click "Sign in with Keycloak"
3. You'll be redirected to Keycloak login
4. Enter test user credentials
5. After successful login, you'll be redirected back to OpenTranscribe

## Production Configuration

### Keycloak Server

For production, use a properly secured Keycloak instance:

```bash
# .env for production
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=https://keycloak.yourdomain.com
KEYCLOAK_REALM=opentranscribe
KEYCLOAK_CLIENT_ID=opentranscribe-app
KEYCLOAK_CLIENT_SECRET=<secure-secret>
KEYCLOAK_CALLBACK_URL=https://yourdomain.com/login  # Frontend login page
KEYCLOAK_ADMIN_ROLE=admin
```

### Security Considerations

1. **HTTPS Required**: Always use HTTPS in production
2. **Client Secret**: Stored encrypted (AES-256-GCM) in database when configured via Admin UI; never commit to git
3. **Token Validation**: OpenTranscribe validates tokens using Keycloak's JWKS endpoint (auto-discovered via OIDC metadata)
4. **Role Mapping**: Only users with the configured `KEYCLOAK_ADMIN_ROLE` get admin access
5. **MFA**: Keycloak users bypass OpenTranscribe's local MFA — configure MFA enforcement in your Keycloak realm
6. **Federated Logout**: When a user logs out of OpenTranscribe, the logout is propagated to Keycloak so the Keycloak SSO session is also terminated

### LDAP/AD Federation

To use Keycloak with your existing Active Directory:

1. Go to **User Federation** in Keycloak admin
2. Add **LDAP** provider
3. Configure your AD connection settings
4. Users can then log in to OpenTranscribe using their AD credentials via Keycloak

### Social Login

To enable Google, GitHub, etc.:

1. Go to **Identity Providers** in Keycloak admin
2. Add desired provider (e.g., Google)
3. Configure OAuth credentials from the provider
4. Users can then use social login to access OpenTranscribe

## Troubleshooting

### Common Issues

**"Keycloak authentication is not enabled"**
- If using Admin UI: verify Keycloak/OIDC is enabled in Settings → Authentication → Keycloak/OIDC
- If using .env: ensure `KEYCLOAK_ENABLED=true` and restart the backend
- Database config takes precedence — an explicit `enabled=false` in the database overrides a `true` in .env

**"Invalid or expired state parameter"**
- Try the login again (state tokens expire after 10 minutes)
- Clear browser cookies and try again

**"Failed to exchange authorization code"**
- Verify client secret is correct
- Check Keycloak logs: `docker compose logs keycloak`
- Ensure callback URL matches exactly

**Keycloak login page doesn't load or loads slowly**
- Check that `KEYCLOAK_SERVER_URL` is accessible from your browser (not just from the server)
- For LAN access, use server IP address (e.g., `http://192.168.x.x:8180`) instead of `localhost`
- Update Keycloak client redirect URIs to include your access URL
- Verify with: `curl http://your-server-ip:8180/realms/opentranscribe/.well-known/openid-configuration`

**Browser shows raw JSON instead of logging in**
- This means the callback URL is pointing to the backend API instead of frontend
- Callback URL MUST be: `http://your-domain/login` (frontend page)
- NOT: `http://your-domain/api/auth/keycloak/callback` (backend API)
- Update via Admin UI → Settings → Authentication → Keycloak → Callback URL

**User created but has wrong role**
- Verify role mapping in Keycloak user's "Role mapping" tab
- Check `KEYCLOAK_ADMIN_ROLE` matches your Keycloak role name exactly

### Debug Logging

Enable debug logging in OpenTranscribe:

```bash
# In backend container
export LOG_LEVEL=DEBUG
```

Check backend logs for authentication details:
```bash
./opentr.sh logs backend
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│                 │     │                  │     │                 │
│  OpenTranscribe │────▶│    Keycloak      │────▶│   LDAP/AD/      │
│    Frontend     │     │   (OIDC IdP)     │     │   Social Login  │
│                 │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │
        │                        │
        ▼                        ▼
┌─────────────────┐     ┌──────────────────┐
│                 │     │                  │
│  OpenTranscribe │◀────│  Token Validation│
│    Backend      │     │  (JWKS/JWT)      │
│                 │     │                  │
└─────────────────┘     └──────────────────┘
```

1. User clicks "Sign in with Keycloak"
2. Frontend requests authorization URL from backend
3. User is redirected to Keycloak login
4. After login, Keycloak redirects back with authorization code
5. Backend exchanges code for tokens
6. Backend validates tokens using Keycloak's JWKS
7. User is created/updated in OpenTranscribe database
8. OpenTranscribe issues its own JWT for session management
