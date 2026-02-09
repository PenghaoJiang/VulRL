# Quick Start Guide

## TL;DR

```bash
cd E:\git_fork_folder\VulRL

# Preview what will be changed (safe, no modifications)
python data_pre_process_scripts\vulhub_fix_port_bind_removal\3_remove_fixed_port_bindings.py --dry-run

# Apply changes to all 307 Vulhub benchmarks
python data_pre_process_scripts\vulhub_fix_port_bind_removal\3_remove_fixed_port_bindings.py
```

## What This Does

Converts fixed port bindings to ephemeral ports:
- **Before**: `"8080:8080"` (fixed - causes conflicts)
- **After**: `8080` (ephemeral - Docker assigns random ports)

## Why?

Enables running the **same** Vulhub benchmark multiple times in parallel without port conflicts.

## Example

**Before** (can only run once):
```bash
docker compose -p test1 up -d  # ✅ Works
docker compose -p test2 up -d  # ❌ FAILS: port 8080 already allocated
```

**After** (can run multiple times):
```bash
docker compose -p test1 up -d  # ✅ Works (gets port 49152)
docker compose -p test2 up -d  # ✅ Works (gets port 49153)
docker compose -p test3 up -d  # ✅ Works (gets port 49154)
```

## Safety Features

- ✅ Original files backed up as `docker-compose-original.yml`
- ✅ Dry-run mode to preview changes
- ✅ Smart filtering prevents re-processing
- ✅ Idempotent - safe to run multiple times

## Restore Original

If you need to revert:
```bash
cd benchmark\vulhub\<target>\<cve>
cp docker-compose-original.yml docker-compose.yml
```

## Test First

Test with 2 example benchmarks:
```bash
python data_pre_process_scripts\vulhub_fix_port_bind_removal\3_remove_fixed_port_bindings.py --test --dry-run
python data_pre_process_scripts\vulhub_fix_port_bind_removal\3_remove_fixed_port_bindings.py --test
```

## More Info

- Full documentation: `README.md`
- Implementation details: `SUMMARY.md`
- Background: `.local_workspace\PORT_CONFLICT_QUICK_REFERENCE.md`
