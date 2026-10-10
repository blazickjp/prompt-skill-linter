"""Loopback-only Studio server. No upload execution and no source persistence."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import urlsplit, unquote

from . import __version__
from .engine import ContractError
from .schema import unique_object
from .extraction import extract, accept
from .service import analyze, examples, what_if, contract_diff, counterexample_explorer, export_bundle

MAX_BODY = 2_000_000
WEB_ROOT = Path(__file__).resolve().parents[1] / 'web'
if not WEB_ROOT.is_dir():
    WEB_ROOT = Path(__file__).with_name('web')


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler=None):
        if address[0] not in ('127.0.0.1', 'localhost'):
            raise ValueError('Studio binds only to IPv4 loopback; use 127.0.0.1.')
        self.analysis_slots = threading.BoundedSemaphore(2)
        super().__init__(address, handler or Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'PromptSkillStudio'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        # No source text, request URLs, credentials or provider bodies in logs.
        return

    def send_bytes(self, data, content_type, status=200, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def json(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8', status)

    def error(self, code, message, status=400):
        self.json({'error': {'code': code, 'message': message}}, status)

    def authorized_origin(self):
        port = self.server.server_address[1]
        allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.headers.get('Host') not in allowed_hosts:
            self.error('INVALID_HOST', 'Only this loopback server host is accepted.', 403)
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin not in {'http://' + host for host in allowed_hosts}:
            self.error('INVALID_ORIGIN', 'Cross-origin requests are not accepted.', 403)
            return False
        if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
            self.error('CROSS_SITE_REQUEST', 'Cross-site requests are not accepted.', 403)
            return False
        return True

    def do_OPTIONS(self):
        self.error('METHOD_NOT_ALLOWED', 'Cross-origin preflight is not supported.', 405)

    def do_GET(self):
        if not self.authorized_origin():
            return
        if not self.path.startswith('/') or len(self.path) > 4096:
            self.error('INVALID_PATH', 'Invalid request path.', 400); return
        path = urlsplit(self.path).path
        if path == '/api/health':
            from .provider import configuration
            self.json({'version': __version__, 'status': 'ready', 'local_only': True,
                       'capabilities': ['reviewed_contracts', 'offline_extraction', 'bounded_cnf', 'finite_workflows', 'what_if', 'regression_export'],
                       'provider': configuration()})
            return
        if path == '/api/examples':
            self.json(examples()); return
        if path == '/api/schema':
            self.json(json.loads(Path(__file__).with_name('contract.schema.json').read_text())); return
        if path.startswith('/api/'):
            self.error('NOT_FOUND', 'Unknown API endpoint.', 404); return
        relative = unquote(path).lstrip('/') or 'index.html'
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in relative) or '\\' in relative or ':' in relative or any(part.startswith('.') or part == '..' for part in relative.split('/')):
            self.error('INVALID_PATH', 'Invalid static asset path.', 400); return
        try:
            target = (WEB_ROOT / relative).resolve()
            if not target.is_relative_to(WEB_ROOT.resolve()) or not target.is_file() or target.suffix not in ('.html', '.css', '.js', '.svg', '.png', '.ico', '.json', '.woff2'):
                self.error('NOT_FOUND', 'Static asset not found.', 404); return
            data = target.read_bytes()
        except (ValueError, OSError):
            self.error('INVALID_PATH', 'Static asset path could not be read.', 400); return
        self.send_bytes(data, mimetypes.guess_type(target.name)[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.authorized_origin():
            return
        if self.headers.get('Transfer-Encoding') is not None:
            self.error('INVALID_BODY', 'Chunked request bodies are not supported.', 400); return
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            self.error('CONTENT_TYPE', 'POST requests require application/json.', 415); return
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            self.error('INVALID_BODY', 'Content-Length must be an integer.', 400); return
        if not 0 < size <= MAX_BODY:
            self.error('BODY_LIMIT', f'JSON body must be between 1 and {MAX_BODY} bytes.', 413); return
        if not self.server.analysis_slots.acquire(blocking=False):
            self.error('BUSY', 'Two analyses are already running. Please retry shortly.', 429); return
        try:
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ContractError('Incomplete request body.')
            value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite number')))
            if not isinstance(value, dict):
                raise ContractError('Request body must be a JSON object.')
            path = urlsplit(self.path).path
            if path == '/api/analyze':
                result = analyze(value)
            elif path == '/api/extract':
                provider = value.get('provider', 'offline')
                if provider == 'openai':
                    from .provider import model_extract
                    result = model_extract(value.get('sources'), value.get('consent'))
                else:
                    result = extract(value.get('sources'), provider)
            elif path == '/api/accept':
                result = accept(value.get('draft'), value.get('accepted_candidate_ids'))
                analyze(result['bundle'])  # Source and accepted interpretation validation before returning.
            elif path == '/api/what-if':
                result = what_if(value.get('bundle'), value.get('changes'))
            elif path == '/api/diff':
                result = contract_diff(value.get('before'), value.get('after'))
            elif path == '/api/explore':
                result = counterexample_explorer(value.get('bundle'), value.get('workflow_id'), value.get('context_id'))
            elif path == '/api/export':
                data = export_bundle(value.get('bundle'))
                self.send_bytes(data, 'application/zip', filename='prompt-skill-linter-regression.zip')
                return
            else:
                self.error('NOT_FOUND', 'Unknown API endpoint.', 404); return
            self.json(result)
        except (ContractError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
            import sys
            error = sys.exc_info()[1]
            message = str(error) if isinstance(error, ContractError) else 'Malformed or unsupported input; no analysis result was produced.'
            self.error('INVALID_INPUT', message[:500], 400)
        except (OSError, TimeoutError):
            self.error('IO_ERROR', 'The local operation or configured provider request could not complete.', 502)
        finally:
            self.server.analysis_slots.release()


def serve(port=8765):
    server = StudioServer(('127.0.0.1', port))
    print(f'Prompt Skill Studio: http://127.0.0.1:{server.server_address[1]}', flush=True)
    print('Local-only. Source contents are not persisted. Ctrl+C stops the server.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
