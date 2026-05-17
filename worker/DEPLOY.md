# Cloudflare Worker Deployment

## Setup

1. Install Wrangler CLI:
```bash
npm install -g wrangler
```

2. Login to Cloudflare:
```bash
wrangler login
```

3. Deploy the worker:
```bash
wrangler deploy
```

## Configuration

- **Worker name**: `spoolup-landing`
- **Static assets**: Served from `./landing` directory
- **Worker script**: `worker/src/index.ts`

## Domain Setup

After deployment, configure your custom domain in Cloudflare Dashboard:
1. Go to Workers & Pages
2. Select `spoolup-landing`
3. Add Custom Domain: `spoolup.alihadiozturk.com`

## Future API Endpoints

The worker includes placeholder API routes for TikTok OAuth:
- `/api/auth/tiktok/callback` - OAuth callback handler

## Environment Variables

Set secrets via Wrangler:
```bash
wrangler secret put TIKTOK_CLIENT_ID
wrangler secret put TIKTOK_CLIENT_SECRET
```
