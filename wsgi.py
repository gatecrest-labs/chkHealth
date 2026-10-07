from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app

application = create_app()
# Trust one layer of reverse-proxy headers (ALB, Cloud Run ingress, Nginx).
# Without this, request.remote_addr shows the load-balancer IP and
# request.scheme stays "http" even for HTTPS connections.
application.wsgi_app = ProxyFix(application.wsgi_app, x_for=1, x_proto=1, x_host=1)
