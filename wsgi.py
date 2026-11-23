import os

from app import app


class PrefixMiddleware:
    def __init__(self, wsgi_app, prefix):
        self.wsgi_app = wsgi_app
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == self.prefix or path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = self.prefix
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            return self.wsgi_app(environ, start_response)
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Not Found: passez par le prefixe " + self.prefix.encode() + b"\n"]


_prefix = os.environ.get("TARDROP_PREFIX", "").strip()
if _prefix and _prefix != "/":
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, _prefix)

if __name__ == "__main__":
    app.run()
