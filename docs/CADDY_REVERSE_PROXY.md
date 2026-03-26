# Caddy Reverse Proxy Configuration

When running Podly behind Caddy (especially over WireGuard), you must configure Caddy to forward the correct headers so the Flask app generates proper HTTPS URLs.

## Required Headers

Caddy must set these headers when proxying to the upstream Podly container:

- `X-Forwarded-Proto`: The original scheme (http or https)
- `X-Forwarded-Host`: The original host header from the client
- `X-Forwarded-For`: The original client IP

## Example Caddyfile

```caddyfile
your-domain.com {
    reverse_proxy podly-server:5001 {
        # Required for correct URL generation in RSS feeds
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

### Over WireGuard

If Caddy is on a different server connected via WireGuard:

```caddyfile
your-domain.com {
    reverse_proxy 10.0.0.2:5001 {
        # Replace 10.0.0.2 with the WireGuard IP of your Podly server
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

## Why This Matters

The Flask app uses `werkzeug.middleware.proxy_fix.ProxyFix` to trust these headers. Without them:

- RSS feed `<link>` and `<enclosure>` URLs will use `http://` instead of `https://`
- URLs may use the internal hostname/port instead of the public domain
- Podcast apps will fail to download episodes or trigger processing

## Verification

After configuring Caddy, verify the RSS feed uses correct URLs:

```bash
curl -s "https://your-domain.com/feed/combined?feed_token=...&feed_secret=..." | grep -o 'url="[^"]*"' | head -3
```

Expected output should show `https://your-domain.com/...` URLs.

## Flask ProxyFix Configuration

The app is configured with:

```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)
```

This trusts one level of proxy headers. If you have multiple proxies, adjust the numbers accordingly.
