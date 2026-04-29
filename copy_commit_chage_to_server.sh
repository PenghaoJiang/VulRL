#!/bin/bash

git diff --name-only HEAD~1 | while read file; do
  echo "$file"
  ssh -n vulrl-server "mkdir -p /data1/jph/VulRL_CTF/VulRL/$(dirname "$file")"
  scp "$file" vulrl-server:/data1/jph/VulRL_CTF/VulRL/"$file"
done