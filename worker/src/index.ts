/**
 * SpoolUp Landing Site - Cloudflare Worker
 * 
 * Simple static site serving. No API endpoints.
 */

export interface Env {
  // No environment variables needed for static site
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Static assets are served automatically by Cloudflare Workers
    // when configured with [site] in wrangler.toml
    return new Response('Not Found', { status: 404 });
  },
};
