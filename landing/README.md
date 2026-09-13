# SpoolUp Landing Site

Static marketing site for SpoolUp — the 3D printer timelapse publishing platform. Pure HTML/CSS/JS, no build step.

## Pages

| File | Purpose |
|---|---|
| `index.html` | Home — product pitch and call to action |
| `features.html` | Feature overview |
| `contact.html` | Contact page |
| `privacy-policy.html` | Privacy policy (required for YouTube/TikTok app review) |
| `terms-of-service.html` | Terms of service (required for YouTube/TikTok app review) |

## Structure

```
landing/
├── index.html
├── features.html
├── contact.html
├── privacy-policy.html
├── terms-of-service.html
├── css/
│   └── styles.css      # All pages share one stylesheet
├── js/
│   └── main.js         # Shared client-side behavior
└── assets/
    └── logo.png
```

## Local Preview

No build step — serve the folder with any static file server:

```bash
# Python
python -m http.server 8080 -d landing

# or Node
npx serve landing
```

Then open `http://localhost:8080`.

## Deployment

The site is deployed as static assets on **Cloudflare Workers** via the root `wrangler.jsonc`:

```jsonc
{
    "name": "spoolup",
    "compatibility_date": "2024-12-05",
    "assets": {
        "directory": "./landing"
    }
}
```

Deploy with:

```bash
npx wrangler deploy
```

(Requires `wrangler` and a Cloudflare account. No Worker script is involved — assets are served directly.)

## Conventions

- Keep the site dependency-free: plain HTML, one shared CSS file, one shared JS file.
- Privacy policy and terms of service URLs are referenced by the TikTok app submission (see `docs/tiktok-app-submission.md`) — do not rename those files.
