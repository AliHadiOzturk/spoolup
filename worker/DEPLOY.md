# Cloudflare Worker Deployment

## Simple Static Site

This is a **static landing site** - no API endpoints needed. Cloudflare Workers serves the HTML/CSS/JS files directly.

## Deploy

1. Install Wrangler CLI:
```bash
npm install -g wrangler
```

2. Login to Cloudflare:
```bash
wrangler login
```

3. Deploy:
```bash
wrangler deploy
```

4. Add your custom domain in Cloudflare Dashboard:
   - Workers & Pages → spoolup → Custom Domains → Add `spoolup.alihadiozturk.com`

## What Gets Deployed

All files in the `landing/` directory:
- HTML pages (index.html, privacy-policy.html, etc.)
- CSS styles (css/styles.css)
- JavaScript (js/main.js)
- Logo image (assets/logo.png)

## Configuration

- **Worker name**: `spoolup`
- **Static assets**: `landing/` directory
- **No API endpoints** - pure static site
