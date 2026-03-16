# EzVulRL Generator: Self-Contained Design

## Problem

Previously, `ez_generator` depended on `worker_router/models.py` for Pydantic models:
- Required runtime dependency on parent directory (`sys.path` manipulation)
- Broke when copied to SkyRL directory on different machines
- Made `ez_generator` not truly portable

## Solution

**Use TypedDict instead of Pydantic models** - Type hints only, no runtime validation.

### What Changed

**Created `types.py`:**
- Defines all request/response structures using `TypedDict`
- TypedDict is just for IDE autocomplete and type checking
- At runtime, they're plain Python dictionaries
- No Pydantic dependency needed

**Updated `worker_router_client.py`:**
```python
# Before (Pydantic):
request = RolloutRequest(cve_id="...", prompt="...")
async with session.post(url, json=request.dict()) as resp:
    data = await resp.json()
    return RolloutResult(**data)

# After (Plain dicts):
request: RolloutRequest = {"cve_id": "...", "prompt": "..."}
async with session.post(url, json=request) as resp:
    data = await resp.json()
    return data  # Already a dict matching RolloutResult structure
```

**Updated `ez_vulrl_generator.py`:**
```python
# Before (Pydantic):
request = RolloutRequest(cve_id=..., prompt=...)
print(request.cve_id)
for step in trajectory:
    print(step.action)

# After (Plain dicts):
request: RolloutRequest = {"cve_id": ..., "prompt": ...}
print(request["cve_id"])
for step in trajectory:
    print(step["action"])
```

## Benefits

✅ **Self-Contained**: No imports from parent directories
✅ **Portable**: Copies cleanly to SkyRL directory structure
✅ **Machine-Independent**: Works when generator and worker router are on different machines
✅ **Type-Safe**: Still get IDE autocomplete and type checking
✅ **Lightweight**: No Pydantic dependency for generator

## Trade-offs

### What We Lose:
- ❌ Client-side validation (but server validates anyway)
- ❌ Pydantic's `.dict()` and `.model_dump()` methods (just use the dict directly)
- ❌ Automatic type coercion (e.g., int → float)

### What We Keep:
- ✅ Type hints for IDE support
- ✅ Mypy/Pylance type checking
- ✅ Clear API contracts
- ✅ JSON serialization (plain dicts)

## Architecture

```
Before (Coupled):
┌──────────────────┐
│  ez_generator    │
│                  │
│  imports from ⤵  │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│  worker_router   │
│  └─ models.py    │
│     (Pydantic)   │
└──────────────────┘

After (Decoupled):
┌──────────────────┐
│  ez_generator    │
│  └─ types.py     │
│     (TypedDict)  │
└──────────────────┘
         │ HTTP
         ▼
┌──────────────────┐
│  worker_router   │
│  └─ models.py    │
│     (Pydantic)   │
└──────────────────┘
```

## Files Modified

1. ✅ `ez_generator/types.py` - NEW: TypedDict definitions
2. ✅ `ez_generator/worker_router_client.py` - Dict-based client
3. ✅ `ez_generator/ez_vulrl_generator.py` - Dict-based request creation

## Validation Strategy

**Client-Side** (Generator):
- TypedDict for type hints (IDE support)
- No runtime validation
- Trust the programmer

**Server-Side** (Worker Router):
- Pydantic models for validation
- Validates all incoming requests
- Returns structured errors

This is standard REST API design: **server validates, client trusts**.

## Testing

The generator is now a pure HTTP client:
- Takes dicts as input
- Sends JSON over HTTP
- Receives JSON, returns as dicts
- No dependency on where Worker Router runs

Works correctly when:
- Generator and Worker Router on same machine ✅
- Generator and Worker Router on different machines ✅
- Generator copied to SkyRL directory ✅
