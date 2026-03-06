"""URL validation utilities to prevent SSRF attacks."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Private/reserved hostnames that should be blocked
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",  # GCP metadata
}


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL is not targeting internal/private resources.

    Returns:
        Tuple of (is_safe, reason_if_blocked)
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return False, "Only HTTP/HTTPS URLs are allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Block known internal hostnames
    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False, f"Blocked hostname: {hostname}"

    # Resolve hostname and check IP
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addr_infos = socket.getaddrinfo(hostname, parsed.port or default_port)
        for _family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)

            # For IPv6-mapped IPv4 addresses (e.g. ::ffff:169.254.169.254),
            # extract the underlying IPv4 address for proper checks
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped

            if ip.is_private:
                return False, f"Private IP address: {ip}"
            if ip.is_loopback:
                return False, f"Loopback address: {ip}"
            if ip.is_reserved:
                return False, f"Reserved address: {ip}"
            if ip.is_link_local:
                return False, f"Link-local address: {ip}"
            # Block AWS/GCP/Azure metadata IPs
            if str(ip) in ("169.254.169.254", "169.254.170.2"):
                return False, "Cloud metadata endpoint blocked"
    except socket.gaierror:
        return False, f"Cannot resolve hostname: {hostname}"

    return True, ""
