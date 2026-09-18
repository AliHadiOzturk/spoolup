"""Embedded FastAPI dashboard (localhost; no auth in v1)."""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from spoolup.dashboard.state import MASKED, DashboardRequest

logger = logging.getLogger(__name__)

_TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")
_STATIC = os.path.join(os.path.dirname(__file__), "static")

INT_KEYS = {"dashboard_port", "stream_fps", "watchdog_interval",
            "auto_update_interval_h", "ingest_buffer_seconds",
            "retry_attempts"}
BOOL_KEYS = {"dashboard_enabled", "enable_live_stream",
             "enable_timelapse_upload", "disable_ssl_verify",
             "kick_enabled", "auto_update_enabled"}

# Mirrors spoolup.main.Config.DEFAULTS plus dashboard-only keys.
# Kept as an explicit list (instead of importing Config) because spoolup.main
# pulls in runtime deps (requests/google-*) that a dashboard-only install
# may not have; update this when Config.DEFAULTS changes.
KNOWN_KEYS = {
    "moonraker_url", "webcam_url", "timelapse_dir", "client_secrets_file",
    "token_file", "stream_resolution", "stream_fps", "stream_bitrate",
    "stream_buffer_size", "timelapse_mode", "printer_ip", "moonraker_port",
    "youtube_category_id", "video_privacy", "stream_privacy",
    "enable_live_stream", "enable_timelapse_upload", "retry_attempts",
    "retry_delay", "disable_ssl_verify", "kick_enabled", "kick_rtmp_url",
    "kick_stream_key", "kick_channel_url", "ingest_buffer_seconds",
    "dashboard_enabled", "dashboard_host", "dashboard_port",
    "watchdog_interval", "auto_update_interval_h", "auto_update_enabled",
    "audio_server_enabled", "audio_default_volume", "data_dir",
    "librespot_path", "spotify_username", "spotify_password",
    "spotify_playlist_uri", "mainsail_url", "keep_stream_on_error",
    "log_file",
}


def create_app(ctx) -> FastAPI:
    app = FastAPI(title="SpoolUp Dashboard", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=_TEMPLATES)
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    def base_env(request: Request):
        return {"request": request}

    def render(request: Request, name: str, **extra):
        context = dict(base_env(request), **extra)
        return templates.TemplateResponse(request, name, context)

    def _need_wizard() -> bool:
        return not os.path.exists(ctx.config_file)

    def _wizard_env():
        return {"config": ctx.mask_config(ctx.config_values()),
                "int_keys": INT_KEYS}

    @app.get("/api/status")
    def api_status():
        return ctx.status()

    @app.get("/api/logs")
    def api_logs(limit: int = 200):
        return {"lines": ctx.logs(limit)}

    @app.get("/api/sessions")
    def api_sessions():
        if getattr(ctx, "sessions", None) is None:
            return {"sessions": []}
        return {"sessions": ctx.sessions.list_recent(50)}

    def _render_app(request: Request, initial: str):
        """Single-page shell: every route serves the app; `initial` picks
        the pane, and the others stay in the DOM (Mainsail iframe and other
        state survive tab switches)."""
        return render(
            request,
            "app.html",
            initial=initial,
            needs_wizard=False,
            config=ctx.mask_config(ctx.config_values()),
            int_keys=INT_KEYS,
            mainsail_url=ctx.config_values().get("mainsail_url") or "",
        )

    @app.get("/", response_class=HTMLResponse)
    def page_dashboard(request: Request):
        if _need_wizard():
            return render(request, "wizard.html", **_wizard_env())
        return _render_app(request, "dashboard")

    @app.get("/logs", response_class=HTMLResponse)
    def page_logs(request: Request):
        return _render_app(request, "logs")

    @app.get("/settings", response_class=HTMLResponse)
    def page_settings(request: Request):
        return _render_app(request, "settings")

    @app.post("/api/wizard/token")
    async def wizard_token(request: Request):
        import tempfile

        try:
            form = await request.form()
            if "token" not in form:
                return JSONResponse({"ok": False, "error": "missing token"},
                                    status_code=400)
            token_path: str = ctx.config_values().get("token_file") \
                or "youtube_token.json"
            parent = os.path.dirname(os.path.abspath(token_path))
            os.makedirs(parent, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(await form["token"].read())
                os.replace(tmp, token_path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            return {"ok": True, "path": token_path}
        except Exception as e:
            logger.exception("token upload failed")
            return JSONResponse({"ok": False, "error": str(e)},
                                status_code=500)

    @app.post("/api/stream/start")
    def api_stream_start():
        ctx.submit(DashboardRequest(kind="stream_start"))
        return {"ok": True, "queued": True}

    @app.post("/api/stream/stop")
    def api_stream_stop():
        return {"ok": bool(ctx.submit(DashboardRequest(kind="stream_stop")))}

    @app.post("/api/stream/restart")
    def api_stream_restart():
        return {"ok": bool(ctx.submit(DashboardRequest(kind="stream_restart")))}

    @app.get("/api/config")
    def api_config_get():
        return ctx.mask_config(ctx.config_values())

    @app.put("/api/config")
    async def api_config_put(request: Request):
        values = await request.json()
        incoming = {
            k: v for k, v in values.items()
            if not (k in ctx.secret_keys() and v == MASKED)
        }
        unknown = set(incoming) - KNOWN_KEYS
        if unknown:
            return JSONResponse(
                {"ok": False, "error": "unknown keys: %s" % sorted(unknown)},
                status_code=400,
            )
        for k, v in incoming.items():
            if k in INT_KEYS and not isinstance(v, int):
                return JSONResponse({"ok": False, "error": "%s must be int" % k},
                                    status_code=400)
            if k in BOOL_KEYS and not isinstance(v, bool):
                return JSONResponse(
                    {"ok": False, "error": "%s must be boolean" % k},
                    status_code=400)
        ok = ctx.save_config(incoming)
        if ok:
            banner = ("Configuration saved — "
                      "restart the application to apply.")
            if banner not in ctx.banners:
                ctx.add_banner(banner)
        return {"ok": ok}

    @app.post("/api/config/test-webcam")
    async def api_test_webcam(request: Request):
        body = await request.json()
        return {"ok": bool(ctx.test_webcam(str(body.get("url") or "")))}

    @app.post("/api/config/test-moonraker")
    async def api_test_moonraker(request: Request):
        body = await request.json()
        return {"ok": bool(ctx.test_moonraker(str(body.get("url") or "")))}

    @app.get("/api/audio/status")
    def api_audio_status():
        srv = ctx.get_audio_server()
        return {
            "enabled": bool(ctx.config_values().get("audio_server_enabled", True)),
            "snapshot": srv.snapshot() if srv else None,
            "playlist": ctx.playlist_state.load() if ctx.playlist_state else None,
        }

    @app.get("/api/music/tracks")
    def api_music_tracks():
        return ctx.audio_library.list_tracks() if ctx.audio_library else []

    @app.post("/api/music/tracks")
    async def api_music_upload(request: Request):
        if ctx.audio_library is None:
            return JSONResponse(
                {"ok": False, "error": "audio not initialized"}, status_code=503
            )
        form = await request.form()
        if "file" not in form:
            return JSONResponse({"ok": False, "error": "missing file"}, status_code=400)
        try:
            track = ctx.audio_library.save_upload(
                form["file"].filename, await form["file"].read()
            )
            return track
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    @app.delete("/api/music/tracks/{track_id}")
    def api_music_delete(track_id: str):
        ok = ctx.audio_library.delete_track(track_id) if ctx.audio_library else False
        return {"ok": ok}

    @app.post("/api/audio/source")
    async def api_audio_source(request: Request):
        body = await request.json()
        return {"ok": bool(ctx.submit(DashboardRequest(kind="audio_source", payload=body)))}

    @app.post("/api/audio/volume")
    async def api_audio_volume(request: Request):
        body = await request.json()
        return {"ok": bool(ctx.submit(DashboardRequest(kind="audio_volume", payload=body)))}

    @app.put("/api/music/playlist")
    async def api_music_playlist(request: Request):
        if ctx.playlist_state is None:
            return JSONResponse(
                {"ok": False, "error": "audio not initialized"}, status_code=503
            )
        body = await request.json()
        ctx.playlist_state.save({"order": body.get("order", [])})
        return {"ok": True}

    @app.get("/music", response_class=HTMLResponse)
    def page_music(request: Request):
        return _render_app(request, "music")

    @app.get("/api/update/status")
    def api_update_status():
        if getattr(ctx, "get_update_status", None) is None:
            return {"pending_restart": False, "last_check": None,
                    "last_apply": None}
        return ctx.get_update_status()

    @app.post("/api/update/check")
    def api_update_check():
        if ctx.updater is None:
            return {"ok": False, "error": "updater not available"}
        result = ctx.updater.check()
        ctx.updater.set_state(last_check=result)
        return result

    @app.post("/api/update/apply")
    def api_update_apply():
        ok = ctx.submit(DashboardRequest(kind="update_apply"))
        return {"ok": ok, "queued": ok}

    @app.get("/printer", response_class=HTMLResponse)
    def page_printer(request: Request):
        return _render_app(request, "printer")

    return app
