/**
 * SpoolUp Landing Site - Cloudflare Worker
 * 
 * This Worker serves the static landing site and can be extended
 * for API functionality (TikTok OAuth callbacks, etc.)
 */

export interface Env {
  // Add environment variables here as needed
  // TIKTOK_CLIENT_ID?: string;
  // TIKTOK_CLIENT_SECRET?: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const pathname = url.pathname;
    
    // Serve static assets from the landing directory
    // Cloudflare Workers will automatically serve files from the site bucket
    
    // If it's an API route (for future TikTok OAuth integration)
    if (pathname.startsWith('/api/')) {
      return handleAPI(request, env);
    }
    
    // For all other routes, serve static content
    // The static asset serving is handled by Cloudflare's asset system
    // when configured in wrangler.toml
    
    // This worker is primarily for future API endpoints
    // Static files are served automatically by the Workers platform
    return new Response('Not Found', { status: 404 });
  },
};

async function handleAPI(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  
  // Example: TikTok OAuth callback endpoint (for future implementation)
  if (url.pathname === '/api/auth/tiktok/callback') {
    return new Response(
      JSON.stringify({ 
        status: 'success',
        message: 'OAuth callback received. Integration pending.' 
      }),
      {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      }
    );
  }
  
  return new Response('API endpoint not found', { status: 404 });
}
