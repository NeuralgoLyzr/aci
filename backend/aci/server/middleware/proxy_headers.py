import ipaddress

from starlette.types import ASGIApp, Receive, Scope, Send


class ProxyHeadersMiddleware:
    """
    Rewrites scope["client"] and scope["scheme"] from X-Forwarded-For /
    X-Forwarded-Proto headers, but only when the connecting IP is trusted.

    trusted_hosts accepts:
    - "*"                  – trust every proxy (safe when the pod is already
                             in a private subnet behind an ALB / App Gateway)
    - exact IP or hostname – e.g. "my-alb.us-east-1.elb.amazonaws.com"
    - CIDR range           – e.g. "10.200.0.0/24" (Azure App Gateway subnet)
    - comma-separated mix  – e.g. "10.200.0.0/24,10.0.0.5"

    For AWS ALB set SERVER_TRUSTED_PROXY_HOSTS to the ALB DNS name or IP.
    For Azure App Gateway set it to the App Gateway subnet CIDR.
    Leave it unset (or "*") to trust all proxies.
    """

    def __init__(self, app: ASGIApp, trusted_hosts: str | list[str] = "*") -> None:
        self.app = app
        self._trust_all = trusted_hosts == "*"
        self._cidr_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self._exact_hosts: set[str] = set()

        if not self._trust_all:
            if isinstance(trusted_hosts, str):
                hosts = [h.strip() for h in trusted_hosts.split(",") if h.strip()]
            else:
                hosts = [h.strip() for h in trusted_hosts if h.strip()]

            for host in hosts:
                try:
                    self._cidr_networks.append(ipaddress.ip_network(host, strict=False))
                except ValueError:
                    self._exact_hosts.add(host)

    def _is_trusted(self, host: str) -> bool:
        if self._trust_all:
            return True
        if host in self._exact_hosts:
            return True
        try:
            ip = ipaddress.ip_address(host)
            return any(ip in net for net in self._cidr_networks)
        except ValueError:
            return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            client = scope.get("client")
            if client and self._is_trusted(client[0]):
                headers = dict(scope["headers"])

                if b"x-forwarded-for" in headers:
                    # Leftmost entry is the original client IP
                    forwarded_for = headers[b"x-forwarded-for"].decode("latin-1")
                    client_host = forwarded_for.split(",")[0].strip()
                    scope["client"] = (client_host, 0)

                if b"x-forwarded-proto" in headers:
                    proto = headers[b"x-forwarded-proto"].decode("latin-1")
                    scope["scheme"] = proto.split(",")[0].strip()

        await self.app(scope, receive, send)
