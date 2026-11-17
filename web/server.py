"""
Dashboard server: serves the static pages in STATIC_DIR and relays the pages' /csv queries to
postgres-bridge (BRIDGE_URL) over the internal compose network, so pages and data share one
origin (no CORS). This service has no database credentials or driver: postgres-bridge is the
only service that talks to PostgreSQL and still applies its own read-only validation/allowlists.
"""

import os
import urllib.error
import urllib.parse
import urllib.request

from flask import Flask, Response, abort, redirect, request, send_from_directory

STATIC_DIR = os.environ.get('STATIC_DIR', '/app/static')
DEFAULT_PAGE = os.environ.get('DEFAULT_PAGE', 'fundo_fixo_cto_ff.html')
BRIDGE_URL = os.environ.get('BRIDGE_URL', 'http://postgres-bridge:13714').rstrip('/')
BRIDGE_TIMEOUT = float(os.environ.get('BRIDGE_TIMEOUT', '60'))

# Only the exact queries the pages run are relayed; anything else is refused here, before the
# bridge. Adding a page/query means adding it to this set (and rebuilding the image).
ALLOWED_SQL = {
    "SELECT * FROM v_cto_ff",
    "SELECT * FROM dataref_ud",
}

# Pages may only talk to this origin
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

app = Flask(__name__)


def text(msg: str, status: int) -> Response:
    return Response(msg, status=status, mimetype='text/plain')


@app.get('/csv')
def csv_relay():
    sql = request.args.get('sql', '').strip()
    db = request.args.get('db', '').strip()
    if sql not in ALLOWED_SQL:
        return text("Error: query not allowed for this dashboard.", 403)
    url = f"{BRIDGE_URL}/csv?" + urllib.parse.urlencode({'db': db, 'sql': sql})
    try:
        with urllib.request.urlopen(url, timeout=BRIDGE_TIMEOUT) as r:
            body, status, ctype = r.read(), r.status, r.headers.get('Content-Type', 'text/csv')
    except urllib.error.HTTPError as e:  # bridge answered with an error: pass its message through
        body, status, ctype = e.read(), e.code, e.headers.get('Content-Type', 'text/plain')
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return text(f"Error: postgres-bridge unavailable ({getattr(e, 'reason', e)}).", 502)
    resp = Response(body, status=status, content_type=ctype)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.get('/health')
def health():
    return {"status": "healthy"}


@app.get('/')
def index():
    return redirect('/' + DEFAULT_PAGE)


# Literal routes (/csv, /health) take precedence over this variable rule in Flask
@app.get('/<path:filename>')
def static_page(filename):
    if not os.path.isdir(STATIC_DIR):
        abort(404)
    resp = send_from_directory(STATIC_DIR, filename)  # rejects paths escaping STATIC_DIR
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Content-Security-Policy'] = CSP
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    return resp
