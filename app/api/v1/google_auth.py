from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.logging import get_logger
from app.tools.calendar import build_google_authorization_url, save_google_oauth_token

router = APIRouter(prefix="/auth/google", tags=["google-auth"])
log = get_logger(__name__)


@router.get("/start")
async def start_google_auth():
    """Redirect the admin to Google so the app can access the business calendar."""
    return RedirectResponse(build_google_authorization_url())


@router.get("/callback")
async def google_auth_callback(request: Request):
    """Store the OAuth token after Google redirects back to the backend."""
    if "code" not in request.query_params:
        error = request.query_params.get("error")
        detail = f"<p>Google returned: {error}</p>" if error else ""
        return HTMLResponse(
            "<h2>Google Calendar authorization was not completed</h2>"
            "<p>Open the authorization start URL first, then finish the Google consent screen.</p>"
            f"{detail}"
            '<p><a href="/auth/google/start">Start Google Calendar authorization</a></p>',
            status_code=400,
        )

    callback_url = str(request.url)
    try:
        save_google_oauth_token(callback_url)
    except Exception as exc:
        log.warning("google calendar authorization failed: %s", exc)
        return HTMLResponse(
            f"<h2>Google Calendar authorization failed</h2><p>{exc}</p>",
            status_code=400,
        )

    return HTMLResponse(
        "<h2>Google Calendar connected</h2>"
        "<p>You can close this tab and return to the voice agent.</p>"
    )
