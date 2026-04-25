# Self-Hosting Guide

Deploy Healthclaw on your own VPS or server. This guide covers generic VPS deployment (Hetzner, DigitalOcean, AWS, etc.).

## Prerequisites

- A VPS with 2GB+ RAM (4GB+ recommended)
- Ubuntu 22.04 LTS (or similar Linux distribution)
- Domain name (optional, but recommended for HTTPS)
- Docker and Docker Compose installed

## Step 1: Prepare Your Server

### Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add yourself to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### Install Docker Compose

```bash
sudo apt install docker-compose -y
```

## Step 2: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/vlbandara/Healthclaw.git
cd Healthclaw

# Create config
cp .env.example .env

# Edit .env with your settings (see below)
nano .env
```

### Required .env Settings

```env
# AI Configuration (local Ollama recommended for privacy)
NANOBOT_AGENTS__DEFAULTS__PROVIDER=ollama
NANOBOT_AGENTS__DEFAULTS__MODEL=gemma:7b
OLLAMA_API_BASE=http://host.docker.internal:11434

# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your-telegram-bot-token

# Multi-Tenant Family Mode
NANOBOT_MULTI_TENANT=true

# Security
HEALTH_VAULT_KEY=generate-with-python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Database
POSTGRES_PASSWORD=change-me-to-a-strong-password

# Domain (if using Caddy for HTTPS)
DOMAIN=your-domain.com
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
```

## Step 3: Install Ollama (On the Host)

For fully private deployment, install Ollama on your host:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Gemma
ollama pull gemma:7b

# Configure Ollama to accept connections from Docker
# Edit /etc/ollama/ollama.env and add:
OLLAMA_HOST=0.0.0.0
```

Restart Ollama: `sudo systemctl restart ollama`

### Allow Docker to Reach Host Ollama

On Linux, add this to your docker-compose override or run containers with:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Or set `OLLAMA_API_BASE=http://172.17.0.1:11434` (check your Docker bridge IP with `ip addr show docker0`).

## Step 4: Configure Firewall

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (for Caddy)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

## Step 5: Start the Stack

```bash
# Start with Docker Compose
docker compose --env-file .env up -d --build postgres redis orchestrator worker caddy

# Check logs
docker compose logs -f
```

## Step 6: Verify

1. Visit `http://your-server-ip` or `https://your-domain.com`
2. Check the orchestrator health: `curl http://localhost:8080/healthz`
3. Send a message to your Telegram bot

## Step 7: HTTPS with Caddy (Recommended)

Caddy automatically handles HTTPS. Ensure your domain points to your server's IP, then:

```bash
# Update .env with your domain
DOMAIN=Healthclaw.yourdomain.com

# Restart Caddy
docker compose --env-file .env up -d caddy
```

Caddy will automatically obtain and renew Let's Encrypt certificates.

## Optional: Set Up Ollama as a System Service

For more reliable Ollama hosting:

```bash
# Create systemd service
sudo nano /etc/systemd/system/ollama.service
```

Contents:
```ini
[Unit]
Description=Ollama Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

## Security Hardening

### For Production

1. **Use strong passwords:**
   ```env
   POSTGRES_PASSWORD=your-very-long-random-password
   HEALTH_VAULT_KEY=generated-above
   ```

2. **Enable firewall:**
   ```bash
   sudo ufw default deny incoming
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```

3. **Regular updates:**
   ```bash
   # Update Docker images
   docker compose pull
   docker compose up -d --build

   # Update Ollama models
   ollama pull gemma:7b
   ```

4. **Monitor logs:**
   ```bash
   docker compose logs --tail=100 -f
   ```

5. **Back up data:**
   ```bash
   # Back up nanobot state
   tar -czf nanobot-backup-$(date +%Y%m%d).tar.gz ~/.nanobot
   ```

### Fail2ban

Install fail2ban to protect against brute force:

```bash
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

## Troubleshooting

### Database connection issues

```bash
# Check postgres is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# Reset database (careful — loses data)
docker compose down -v
docker compose up -d
```

### Ollama not reachable from Docker

```bash
# Check Ollama is running
curl http://localhost:11434

# Check host IP in docker network
ip addr show docker0
# Likely 172.17.0.1

# Update .env
OLLAMA_API_BASE=http://172.17.0.1:11434
```

### Telegram bot not responding

```bash
# Check TELEGRAM_BOT_TOKEN is correct
# Restart worker
docker compose restart worker

# Check logs
docker compose logs worker | grep -i telegram
```

## Updating

```bash
git pull
docker compose --env-file .env up -d --build
```

## Related Documentation

- [Getting Started](GETTING_STARTED.md) — Initial setup guide
- [Architecture](ARCHITECTURE.md) — System design
- [Security](SECURITY.md) — Production security checklist
- [FAQ](FAQ.md) — Common questions