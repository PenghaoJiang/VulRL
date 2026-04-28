# vulhub RCE, create /tmp/exploit.txt
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/aj-report/CNVD-2024-15077
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/apache-druid/CVE-2021-25646
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/apisix/CVE-2020-13945
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/apisix/CVE-2021-45232
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/airflow/CVE-2020-11981
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/elasticsearch/CVE-2014-3120
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/elasticsearch/CVE-2015-1427
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/erlang/CVE-2025-32433
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/flask/ssti
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/flink/CVE-2020-17518
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/geoserver/CVE-2024-36401
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/gitlab/CVE-2021-22205
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/gitlist/CVE-2018-1000533
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/hadoop/unauthorized-yarn
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/httpd/CVE-2021-41773
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/httpd/CVE-2021-42013
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/jimureport/CVE-2023-4450
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/jupyter/notebook-rce
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/langflow/CVE-2025-3248
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/libssh/CVE-2018-10933
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/metabase/CVE-2023-38646
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/mongo-express/CVE-2019-10758
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/opentsdb/CVE-2020-35476
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/phpunit/CVE-2017-9841
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/php/8.1-backdoor
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-045
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/thinkphp/5-rce
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/tomcat/CVE-2017-12615
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/weblogic/CVE-2017-10271


# vulhub read (SQLi, LFI, etc.), extract flag_* from output
# SQLi
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/1panel/CVE-2024-39907
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/appweb/CVE-2018-8715
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/django/CVE-2021-35042
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/django/CVE-2022-34265
# LFI
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/flink/CVE-2020-17519
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/coldfusion/CVE-2010-2861
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/rails/CVE-2019-5418
# SSRF
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/adminer/CVE-2021-21311
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752
# file read via malicious MySQL LOCAL INFILE
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/adminer/CVE-2021-43008
# controlled file write
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/airflow/CVE-2020-11978
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/airflow/CVE-2020-17526
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/activemq/CVE-2016-3088
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/activemq/CVE-2022-41678
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/activemq/CVE-2023-46604
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/aria2/rce
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/bash/CVE-2014-6271
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/cacti/CVE-2022-46169
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/cacti/CVE-2023-39361
# privilege escalation
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/couchdb/CVE-2017-12635
# DNS Zone Transfer
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/dns/dns-zone-transfer
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/elasticsearch/CVE-2015-3337
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/elasticsearch/CVE-2015-5531
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/elasticsearch/WooYun-2015-110216
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/solr/Remote-Streaming-Fileread
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/solr/CVE-2017-12629-XXE

# Both rce and read
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/thinkphp/5.0.23-rce



# from reverse alphabetic order
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/yapi/mongodb-inj
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/xxl-job/unacc
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/weblogic/CVE-2020-14882
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/vite/CNVD-2022-44615
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/uwsgi/CVE-2018-7490
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/unomi/CVE-2020-13942
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/tomcat/tomcat8
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/thinkphp/2-rce
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/teamcity/CVE-2023-42793
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/supervisor/CVE-2017-11610
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-001
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-005
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-007
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-008
bash ./run_oracle_and_test_4_rce.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-009
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-012
bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/struts2/s2-032
# SKIP: vite/CVE-2025-30208 - Vite's server.allowedHosts restricts to localhost only.
#       Exploit works from host (localhost:port) but blocked from attacker container (web:5173).
#       Incompatible with attacker-container testing approach.
# SKIP: tomcat/CVE-2025-24813 - Requires Java in attacker container for ysoserial payload generation.
#       Attacker container lacks Java, making deserialization gadget creation impractical.
#       Would require Java installation during exploit (too slow for RL training).
# SKIP: tikiwiki/CVE-2020-15906 - Multi-step chain (auth bypass + SSTI) unreliable in test environment.
#       Requires 51 failed login attempts to trigger lockout, then blank password login.
#       Auth bypass not working reliably despite lockout success. Too slow (51 HTTP requests)
#       and environment-sensitive for practical RL training.

