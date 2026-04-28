#!/usr/bin/env python3
"""
Build a single-row parquet for training-environment CTF smoke tests.

This dataset is intentionally scripted: instead of asking the model to freely
solve the challenge, it tells the model to execute a deterministic checklist
that exercises the same command surface as the rollout executor fake-LLM test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex

import pandas as pd

from dataset_converter_v2 import SKYRL_TOOL_DEFINITIONS
from dataset_converter_ctf import (
    _DEFAULT_CTFMIX,
    _convert_one,
    _load_challenge,
    _load_ctf_metadata,
    _normalize_ctf_subtasks,
    _resolve_challenge_endpoint,
)


DEFAULT_CHALLENGE_REL_PATH = "cybench/HKC/web/22-back-to-the-past"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "ctf_parquet" / "train_ctf_fake_test.parquet"


def _pick_checkpoint_subtasks(subtasks):
    non_flag = [
        subtask
        for subtask in subtasks
        if "flag" not in str(subtask.get("question") or "").lower()
    ]
    selected = non_flag[:3] if len(non_flag) >= 3 else subtasks[:3]
    if len(selected) < 3:
        raise ValueError(
            f"Need at least 3 checkpoint subtasks for the scripted fake test, got {len(selected)}"
        )
    return selected


def _build_long_file_command(answer1: str, answer2: str, answer3: str) -> str:
    return "\n".join(
        [
            "rm -f fake_notes.txt",
            "for i in $(seq 1 140); do",
            '  case "$i" in',
            f"    5) echo {shlex.quote(f'line 005: hidden answer marker is {answer1}')} ;;",
            f"    77) echo {shlex.quote(f'line 077: recovered checkpoint answer is {answer2}')} ;;",
            "    110) echo 'line 110: alpha_marker_for_search_dir' ;;",
            f"    124) echo {shlex.quote(f'line 124: commit counter says {answer3}')} ;;",
            "    *) printf 'line %03d: filler text for editor navigation\\n' \"$i\" ;;",
            "  esac",
            "done > fake_notes.txt",
        ]
    )


def _build_fake_test_context(
    *,
    rel_path: str,
    challenge_data: dict,
    checkpoint_subtasks: list[dict],
    final_flag: str,
) -> str:
    endpoint, host, port = _resolve_challenge_endpoint(challenge_data, rel_path)
    first, second, third = checkpoint_subtasks
    answer1 = str(first.get("answer") or "").strip()
    answer2 = str(second.get("answer") or "").strip()
    answer3 = str(third.get("answer") or "").strip()
    q1 = str(first.get("question") or "").strip()
    q2 = str(second.get("question") or "").strip()
    q3 = str(third.get("question") or "").strip()

    lines = [
        "TEST MODE: scripted CTF integration test.",
        "",
        "This is not a free-form solve. Your goal is to exercise the training-time toolchain deterministically.",
        "Ignore the semantic meaning of observations unless a command fails to parse or the tool is unavailable.",
        "Execute exactly one checklist step per turn, in order.",
        "Do not skip steps, do not merge steps, and do not replace a command with a different command.",
        "After the final `submit` command, stop.",
        "",
        f"Challenge path: {rel_path}",
        f"Target endpoint (in-network): {endpoint}",
        f"Target host for connect_start: {host}",
        f"Target port for connect_start: {port}",
        "",
        "Checkpoint answers to record during this scripted test:",
        f"1. {q1} -> {answer1}",
        f"2. {q2} -> {answer2}",
        f"3. {q3} -> {answer3}",
        f"Final flag -> {final_flag}",
        "",
        "Required checklist:",
        "1. Run `apt-get update`.",
        "2. Run `DEBIAN_FRONTEND=noninteractive apt-get install -y jq python3-setproctitle`.",
        "3. Run `state`.",
        "4. Run `pwd`.",
        "5. Run `ls -la`.",
        "6. Run `create \"probe.txt\"`.",
        "7. Run the following exact edit command:",
        "```",
        "edit 1:1",
        "This file exists to exercise create/open/edit on a real file.",
        "It is not part of the challenge itself.",
        "We only need deterministic local content here.",
        "end_of_edit",
        "```",
        "8. Run `open \"probe.txt\"`.",
        "9. Run this exact multiline shell command to create a long file with embedded checkpoint answers:",
        "```bash",
        _build_long_file_command(answer1, answer2, answer3),
        "```",
        "10. Run `open \"fake_notes.txt\"`.",
        "11. Run `goto 80`.",
        "12. Run `scroll_down`.",
        "13. Run `scroll_up`.",
        f"14. Run `search_file {shlex.quote(answer1)}`.",
        "15. Run `find_file \"fake_notes.txt\" /attacker`.",
        "16. Run `search_dir \"alpha_marker_for_search_dir\" /attacker`.",
        "17. Run this exact command to create canned decompile output:",
        "```bash",
        "mkdir -p /ghidra_out && cat <<'EOF' > /ghidra_out/true.decomp.json",
        "{",
        '  "functions": {',
        '    "main": "int main(void) {\\\\n    return 0;\\\\n}"',
        "  },",
        '  "addresses": {}',
        "}",
        "EOF",
        "```",
        "18. Run this exact command to create canned disassembly output:",
        "```bash",
        "mkdir -p /ghidra_out && cat <<'EOF' > /ghidra_out/true.disas.json",
        "{",
        '  "functions": {',
        '    "main": "main:\\\\n  xor eax, eax\\\\n  ret"',
        "  },",
        '  "addresses": {}',
        "}",
        "EOF",
        "```",
        "19. Run `decompile /bin/true --function_name main`.",
        "20. Run `disassemble /bin/true --function_name main`.",
        "21. Run `debug_start /bin/true`.",
        "22. Run `debug_add_breakpoint _start`.",
        "23. Run `debug_continue`.",
        "24. Run `debug_exec 'x/i $pc'`.",
        "25. Run `debug_step 2`.",
        "26. Run `debug_stop`.",
        f"27. Run `connect_start {host} {port}`.",
        f"28. Run `connect_sendline 'GET / HTTP/1.0\\r\\nHost: {host}\\r\\n\\r\\n'`.",
        "29. Run `connect_exec close`.",
        "30. Run `connect_stop`.",
        f"31. Run `curl -s http://{host}:{port}/ | head -n 5`.",
        f"32. Run `submit_subtask {int(first['index'])} {shlex.quote(answer1)}`.",
        f"33. Run `submit_subtask {int(second['index'])} {shlex.quote(answer2)}`.",
        f"34. Run `submit_subtask {int(third['index'])} {shlex.quote(answer3)}`.",
        f"35. Run `submit {shlex.quote(final_flag)}`.",
        "",
        "For each turn, write a short DISCUSSION that states which numbered checklist step you are executing next, then emit exactly the command for that step.",
    ]
    return "\n".join(lines).strip()


def build_fake_test_row(
    *,
    rel_path: str,
    output_path: Path,
    ctfmix_root: Path,
    max_steps: int,
    timeout: int,
) -> Path:
    challenge_dir = (ctfmix_root / rel_path).resolve()
    challenge_data = _load_challenge(challenge_dir)
    ctf_metadata = _load_ctf_metadata(challenge_dir)
    ctf_subtasks = _normalize_ctf_subtasks(ctf_metadata)
    checkpoint_subtasks = _pick_checkpoint_subtasks(ctf_subtasks)
    final_flag = str(challenge_data.get("flag") or "").strip()
    if not final_flag:
        raise ValueError(f"Expected a final flag in challenge.json for {rel_path}")

    prompt_context_override = _build_fake_test_context(
        rel_path=rel_path,
        challenge_data=challenge_data,
        checkpoint_subtasks=checkpoint_subtasks,
        final_flag=final_flag,
    )
    row = _convert_one(
        rel_path=rel_path,
        task_type="cybench_docker" if rel_path.startswith("cybench/") else "nyu_ctf_subtask",
        ctfmix_root=ctfmix_root,
        max_steps=max_steps,
        timeout=timeout,
        tools_json=json.dumps(SKYRL_TOOL_DEFINITIONS, ensure_ascii=False),
        seen_ids={},
        prompt_context_override=prompt_context_override,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_parquet(output_path, index=False)
    output_path.with_suffix(".json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge-rel-path", default=DEFAULT_CHALLENGE_REL_PATH)
    parser.add_argument("--ctfmix-root", type=Path, default=_DEFAULT_CTFMIX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    out = build_fake_test_row(
        rel_path=str(args.challenge_rel_path).replace("\\", "/").strip("/"),
        output_path=args.output,
        ctfmix_root=args.ctfmix_root.resolve(),
        max_steps=args.max_steps,
        timeout=args.timeout,
    )
    print(f"Wrote fake-train parquet to {out}")
    print(f"Preview row JSON at {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
