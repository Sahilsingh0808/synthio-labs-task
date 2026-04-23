# Deploying VoiceSlide to `synthio-labs.jeenius.tech`

End-to-end runbook for a fresh Ubuntu / Debian server (22.04 LTS or later).

## Topology

```
                 synthio-labs.jeenius.tech:443
                             │
                             ▼
              ┌──────────────────────────────┐
              │   host nginx (TLS / HTTP/2)  │
              │   certs via Let's Encrypt    │
              └──────────────┬───────────────┘
                             │ http://127.0.0.1:5173
                             ▼
              ┌──────────────────────────────┐
              │   docker compose stack       │
              │  ┌────────────────────────┐  │
              │  │ frontend (nginx+SPA)   │──┼── /api/*, /ws/* ─▶ backend:9001
              │  │   basic-auth (optional)│  │
              │  └────────────────────────┘  │
              └──────────────────────────────┘
```

Host nginx terminates TLS and forwards plain HTTP to the docker-compose frontend on `127.0.0.1:5173`. The compose frontend's internal nginx serves the SPA and reverse-proxies `/api/*` and `/ws/*` to the backend container over the docker bridge network.

---

## 1. Server prerequisites

```bash
# Docker Engine + Docker Compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"    # log out / back in afterwards

# Host nginx + certbot
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx ufw
```

## 2. DNS

Point an `A` record for `synthio-labs.jeenius.tech` at the server's public IP. Confirm it resolves before going further:

```bash
dig +short synthio-labs.jeenius.tech
```

## 3. Firewall

Only `80` and `443` should be exposed publicly. Backend `9001` and frontend `5173` are host-loopback-only after the next step.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 4. Clone + configure

```bash
sudo mkdir -p /srv && sudo chown "$USER":"$USER" /srv
cd /srv
git clone <your-repo-url> voiceslide
cd voiceslide

# Backend credentials
cp backend/.env.example backend/.env
# …then edit backend/.env and fill in the Azure / OpenAI keys.

# Compose-level overrides (gate the site, bind to loopback only, etc.)
cp .env.deploy.example .env
# …then edit .env, e.g.:
#   BASIC_AUTH_USERNAME=alice
#   BASIC_AUTH_PASSWORD=super-secret
#   FRONTEND_PORT=5173
```

### Bind compose ports to loopback (production hardening)

The default `docker-compose.yml` binds `5173` and `9001` to `0.0.0.0` — fine for local dev, too open for a public server. Set `BIND_HOST` in the root `.env`:

```bash
echo 'BIND_HOST=127.0.0.1' >> .env
```

After `./deploy.sh`, `docker compose ps` should show the ports bound to `127.0.0.1` only. With the host firewall + loopback binding, the only public entry point is the host nginx on `443`.

## 5. First deploy (HTTP only, to issue certs)

Install a stub host nginx vhost that only handles the ACME HTTP challenge so certbot can issue the cert:

```bash
sudo mkdir -p /var/www/certbot
sudo tee /etc/nginx/sites-available/synthio-labs.jeenius.tech >/dev/null <<'NGINX'
server {
    listen 80;
    server_name synthio-labs.jeenius.tech;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 "OK"; }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/synthio-labs.jeenius.tech \
           /etc/nginx/sites-enabled/synthio-labs.jeenius.tech
sudo nginx -t && sudo systemctl reload nginx
```

Issue the cert (webroot mode — no interruption to nginx):

```bash
sudo certbot certonly --webroot -w /var/www/certbot \
  -d synthio-labs.jeenius.tech \
  --agree-tos -m ops@jeenius.tech --non-interactive
```

Certbot installs a systemd timer (`certbot.timer`) that handles renewal automatically.

## 6. Install the full host vhost

```bash
sudo cp deploy/nginx/synthio-labs.jeenius.tech.conf \
        /etc/nginx/sites-available/synthio-labs.jeenius.tech
sudo nginx -t && sudo systemctl reload nginx
```

## 7. Start the compose stack

```bash
./deploy.sh
```

The script preflights Docker, validates the env files, builds both images, brings up the stack, and blocks until both healthchecks pass. Re-run any time:

```bash
./deploy.sh --pull       # git pull then deploy
./deploy.sh --fresh      # no-cache rebuild (use after requirements changes)
./deploy.sh --logs       # tail logs after deploy
./deploy.sh --stop       # bring the stack down
./deploy.sh --status     # docker compose ps
```

Site should be live at **https://synthio-labs.jeenius.tech**.

## 8. Verify

```bash
# Health — works with or without basic auth
curl -i https://synthio-labs.jeenius.tech/healthz

# SPA — 401 if BASIC_AUTH is set, 200 otherwise
curl -I https://synthio-labs.jeenius.tech/

# With auth
curl -u alice:super-secret https://synthio-labs.jeenius.tech/
```

## 9. Operational notes

**Updates**
```bash
cd /srv/voiceslide
./deploy.sh --pull
```

**Logs**
```bash
docker compose logs -f backend        # realtime relay / Azure calls
docker compose logs -f frontend       # nginx access/error
sudo tail -f /var/log/nginx/voiceslide.error.log   # host TLS / proxy
```

**Rotate basic auth credentials**
Edit the root `.env`, then:
```bash
docker compose restart frontend       # entrypoint regenerates .htpasswd
```

**Cert renewal**
Automatic via `certbot.timer`. Test renewal without actually rotating:
```bash
sudo certbot renew --dry-run
```

**Rolling back**
```bash
git reset --hard <good-commit>
./deploy.sh --fresh
```

## Common pitfalls

- **WS drops after 60s** — host nginx `proxy_read_timeout` too short. The shipped vhost uses 3600s; if you edited it, double-check.
- **502 from host nginx** — compose stack not healthy. `./deploy.sh --status` + `docker compose logs`.
- **Cert renewal fails** — ensure the `/.well-known/acme-challenge/` location block is still reachable over plain HTTP (port 80). The shipped vhost preserves it.
- **Basic auth prompts re-appear every page** — usually caused by navigating between `http://` and `https://` origins. HSTS (enabled in the vhost) prevents this from happening after the first successful HTTPS visit.
- **Audio cutting out** — check the backend container `/healthz` through the compose frontend: `curl -u user:pass https://synthio-labs.jeenius.tech/healthz`. If that fails, the backend dropped and the relay is unreachable.
