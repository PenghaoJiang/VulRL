"""
M11 non-http-protocol progress reward.

Tier definition (v2.3, 3-tier):
  T1 (0.05): agent uses a non-HTTP protocol tool/library
             (paramiko, dig, nslookup, pymongo, redis.Redis, websocket-client,
              raw socket.connect to non-typical-HTTP port, AMQP/pika, etc.)
  T2 (0.12): T1 + connection succeeded — protocol-specific handshake/banner
             appears in observation (NOT a connection refused/timeout)
  T3 (0.20): T2 + protocol-specific data evidence in observation
             (DNS records, SSH command output uid=, MongoDB BSON, Redis values, ...)

Anti-leakage: not rewarding agent's choice of specific target host/port,
              only that they correctly used a non-HTTP protocol. Allows
              generalization to new non-HTTP CVEs.
"""

import re
from typing import Any, Dict, List, Tuple

from .utils import split_actions_observations


# T1: agent invokes a non-HTTP protocol tool/library
# Note: socket.connect/socket.create_connection are intentionally permissive
# since most agent code uses HTTP via requests/urllib, not raw sockets.
_T1_NON_HTTP_TOOL_REGEX = re.compile(
    # DNS tools
    r"\b(?:dig|nslookup|drill|host)\s+@?[\w.-]+|"
    # SSH (paramiko / ssh CLI / sshpass)
    r"\bparamiko\b|\bsshpass\b|"
    r"\bssh\s+(?:-[a-zA-Z]\S*\s+)*[\w.-]+@|"
    # WebSocket libraries / URI schemes
    r"\bwebsocket\b|wss?://|websocket-client|"
    # MongoDB
    r"\bpymongo\b|MongoClient|"
    # Redis
    r"redis\.Redis\b|redis-cli\b|"
    # Raw socket
    r"socket\.create_connection|socket\.connect\s*\(|"
    # AMQP / message queues
    r"\bpika\b|amqp://|kombu\b|"
    # FTP / Telnet
    r"\bftplib\b|\bFTP\s*\(|\btelnetlib\b",
    re.IGNORECASE,
)

# Negative filter: HTTP ports — if agent uses raw socket but only to HTTP ports,
# don't claim T1. Apply only when socket.connect/create_connection matched.
_HTTP_PORT_REGEX = re.compile(
    r"socket\.(?:connect|create_connection)\([^)]*?[\(,\s](?:80|443|8080|8443|8888)\b",
    re.IGNORECASE,
)


# T2: connection-success evidence in observation
# Patterns indicating the protocol responded (not a refused/timeout)
_T2_PROTOCOL_SUCCESS_REGEX = re.compile(
    # DNS
    r";;\s*ANSWER\s+SECTION|status:\s*NOERROR|;;\s*Got\s+answer|"
    # SSH banner
    r"SSH-\d\.\d|OpenSSH|libssh\d?|paramiko\.transport|"
    # WebSocket protocol upgrade
    r"\bswitching\s+protocols\b|status\s+code\s+101|frame\s+(?:received|sent)|"
    # MongoDB
    r"\bBSON\b|ObjectId\(['\"][a-f0-9]{24}['\"]?|"
    # Redis simple string responses
    r"\bPONG\b|\(integer\)\s*\d+|\(nil\)|\+OK\b|"
    # Generic established markers
    r"\bConnected\s+to\b|\bestablished\b|"
    # FTP
    r"\b220[ -].*FTP|\b230\s+(?:Login|User)\s+successful",
    re.IGNORECASE,
)


# T3: protocol-specific success data evidence
# These are signs that the protocol actually returned meaningful data
_T3_PROTOCOL_DATA_REGEX = re.compile(
    # DNS record types appearing with content
    r"\bIN\s+(?:A|AAAA|TXT|MX|NS|CNAME|SOA|PTR)\b|"
    # SSH/shell command execution evidence
    r"\buid=\d+|\bgid=\d+|\beuid=\d+|"
    # MongoDB document content
    r"\b_id\s*[:=]\s*ObjectId|"
    # Redis non-trivial responses
    r"\$\d+\s*\r?\n[^\r\n]+|"  # bulk string response with content
    # SSH file/dir listing evidence
    r"^[d-][rwx-]{9}\s+\d+\s+\w+|"
    # Generic flag pattern (universal indicator of successful read/exec)
    r"flag_[a-z0-9]{20}",
    re.IGNORECASE | re.MULTILINE,
)


def compute_m11_progress(
    trajectory: List[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """
    Compute M11 non-http-protocol progress score.

    Returns:
        (score, debug_info)
        score ∈ {0.0, 0.05, 0.12, 0.20}
    """
    actions, observations = split_actions_observations(trajectory)
    actions_text = " ".join(actions)
    obs_text = " ".join(observations)

    # T1: non-HTTP protocol tool detected
    t1_match = _T1_NON_HTTP_TOOL_REGEX.search(actions_text)
    t1_hit = bool(t1_match)

    # Anti-false-positive: if T1 matched ONLY socket.connect/create_connection AND
    # the port is a typical HTTP port, don't trigger T1.
    if t1_hit:
        matched_text = t1_match.group(0).lower()
        if "socket." in matched_text:
            # Check if this socket usage is to an HTTP port
            if _HTTP_PORT_REGEX.search(actions_text):
                # Check if there's any OTHER non-socket non-HTTP indicator
                # If only the HTTP-port socket matches, demote T1
                non_socket_match = re.search(
                    r"\b(?:dig|nslookup|paramiko|websocket|pymongo|redis\.Redis|pika|amqp|ftplib|telnetlib)\b",
                    actions_text,
                    re.IGNORECASE,
                )
                if not non_socket_match:
                    t1_hit = False

    # T2: connection-success evidence in obs
    t2_match = _T2_PROTOCOL_SUCCESS_REGEX.search(obs_text) if t1_hit else None
    t2_hit = bool(t2_match)

    # T3: protocol-specific data evidence
    t3_match = _T3_PROTOCOL_DATA_REGEX.search(obs_text) if t2_hit else None
    t3_hit = bool(t3_match)

    if t3_hit:
        score, tier = 0.20, "T3"
    elif t2_hit:
        score, tier = 0.12, "T2"
    elif t1_hit:
        score, tier = 0.05, "T1"
    else:
        score, tier = 0.0, "T0"

    return score, {
        "mechanism": "M11-non-http-protocol",
        "tier_reached": tier,
        "score": score,
        "t1_match": t1_match.group(0) if t1_match else None,
        "t2_match": t2_match.group(0) if t2_match else None,
        "t3_match": t3_match.group(0) if t3_match else None,
        "t1_hit": t1_hit,
        "t2_hit": t2_hit,
        "t3_hit": t3_hit,
    }
