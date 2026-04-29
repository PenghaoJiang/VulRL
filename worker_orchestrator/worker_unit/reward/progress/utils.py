"""
Shared utilities for progress reward computation.

- Trajectory parsing (action/observation extraction)
- Token pairing detection (high-entropy unique probe token + reflection in response)
- Config payload extraction (used by M10 to restrict T2 regex scope)
"""

import math
import re
from collections import Counter
from typing import Any, Dict, List, Tuple


def split_actions_observations(trajectory: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """Extract action strings and observation strings from a trajectory."""
    actions = [(step.get("action") or "") for step in trajectory]
    observations = [(step.get("observation") or "") for step in trajectory]
    return actions, observations


def shannon_entropy(s: str) -> float:
    """Shannon entropy in bits per character. Random strings score ~4-5+."""
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def is_high_entropy_token(token: str, min_len: int = 12, min_entropy: float = 3.5) -> bool:
    """
    Filter for tokens that are unlikely to appear in natural HTTP traffic by chance.
    Used to detect agent-injected probe tokens for token pairing.
    """
    if len(token) < min_len:
        return False
    return shannon_entropy(token) >= min_entropy


# Pattern: 12+ chars, alphanumeric, must contain BOTH letters AND digits
_HIGH_ENTROPY_TOKEN_REGEX = re.compile(
    r"\b(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{12,}\b"
)


def has_token_pairing(actions: List[str], observations: List[str]) -> Tuple[bool, str]:
    """
    Detect if agent injected a high-entropy unique token AND that token reflects
    in observations (not as pure shell echo).

    Returns (matched, token_or_empty).

    The pairing test:
      1. Find candidate tokens in actions that pass is_high_entropy_token()
      2. For each candidate, check if it appears in any observation
      3. Skip if obs only contains the token as part of a literal "echo TOKEN"
         (that's shell self-echo, not server-side reflection)
    """
    actions_text = " ".join(actions)
    obs_text = " ".join(observations)

    for match in _HIGH_ENTROPY_TOKEN_REGEX.finditer(actions_text):
        token = match.group(0)
        if not is_high_entropy_token(token):
            continue
        if token not in obs_text:
            continue
        # Skip pure shell echo: if obs only contains "echo TOKEN" pattern, that's
        # the bash command being echoed, not server reflection.
        if _is_only_shell_echo(obs_text, token):
            continue
        return True, token

    return False, ""


def _is_only_shell_echo(obs: str, token: str) -> bool:
    """
    True if every occurrence of `token` in `obs` is part of a literal `echo TOKEN`
    pattern (suggesting shell self-echo, not server-side processing).
    """
    # If token appears at least once OUTSIDE an echo context, it's a real pairing
    echo_pattern = rf"echo\s+['\"]?{re.escape(token)}"
    obs_without_echo = re.sub(echo_pattern, "", obs)
    return token not in obs_without_echo


def extract_http_status_codes(observations: List[str]) -> List[Tuple[str, int]]:
    """
    Extract HTTP status codes from observations.
    Returns list of (raw_match, code) tuples.
    """
    obs_text = " ".join(observations)
    matches = re.findall(r"HTTP/[\d.]+\s+(\d{3})", obs_text)
    return [(f"HTTP/x.x {m}", int(m)) for m in matches]


def extract_url_paths(actions: List[str]) -> set:
    """
    Extract distinct URL paths (without query strings) from agent actions.
    Used by D2 (path diversity) and various per-mechanism checks.
    """
    actions_text = " ".join(actions)
    urls = re.findall(r"https?://[^\s'\"<>]+", actions_text)
    paths = set()
    for u in urls:
        # Strip scheme://host, keep only path part
        m = re.match(r"https?://[^/]+(/[^?#]*)", u)
        if m:
            paths.add(m.group(1))
        else:
            # URL like http://host without trailing path
            paths.add("/")
    return paths


def extract_post_put_bodies(actions: List[str]) -> List[str]:
    """
    Extract POST/PUT body content from agent actions.
    Used by M10 to restrict T2 regex scope to actual config payloads.

    Heuristics covered:
      - curl -d / --data / --data-raw / --data-binary: quoted argument
      - curl --data-urlencode: quoted argument (used in some CVE oracles)
      - wget --post-data="..." or --post-data='...' (note: --post-file= not extractable)
      - Python requests.post/put with data= or json=: argument
      - HTTP body in Python urllib: data=... bytes
      - JDBC URL (full URL kept as a "body" since it's the config payload)

    Limitations (known blind spots, not fixing now):
      - --data-urlencode @file (file content not accessible)
      - wget --post-file=PATH
      - When agent passes a Python variable name (data=payload), only the
        variable name is captured; body content is missed.
    """
    bodies = []
    actions_text = " ".join(actions)

    # curl --data variants: -d / --data / --data-raw / --data-binary / --data-urlencode
    # Quoted argument (single or double)
    for m in re.finditer(
        r"(?:--data(?:-raw|-binary|-urlencode)?|-d)\s+(['\"])(.*?)(\1|$)",
        actions_text, re.DOTALL
    ):
        bodies.append(m.group(2))

    # wget --post-data="..." or --post-data='...' (note: = sign is required for wget)
    # Wget also supports --post-data ... (space-separated) but rare; we cover both.
    for m in re.finditer(
        r"--post-data[=\s]+(['\"])(.*?)(\1|$)",
        actions_text, re.DOTALL
    ):
        bodies.append(m.group(2))

    # wget --post-data=value (unquoted, until whitespace)
    for m in re.finditer(
        r"--post-data=([^\s'\"]+)",
        actions_text
    ):
        bodies.append(m.group(1))

    # Python requests.post(... data=..., json=...)
    # Match the body content between data= and the next comma or close paren
    for m in re.finditer(
        r"(?:data|json)\s*=\s*([^,)\n]+(?:\([^)]*\))?)",
        actions_text
    ):
        bodies.append(m.group(1))

    # JDBC URL extraction (treat as config payload)
    for m in re.finditer(r"jdbc:[^\s'\"<>]+", actions_text):
        bodies.append(m.group(0))

    return bodies


def extract_traversal_sequences(text: str) -> List[str]:
    """
    Extract path-traversal sequences from text. A 'complete traversal' requires
    at least one full ../ pattern (or encoded variant, including mixed encoding).

    Returns list of matched traversal substrings.

    Supports:
      - Plain: ../  ..\
      - Fully URL-encoded: %2e%2e%2f, %2e%2e/, %2e%2e%5c
      - Mixed encoding: .%2e/, %2e./, .%2e%2f, %2e.%2f  (Apache CVE-2021-41773 style)
      - Double URL-encoded: %252e%252e (httpd CVE-2021-42013)
    """
    # Single regex covering all variants:
    # `dot-or-encoded` followed by `dot-or-encoded` followed by `slash-or-encoded`
    # `%252e` (double-encoded) handled separately
    combined = (
        r"(?:\.|%2e|%252e){2}(?:/|%2f|%5c|\\|%252f)"
    )
    matches = re.findall(combined, text, re.IGNORECASE)
    return matches


# Regex for sensitive file content patterns (reused across M03/M04/etc.)
SENSITIVE_FILE_PATTERNS = [
    r"root:[x*!]:0:0:",                                       # /etc/passwd
    r"-----BEGIN\s+(?:RSA|EC|OPENSSH|DSA|PGP)?\s*PRIVATE\s+KEY",   # private key
    r"^\s*adapter:\s*(?:mysql|postgres|sqlite)",               # Rails database.yml
    r"(?:mysql_password|DB_PASSWORD|secret_key_base)\s*[:=]",  # config secrets
    r"nameserver\s+\d+\.\d+\.\d+\.\d+",                       # /etc/resolv.conf
    r"\bAPI_KEY\s*=",                                          # env var dump
]


def has_sensitive_file_content(text: str) -> bool:
    """Return True if any well-known sensitive file pattern appears in text."""
    for p in SENSITIVE_FILE_PATTERNS:
        if re.search(p, text, re.MULTILINE):
            return True
    return False


def has_flag_string(text: str) -> bool:
    """Detect canonical CTF flag pattern flag_[a-z0-9]{20}."""
    return bool(re.search(r"flag_[a-z0-9]{20}", text))
