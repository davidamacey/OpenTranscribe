---
sidebar_position: 3
---

# NGINX & HTTPS Setup

Set up NGINX reverse proxy with SSL/TLS for secure HTTPS access. This enables browser microphone recording from devices other than localhost.

## Why HTTPS?

Modern browsers enforce strict security policies. The `getUserMedia()` API (used for microphone access) only works in:

1. `localhost` connections (development exception)
2. HTTPS connections (production requirement)

If you access OpenTranscribe over HTTP from another device or IP address, browsers will block microphone recording.

## Quick Setup (Homelab/Local Network)

### Step 1: Run SSL Setup

```bash
cd opentranscribe
./opentranscribe.sh setup-ssl
```

This interactive command will:
- Prompt for hostname (e.g., `opentranscribe.local`)
- Generate self-signed SSL certificates
- Update your `.env` configuration
- Show next steps

### Step 2: Configure DNS

**Option A: Router DNS (Recommended)**
Add a DNS entry in your router pointing your hostname to your server's IP address.

**Option B: Local Hosts File**
On each client device, add to:
- Linux/Mac: `/etc/hosts`
- Windows: `C:\Windows\System32\drivers\etc\hosts`

```
192.168.1.100  opentranscribe.local
```

### Step 3: Restart Services

```bash
./opentranscribe.sh restart
```

### Step 4: Trust the Certificate

Import `nginx/ssl/server.crt` on each client device:

#### Windows
1. Double-click the `.crt` file
2. Click **Install Certificate** → **Local Machine**
3. Select **Trusted Root Certification Authorities**
4. Complete wizard and restart browser

#### macOS
1. Double-click to open in Keychain Access
2. Find the certificate, double-click it
3. Expand **Trust** → Set to **Always Trust**
4. Close and enter password

#### Linux (Chrome)
1. Go to `chrome://settings/certificates`
2. Click **Authorities** → **Import**
3. Select `server.crt` and trust for websites

#### iOS
1. Email or AirDrop the `.crt` file
2. Open → Install profile
3. Settings → General → About → Certificate Trust Settings
4. Enable trust for OpenTranscribe

#### Android
1. Copy `server.crt` to device
2. Settings → Security → Install certificate
3. Select CA certificate

### Step 5: Access via HTTPS

```
https://opentranscribe.local
```

All services are available through the reverse proxy:
- Frontend: `https://your-hostname`
- API: `https://your-hostname/api`
- Flower: `https://your-hostname/flower/`
- MinIO Console: `https://your-hostname/minio/`

## Production Setup (Let's Encrypt)

For production with a public domain, use Let's Encrypt for trusted certificates.

### Prerequisites

- Domain name pointing to your server
- Ports 80 and 443 accessible from internet

### Generate Certificates

```bash
# Install certbot
sudo apt install certbot  # Ubuntu/Debian

# Stop services
./opentranscribe.sh stop

# Generate certificates
sudo certbot certonly --standalone -d transcribe.example.com

# Link certificates
mkdir -p nginx/ssl
sudo ln -sf /etc/letsencrypt/live/transcribe.example.com/fullchain.pem nginx/ssl/server.crt
sudo ln -sf /etc/letsencrypt/live/transcribe.example.com/privkey.pem nginx/ssl/server.key
```

### Configure Environment

Edit `.env`:
```bash
NGINX_SERVER_NAME=transcribe.example.com
NGINX_CERT_FILE=/etc/letsencrypt/live/transcribe.example.com/fullchain.pem
NGINX_CERT_KEY=/etc/letsencrypt/live/transcribe.example.com/privkey.pem
```

### Auto-Renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Add cron job
echo "0 0 1 * * certbot renew --quiet && docker compose restart nginx" | sudo tee -a /etc/crontab
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NGINX_SERVER_NAME` | (none) | Hostname for NGINX. Setting this enables HTTPS. |
| `NGINX_HTTP_PORT` | `80` | HTTP port (redirects to HTTPS) |
| `NGINX_HTTPS_PORT` | `443` | HTTPS port |
| `NGINX_CERT_FILE` | `./nginx/ssl/server.crt` | Path to SSL certificate |
| `NGINX_CERT_KEY` | `./nginx/ssl/server.key` | Path to SSL private key |

## Troubleshooting

### SSL Certificates Not Found

```bash
# Generate certificates
./scripts/generate-ssl-cert.sh opentranscribe.local --auto-ip
```

### Browser Shows Security Warning

Expected with self-signed certificates. Options:
1. Trust the certificate on each device (recommended for homelab)
2. Use Let's Encrypt for publicly trusted certificates

### Connection Refused on Port 443

```bash
# Check NGINX container
docker compose ps nginx
docker compose logs nginx
```

### Microphone Still Not Working

1. Verify using HTTPS (not HTTP)
2. Check browser console for errors
3. Ensure certificate is trusted
4. Try incognito/private window

## Advanced: Custom NGINX Configuration

Edit `nginx/site.conf.template` for customizations:

- HTTP Basic Auth for Flower/MinIO
- Custom headers
- Rate limiting
- Larger file upload limits

Restart after changes:
```bash
docker compose restart nginx
```
