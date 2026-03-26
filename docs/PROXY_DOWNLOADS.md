# Proxy Options for Download Failures (Podtrac 403)

Some podcast hosts (notably Podtrac) block datacenter IPs. When that happens, downloads fail with HTTP 403 and processing stops.

Use one of these options:

## Option A: HTTP/HTTPS Proxy (Recommended)

Set proxy environment variables so outbound audio downloads go through a proxy with a permitted egress IP.

Add to `.env.local`:

```bash
HTTP_PROXY=http://user:pass@your-proxy-host:port
HTTPS_PROXY=http://user:pass@your-proxy-host:port
NO_PROXY=localhost,127.0.0.1
```

Then rebuild:

```bash
docker compose down
docker compose up -d --build
```

## Option B: Change Egress IP

Move the server to an IP that is allowed by the host (often a residential or less‑blocked range).

## Option C: Alternate Source URL

Some feeds provide non‑Podtrac mirrors. If possible, switch the source feed or audio URLs to avoid Podtrac entirely.

## Quick Test (Inside Container)

This verifies if Podtrac is blocking your current IP:

```bash
docker exec -i podly-pure-podcasts python - <<'PY'
import requests
url = (
"https://play.podtrac.com/npr-510318/"
"41781d6fdcd9321fcd9dc5780b50c817.mp3?"
"t=podcast&e=nx-s1-5689790&p=510318&d=793"
)
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
r = requests.get(url, headers=headers, timeout=30)
print(r.status_code)
PY
```

- `200` means OK
- `403` means the host is blocking your IP
