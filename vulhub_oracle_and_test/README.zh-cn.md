# Vulhub 参考解与验证脚本

## 如何运行

```bash
bash /data1/jph/VulRL/vulhub_oracle_and_test/run_oracle_and_test.sh \
  /path/to/benchmark/vulhub/<案例目录>
```

示例：

```bash
bash /data1/jph/VulRL/vulhub_oracle_and_test/run_oracle_and_test.sh \
  /data1/jph/VulRL/benchmark/vulhub/aj-report/CNVD-2024-15077
```

**依赖：** Docker（`docker compose` 或 `docker-compose`）、`bash`、`openssl`。脚本会使用或构建 `cve-attacker:latest` 镜像。

**可选环境变量**

| 变量 | 含义 |
|------|------|
| `KEEP_RUNNING=1` | 退出后不销毁 compose 与攻击机容器（调试用）。 |
| `STARTUP_SLEEP` | `compose up` 后等待秒数（默认 `8`）。 |

**退出码：** `oracle_test.sh` 在主机上执行 **两次**：在 **`oracle_solution.sh` 之前**（期望 **`1`**，尚不可观察）与 **之后**（期望 **`0`**）。包装脚本以 **第二次（post）的退出码** 作为进程退出码（`0` 成功，`1` 表示利用效果未观察到）。若 **第一次** 不是 **`1`**，进程以 **`2`** 退出（多为环境未净或测试脚本过弱）。其它非 `0/1` 的测试退出码按错误原样退出。
会打印 `ORACLE_TEST_PRE=<pre> ORACLE_TEST_POST=<post>`。

---

## 脚本放在哪里

**`oracle_solution.sh`** 与 **`oracle_test.sh`** 放在该案例目录内，与 **`docker-compose.yml`**（或 `docker-compose.yaml`）同级；命令行参数即为该目录的绝对或规范路径。

---

## `oracle_solution.sh` — 内容、执行位置与方式

- **位置：** 主机上，案例目录内。
- **执行方式：** 主机读文件并通过标准输入注入攻击机容器：

  `docker exec -i … attacker bash -s < oracle_solution.sh`

  即 **`curl` / `nmap` / Python 等在攻击机容器内执行**，与 vulhub 目标处于 **同一 Docker 网络**；主机只负责调度。

- **用途：** 编写参考利用或环境准备步骤（等价于从攻击机发起的行为）。

- **攻击机内环境变量：** `TARGET_CONTAINER`、`TARGET_CONTAINER_ID`、`COMPOSE_PROJECT_NAME`、`ATTACKER_CONTAINER`。

- **说明：** 脚本经 stdin 执行，`$0` 常为 `-`。访问目标可用容器名/DNS（如 `"$TARGET_CONTAINER"`）。

---

## `oracle_test.sh` — 内容、执行位置与方式

- **位置：** 同上，主机案例目录。
- **执行方式：** 在主机上 **`cd` 到案例目录后执行 `bash ./oracle_test.sh`**。包装脚本会调用 **两次**（参考解前后）；典型“标记文件”类用例期望先 **`1`** 后 **`0`**。
- **用途：** 判断参考解产生的效果能否在 **目标容器** 中被观察到；通过主机上的 **`docker exec` 进入目标**，例如：

  `docker exec "$TARGET_CONTAINER" …`

- **退出码：** `0` 表示可观察到（通过），`1` 表示不可观察（未通过）。包装脚本仅接受这两种退出码。

- **主机环境变量：** `TARGET_CONTAINER`、`TARGET_CONTAINER_ID`、`COMPOSE_PROJECT_NAME`、`ATTACKER_CONTAINER`、`ORACLE_CASE_DIR`（案例目录绝对路径）。

---

## 流程概要

1. 为案例目录执行带独立项目名的 `docker compose up`。  
2. 在目标所在 compose 网络上启动攻击机容器。  
3. 在主机执行 **`oracle_test.sh` 第 1 次**（期望退出 **`1`**，如标记文件尚不存在）。  
4. 用 `docker exec -i` 在攻击机内执行 **`oracle_solution.sh`**。  
5. 在主机执行 **`oracle_test.sh` 第 2 次**（期望退出 **`0`**）。  
6. 除非 `KEEP_RUNNING=1`，否则销毁攻击机并 `compose down -v`。
