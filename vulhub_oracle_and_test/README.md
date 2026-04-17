# Vulhub oracle runner

## Run

```bash
bash /data1/jph/VulRL/vulhub_oracle_and_test/run_oracle_and_test.sh \
  /path/to/benchmark/vulhub/<case>
```

Example:

```bash
bash /data1/jph/VulRL/vulhub_oracle_and_test/run_oracle_and_test.sh \
  /data1/jph/VulRL/benchmark/vulhub/aj-report/CNVD-2024-15077
```

**Requirements:** Docker (with `docker compose` or `docker-compose`), `bash`, `openssl`. The script builds or uses the `cve-attacker:latest` image.

**Optional environment**

| Variable | Meaning |
|----------|---------|
| `KEEP_RUNNING=1` | Leave compose stack and attacker container up after exit (debug). |
| `STARTUP_SLEEP` | Seconds to wait after `compose up` (default `8`). |

The process **exits with the same code** as `oracle_test.sh` (`0` or `1` only; other codes are treated as errors). It prints `ORACLE_TEST_RESULT=<0|1>`.

---

## Where the scripts live

Place **`oracle_solution.sh`** and **`oracle_test.sh`** next to that case’s `docker-compose.yml` (same directory you pass as the argument).

---

## `oracle_solution.sh` — what it is, where it runs

- **Location:** on the host, inside the case directory.
- **How it runs:** the host reads the file and streams it into the attacker container:

  `docker exec -i … attacker bash -s < oracle_solution.sh`

  So the shell and tools (`curl`, `nmap`, Python, etc.) run **inside** `cve-attacker`, on the **same Docker network** as the vulhub target. The host only orchestrates.

- **Purpose:** encode a reference exploit or setup steps (what an agent would do from the attacker).

- **Environment (inside the attacker):** `TARGET_CONTAINER`, `TARGET_CONTAINER_ID`, `COMPOSE_PROJECT_NAME`, `ATTACKER_CONTAINER`.

- **Note:** The script is fed via stdin; `$0` may be `-`. Reach the target by container name/DNS (e.g. `"$TARGET_CONTAINER"`) on the compose network.

---

## `oracle_test.sh` — what it is, where it runs

- **Location:** same case directory on the host.
- **How it runs:** **`bash ./oracle_test.sh` on the host**, with working directory set to the case folder.
- **Purpose:** check whether the solution’s effects are visible **inside the target container** (or via its filesystem/process state). Use host `docker` to reach the target, for example:

  `docker exec "$TARGET_CONTAINER" …`

- **Exit code:** `0` = effect observable (pass), `1` = not observable (fail). The wrapper rejects other exit codes.

- **Environment (on the host):** `TARGET_CONTAINER`, `TARGET_CONTAINER_ID`, `COMPOSE_PROJECT_NAME`, `ATTACKER_CONTAINER`, `ORACLE_CASE_DIR` (absolute path to the case directory).

---

## Flow (short)

1. `docker compose up` for the case with an isolated project name.  
2. Start attacker on the target’s compose network.  
3. Run `oracle_solution.sh` **in** the attacker (via `docker exec -i`).  
4. Run `oracle_test.sh` **on** the host (it uses `docker exec` into **`TARGET_CONTAINER`** as needed).  
5. Tear down attacker and `compose down -v` unless `KEEP_RUNNING=1`.
