# Contributor Guide

### Quick Start (Docker - recommended for local setup)

1. Make the script executable and run:

```bash
chmod +x run_podly_docker.sh
./run_podly_docker.sh --build
./run_podly_docker.sh # foreground with logs 
./run_podly_docker.sh -d # or detached
```

This automatically detects NVIDIA GPUs and uses them if available.

After the server starts:

- Open `http://localhost:5001` in your browser
- Configure settings at `http://localhost:5001/config`
- Add podcast feeds and start processing

## Usage

Once the server is running:

1. Open `http://localhost:5001`
2. Configure settings in the Config page at `http://localhost:5001/config`
3. Add podcast RSS feeds through the web interface
4. Open your podcast app and subscribe to the Podly endpoint (e.g., `http://localhost:5001/feed/1`)
5. Select an episode and download

## Transcription Options

Podly supports multiple options for audio transcription:

1. **Local Whisper (Default)**
   - Slower but self-contained
2. **OpenAI Hosted Whisper**
   - Fast and accurate; billed per-feed via Stripe
3. **Groq Hosted Whisper**
   - Fast and cost-effective

Select your preferred method in the Config page (`/config`).

## Remote Setup

For a TLS reverse proxy that sends `X-Forwarded-Proto`, set `PODLY_TRUSTED_PROXY`
to the immediate proxy peer's exact IPv4 address as seen by Waitress. Podly then
accepts `X-Forwarded-Proto` from that peer so generated feed enclosure URLs use
`https`. Only one peer IP is supported; wildcards, CIDRs, address lists,
hostnames, and IPv6 addresses are rejected at startup. When a configured setting
no longer matches the proxy, Waitress logs the untrusted proxy headers it drops.

- The proxy must overwrite `X-Forwarded-Proto` with a single value. A
  comma-separated chain from a trusted peer is rejected with `400 Bad Request`.
- Only trust an address that ordinary clients cannot connect from. With Docker
  published ports, every client may appear as the bridge gateway (for example
  `172.20.0.1`); trusting that address lets any client choose the scheme. Put
  the proxy on a shared Docker network instead and pin its container IP.
- Forwarded client addresses and hosts are not trusted; authentication rate
  limits use the socket peer address.

Independently of this setting, Podly also infers the scheme from other request headers
(such as `X-Forwarded-Ssl`, `X-Forwarded-Scheme`, `CF-Visitor` and
`Strict-Transport-Security`) and builds URLs from the `Host` header. These
headers are client-controlled and only affect the URLs in that client's response.

### Reverse Proxy Examples

**Nginx:**

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5001;  # PODLY_TRUSTED_PROXY=127.0.0.1
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

**Traefik (docker-compose.yml):**

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.podly.rule=Host(`your-domain.com`)"
  - "traefik.http.routers.podly.tls.certresolver=letsencrypt"
  - "traefik.http.services.podly.loadbalancer.server.port=5001"
```

> **Note**: For proxies that only send `X-Forwarded-Proto` (Nginx and Traefik defaults), set `PODLY_TRUSTED_PROXY` to the proxy's IP or feed URLs stay `http`.

### Built-in Authentication

Podly ships with built-in authentication so you can secure feeds without relying on a reverse proxy.

- Set `REQUIRE_AUTH=true` to enable protection. By default it is `false`, preserving existing behaviour.
- When auth is enabled, Podly fails fast on startup unless `PODLY_ADMIN_PASSWORD` is supplied and meets the strength policy (≥12 characters with upper, lower, digit, symbol). Override the initial username with `PODLY_ADMIN_USERNAME` (default `podly_admin`).
- Provide a long, random `PODLY_SECRET_KEY` so Flask sessions remain valid across restarts. If you omit it, the app generates a new key on each boot and all users are signed out.
- On first boot with an empty database, Podly seeds an admin user using the supplied credentials. **If you are enabling auth on an existing install, start from a fresh data volume.**
- After signing in, open the Config page to rotate your password and manage additional users. When you change the admin password, update the corresponding environment variable in your deployment platform so restarts continue to succeed.
- Use the "Copy protected feed" button to generate feed-specific access tokens that are embedded in subscription URLs so podcast clients can authenticate without your primary password. Rate limiting is still applied to repeated authentication failures.

## Ubuntu Service

Add a service file to /etc/systemd/system/podly.service

```
[Unit]
Description=Podly Podcast Service
After=network.target

[Service]
User=yourusername
Group=yourusername
WorkingDirectory=/path/to/your/app
ExecStart=/usr/bin/env uv run python src/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

enable the service

```
sudo systemctl daemon-reload
sudo systemctl enable podly.service
```

## Database Update

The database auto-migrates on launch.

To add a migration after data model change:

```bash
uv run flask --app ./src/main.py db migrate -m "[change description]"
```

On next launch, the database updates automatically.

## Releases and Commit Messages

This repo uses `semantic-release` to automate versioning and GitHub releases. It relies on
Conventional Commits to determine the next version.

For pull requests, include **at least one** commit that follows the Conventional Commit format:

- `feat: add new episode filter`
- `fix(api): handle empty feed`
- `chore: update dependencies`

If no Conventional Commit is present, the release pipeline will have nothing to publish.

## Docker Support

Podly can be run in Docker with support for both NVIDIA GPU and non-NVIDIA environments.

### Docker Options

```bash
./run_podly_docker.sh --dev          # rebuild containers for local changes
./run_podly_docker.sh --production   # use published images
./run_podly_docker.sh --lite         # smaller image without local Whisper
./run_podly_docker.sh --cpu          # force CPU mode
./run_podly_docker.sh --gpu          # force GPU mode
./run_podly_docker.sh --build        # build only
./run_podly_docker.sh --test-build   # test build
./run_podly_docker.sh -d             # detached
```

### Development vs Production Modes

**Development Mode** (default):

- Uses local Docker builds
- Requires rebuilding after code changes: `./run_podly_docker.sh --dev`
- Mounts essential directories (config, input/output, database) and live code for development
- Good for: development, testing, customization

**Production Mode**:

- Uses pre-built images from GitHub Container Registry
- No building required - images are pulled automatically
- Same volume mounts as development
- Good for: deployment, quick setup, consistent environments

```bash
# Start with existing local container
./run_podly_docker.sh

# Rebuild and start after making code changes
./run_podly_docker.sh --dev

# Use published images (no local building required)
./run_podly_docker.sh --production
```

### Docker Environment Configuration

**Environment Variables**:

- `PUID`/`PGID`: User/group IDs for file permissions (automatically set by run script)
- `CUDA_VISIBLE_DEVICES`: GPU device selection for CUDA acceleration
- `CORS_ORIGINS`: Backend CORS configuration (defaults to accept requests from any origin)

**Env Var Precedence for Config Settings**:

Environment variables for Podly config settings (e.g. `LLM_MODEL`, `WHISPER_TYPE`, `GROQ_API_KEY`) always take precedence over values stored in the database or set through the web UI. This follows the [12-factor app](https://12factor.net/config) principle:

- At runtime, env vars are overlaid on top of database values — the database is never mutated by env vars.
- The API strips env-controlled fields from incoming config updates to prevent the UI from overwriting operator intent.
- In the web UI, env-controlled fields appear as read-only with a visual indicator.
- To give control back to the UI, simply remove the env var and restart the container.

See `.env.local.example` for all available environment variables.

## FAQ

Q: What does "whitelisted" mean in the UI?

A: It means an episode is eligible for download and ad removal. By default, new episodes are automatically whitelisted (`automatically_whitelist_new_episodes`), and only a limited number of old episodes are auto-whitelisted (`number_of_episodes_to_whitelist_from_archive_of_new_feed`). Adjust these settings in the Config page (/config).

Q: How can I enable whisper GPU acceleration?

A: There are two ways to enable GPU acceleration:

1. **Using Docker**:

   - Use the provided Docker setup with `run_podly_docker.sh` which automatically detects and uses NVIDIA GPUs if available
   - You can force GPU mode with `./run_podly_docker.sh --gpu` or force CPU mode with `./run_podly_docker.sh --cpu`

2. **In a local environment**:
   - Install the CUDA version of PyTorch to your virtual environment:
   ```bash
   pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

## Contributing

We welcome contributions to Podly! Here's how you can help:

### Development Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/podly.git
   ```
3. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. Before opening a pull request, run the [automated smoke tests](automated_smoke_testing.md) against a fresh instance of your branch.
5. Create a pull request with a target branch of Preview

#### Application Ports

Both local and Docker deployments provide a consistent experience:

- **Application**: Runs on port 5001 (configurable via web UI at `/config`)
  - Serves both the web interface and API endpoints
  - Frontend is built as static assets and served by the backend
- **Development**: `run_podly_docker.sh` serves everything on port 5001
  - Local script builds frontend to static assets (like Docker)
  - Restart `./run_podly_docker.sh` after frontend changes to rebuild assets

#### Development Modes

Both scripts provide equivalent core functionality with some unique features:

**Common Options (work in both scripts)**:

- `-b/--background` or `-d/--detach`: Run in background mode
- `-h/--help`: Show help information

**Local Development**

**Docker Development** (`./run_podly_docker.sh`):

- **Development mode**: `./run_podly_docker.sh --dev` - rebuilds containers with code changes
- **Production mode**: `./run_podly_docker.sh --production` - uses pre-built images
- **Docker-specific options**: `--build`, `--test-build`, `--gpu`, `--cpu`, `--cuda=VERSION`, `--rocm=VERSION`, `--branch=BRANCH`

**Functional Equivalence**:
Both scripts provide the same core user experience:

- Application runs on port 5001 (configurable)
- Frontend served as static assets by Flask backend
- Same web interface and API endpoints
- Compatible background/detached modes

### Running Tests

Before submitting a pull request, you can run the same tests that run in CI:

To prep your local uv environment to run this script, you will need to first run:

```bash
uv sync --extra dev
```

Then, to run the checks,

```bash
scripts/ci.sh
```

This will run all the necessary checks including:

- Code formatting and linting with ruff
- Type checking with ty
- Unit tests

### Pull Request Process

1. Ensure all tests pass locally
2. Update the documentation if needed
3. Create a Pull Request with a clear description of the changes
4. Link any related issues

### Code Style

- We use ruff for code formatting
- Type hints are required for all new code
- Follow existing patterns in the codebase
