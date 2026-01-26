# Keycloak OIDC Authentication Setup

This guide covers setting up Keycloak for OpenID Connect (OIDC) authentication with OpenTranscribe.

## Overview

Keycloak provides enterprise-grade identity and access management. OpenTranscribe integrates with Keycloak via OIDC, allowing:
- Single Sign-On (SSO) with your organization's identity provider
- Role-based access control synchronized from Keycloak
- Support for LDAP/AD federation through Keycloak
- Social login providers (Google, GitHub, etc.) via Keycloak

## Development Environment Setup

### Step 1: Start Keycloak

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
     - `http://localhost:5174/api/auth/keycloak/callback` (dev)
     - `https://yourdomain.com/api/auth/keycloak/callback` (prod)
   - **Valid post logout redirect URIs**: `+`
   - **Web origins**: `+` (allows all origins from redirect URIs)
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

Add to your `.env` file:

```bash
# Keycloak/OIDC Configuration
KEYCLOAK_ENABLED=true
KEYCLOAK_SERVER_URL=http://localhost:8180
KEYCLOAK_REALM=opentranscribe
KEYCLOAK_CLIENT_ID=opentranscribe-app
KEYCLOAK_CLIENT_SECRET=<paste-client-secret-from-step-4>
KEYCLOAK_CALLBACK_URL=http://localhost:5174/api/auth/keycloak/callback
KEYCLOAK_ADMIN_ROLE=admin
KEYCLOAK_TIMEOUT=30
```

### Step 8: Restart OpenTranscribe

```bash
# Restart backend to load new configuration
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
KEYCLOAK_CALLBACK_URL=https://yourdomain.com/api/auth/keycloak/callback
KEYCLOAK_ADMIN_ROLE=admin
```

### Security Considerations

1. **HTTPS Required**: Always use HTTPS in production
2. **Client Secret**: Keep the client secret secure, never commit to git
3. **Token Validation**: OpenTranscribe validates tokens using Keycloak's JWKS endpoint
4. **Role Mapping**: Only users with the configured `KEYCLOAK_ADMIN_ROLE` get admin access

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
- Ensure `KEYCLOAK_ENABLED=true` in `.env`
- Restart the backend after configuration changes

**"Invalid or expired state parameter"**
- Try the login again (state tokens expire after 10 minutes)
- Clear browser cookies and try again

**"Failed to exchange authorization code"**
- Verify client secret is correct
- Check Keycloak logs: `docker compose logs keycloak`
- Ensure callback URL matches exactly

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
