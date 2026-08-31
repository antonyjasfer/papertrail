import socket
import sys

_orig_getaddrinfo = socket.getaddrinfo

# Initialize custom DNS resolver using 8.8.8.8 and 1.1.1.1
try:
    import dns.resolver
    _resolver = dns.resolver.Resolver()
    _resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
    _resolver.timeout = 3.0
    _resolver.lifetime = 6.0
except Exception:
    _resolver = None

def resolve_with_dnspython(hostname):
    if not _resolver:
        return []
    try:
        answers = _resolver.resolve(hostname, "A")
        return [str(rdata) for rdata in answers]
    except Exception:
        return []

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        if isinstance(host, str) and not host.replace('.', '').isdigit():
            ips = resolve_with_dnspython(host)
            if ips:
                results = []
                for ip in ips:
                    try:
                        # Clean flags to prevent canonname issues
                        clean_flags = flags & ~socket.AI_CANONNAME if hasattr(socket, "AI_CANONNAME") else flags
                        res = _orig_getaddrinfo(ip, port, socket.AF_INET, type, proto, clean_flags)
                        results.extend(res)
                    except Exception:
                        pass
                if results:
                    return results
        raise

socket.getaddrinfo = patched_getaddrinfo
