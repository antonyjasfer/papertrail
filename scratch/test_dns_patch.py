import socket
import struct

def dns_query_8888(hostname):
    """Query 8.8.8.8 directly via UDP socket for IPv4 A records."""
    try:
        # Build DNS query packet
        packet = bytearray()
        # Transaction ID
        packet.extend(b"\xaa\xbb")
        # Flags: standard query, recursion desired
        packet.extend(b"\x01\x00")
        # QDCOUNT = 1
        packet.extend(b"\x00\x01")
        # ANCOUNT, NSCOUNT, ARCOUNT = 0
        packet.extend(b"\x00\x00\x00\x00\x00\x00")
        # QNAME
        for part in hostname.split('.'):
            packet.append(len(part))
            packet.extend(part.encode('ascii'))
        packet.append(0)
        # QTYPE = A (1), QCLASS = IN (1)
        packet.extend(b"\x00\x01\x00\x01")

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3.0)
        s.sendto(packet, ("8.8.8.8", 53))
        data, _ = s.recvfrom(2048)
        s.close()

        # Parse answers
        # Header is 12 bytes
        # Skip question section
        idx = 12
        while data[idx] != 0:
            if data[idx] >= 192: # pointer
                idx += 2
                break
            idx += 1 + data[idx]
        else:
            idx += 1 # null byte
            idx += 4 # QTYPE + QCLASS
        
        # Now at Answers section
        ips = []
        while idx < len(data):
            # Name (might be pointer)
            if data[idx] >= 192:
                idx += 2
            else:
                while data[idx] != 0:
                    idx += 1 + data[idx]
                idx += 1
            if idx + 10 > len(data):
                break
            rtype, rclass, ttl, rdlength = struct.unpack("!HHIH", data[idx:idx+10])
            idx += 10
            if rtype == 1 and rdlength == 4: # A record
                ip = socket.inet_ntoa(data[idx:idx+4])
                ips.append(ip)
            idx += rdlength
        return ips
    except Exception as e:
        print(f"DNS 8.8.8.8 fallback failed for {hostname}: {e}")
        return []

if __name__ == "__main__":
    for host in ["login.microsoftonline.com", "papertrailacrdev.azurecr.io", "management.azure.com"]:
        ips = dns_query_8888(host)
        print(f"{host} -> {ips}")
