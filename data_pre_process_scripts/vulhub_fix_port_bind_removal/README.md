# Vulhub Fixed Port Binding Removal

This directory contains scripts to remove fixed port bindings from Vulhub docker-compose.yml files to enable parallel execution of the same benchmark multiple times.

## Background

Vulhub benchmarks use explicit port bindings (e.g., `"8080:8080"`) which cause conflicts when running multiple instances in parallel. This prevents efficient parallel testing of the same vulnerability.

**Problem**: Fixed bindings like `"8080:8080"` mean HOST port 8080 → CONTAINER port 8080. Only ONE container can bind to HOST port 8080.

**Solution**: Convert to ephemeral bindings like `"8080"` (or just `8080`), which means HOST port (random) → CONTAINER port 8080. Docker automatically assigns unique random ports (e.g., 49152, 49153, etc.).

See `.local_workspace\PORT_CONFLICT_QUICK_REFERENCE.md` for detailed explanation.

## Scripts

### 1. Find Docker Compose Paths
**File**: `1_find_docker_compose_paths.py`

Searches `benchmark/vulhub/` for all directories containing `docker-compose.yml` files and outputs a JSONL file with the paths.

**Usage**:
```bash
python 1_find_docker_compose_paths.py
```

**Output**: `docker_compose_paths.jsonl`
```json
{"path": "benchmark\\vulhub\\apereo-cas\\4.1-rce"}
{"path": "benchmark\\vulhub\\apache-cxf\\CVE-2024-28752"}
...
```

### 2. Docker Compose File Priority
**File**: `ANSWER.md`

**Question**: If a folder has both `docker-compose.yml` and `docker-compose-original.yml`, which would `docker compose up` use?

**Answer**: `docker-compose.yml`

Docker Compose always uses `docker-compose.yml` by default unless you specify a different file with `-f` flag.

### 3. Remove Fixed Port Bindings
**File**: `3_remove_fixed_port_bindings.py`

Main processing script that:
1. Backs up `docker-compose.yml` to `docker-compose-original.yml`
2. Removes fixed port bindings from `docker-compose.yml`
3. Converts `"8080:8080"` → `8080` or `"8080"`

**Features**:
- ✅ Smart filtering to prevent re-processing
- ✅ Dry-run mode to preview changes
- ✅ Test mode with example paths
- ✅ Preserves YAML structure and formatting
- ✅ Handles various port binding formats

**Usage**:

Test with example paths (dry run):
```bash
cd data_pre_process_scripts\vulhub_fix_port_bind_removal
python 3_remove_fixed_port_bindings.py --test --dry-run
```

Test with example paths (apply changes):
```bash
python 3_remove_fixed_port_bindings.py --test
```

Process specific paths:
```bash
python 3_remove_fixed_port_bindings.py --paths "benchmark\vulhub\flask\ssti" "benchmark\vulhub\apache-apisix\CVE-2021-45232"
```

Process all paths from JSONL (dry run):
```bash
python 1_find_docker_compose_paths.py
python 3_remove_fixed_port_bindings.py --dry-run
```

Process all paths from JSONL (apply changes):
```bash
python 3_remove_fixed_port_bindings.py
```

## Filtering Logic

The script prevents re-processing using these filters:

1. **Skip if backup exists AND compose is identical to backup**
   - Means: Already processed but someone reverted changes
   - Action: Don't process again

2. **Skip if backup exists AND compose has no fixed bindings**
   - Means: Already processed successfully
   - Action: Don't process again

3. **Process if backup doesn't exist**
   - Means: Never processed before
   - Action: Create backup and process

4. **Process if backup exists AND compose differs AND has fixed bindings**
   - Means: Backup exists but compose was manually edited and has fixed bindings again
   - Action: Process to remove fixed bindings

## Port Binding Conversion Examples

| Original (Fixed) | Converted (Ephemeral) | Notes |
|------------------|----------------------|-------|
| `"8080:8080"` | `8080` | Simple fixed binding |
| `"127.0.0.1:8080:8080"` | `8080` | With host IP specified |
| `"8080:8081"` | `8081` | Uses container port |
| `8080` | `8080` | Already ephemeral (no change) |
| `"8080"` | `8080` | Already ephemeral string |
| `"3000-3005:3000-3005"` | `"3000-3005"` | Port range |

## Testing

Test the scripts with the provided example paths:

```bash
# Step 1: Find paths
python 1_find_docker_compose_paths.py

# Step 2: Test processing with examples (dry run)
python 3_remove_fixed_port_bindings.py --test --dry-run

# Step 3: Test processing with examples (apply)
python 3_remove_fixed_port_bindings.py --test

# Step 4: Verify changes
git diff benchmark\vulhub\apereo-cas\4.1-rce\docker-compose.yml
git diff benchmark\vulhub\apache-cxf\CVE-2024-28752\docker-compose.yml

# Step 5: Test with docker compose
cd benchmark\vulhub\apereo-cas\4.1-rce
docker compose -p test1 up -d
docker compose -p test2 up -d  # Should work now!
docker compose -p test1 down
docker compose -p test2 down

# Step 6: Restore if needed
cp docker-compose-original.yml docker-compose.yml
```

## Expected Results

For `benchmark\vulhub\apereo-cas\4.1-rce\docker-compose.yml`:

**Before**:
```yaml
version: '2'
services:
 web:
   image: vulhub/apereo-cas:4.1.5
   ports:
    - "8080:8080"
```

**After**:
```yaml
version: '2'
services:
  web:
    image: vulhub/apereo-cas:4.1.5
    ports:
    - 8080
```

## Files Generated

- `docker_compose_paths.jsonl` - List of all docker-compose.yml locations
- `docker-compose-original.yml` - Backup of original files (in each processed directory)

## Dependencies

```bash
pip install pyyaml
```

Or use existing project dependencies (likely already installed).

## Notes

- Original files are safely backed up as `docker-compose-original.yml`
- Script is idempotent - safe to run multiple times
- Dry-run mode allows preview without making changes
- Test mode uses only the two example paths specified in requirements
