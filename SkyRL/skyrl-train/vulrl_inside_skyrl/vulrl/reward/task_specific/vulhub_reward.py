"""
Vulhub specific reward computation using BLEU score.

Compares agent's trajectory actions against ground truth PoC scripts
using BLEU-2 and BLEU-4 scores with linear mapping.
"""

import math
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional


class VulhubReward:
    """
    BLEU-based reward computation for Vulhub tasks.

    Extracts action commands from the agent's trajectory, compares them
    against the ground truth PoC script using BLEU-2 and BLEU-4, then
    maps the scores linearly and combines with weighted average.

    Reward formula:
        reward = 0.7 * linear_map(BLEU-2) + 0.3 * linear_map(BLEU-4)
    """

    # Linear mapping parameters
    BLEU2_BASELINE = 0.03
    BLEU2_CAP = 0.30
    BLEU4_BASELINE = 0.01
    BLEU4_CAP = 0.20

    # Combination weights
    WEIGHT_BLEU2 = 0.7
    WEIGHT_BLEU4 = 0.3

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize VulhubReward.

        Args:
            config: Environment configuration. Expected keys:
                - dataset_path: Path to train.parquet with ground truth PoCs
        """
        self.config = config or {}
        self._poc_cache: Dict[str, str] = {}
        self._load_ground_truth()

    def _load_ground_truth(self):
        """Load ground truth PoC scripts from dataset parquet file."""
        dataset_path = self.config.get('dataset_path', '')

        if not dataset_path:
            candidates = [
                Path.home() / "data" / "cve_vulhub" / "train.parquet",
                Path("/data1/jph/VulRL/data/cve_vulhub/train.parquet"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    dataset_path = str(candidate)
                    break

        if not dataset_path or not Path(dataset_path).exists():
            print(f"[VulhubReward] Warning: Dataset not found, reward will be 0.0")
            return

        try:
            import pandas as pd
            df = pd.read_parquet(dataset_path)
            for _, row in df.iterrows():
                # Build lookup by both vulhub_path and cve_id
                poc = row.get('poc_script', '')
                if not poc:
                    continue
                vulhub_path = row.get('vulhub_path', '')
                cve_id = row.get('cve_id', '')
                if vulhub_path:
                    self._poc_cache[vulhub_path] = poc
                if cve_id:
                    self._poc_cache[cve_id] = poc
            print(f"[VulhubReward] Loaded {len(self._poc_cache)} ground truth PoC entries")
        except Exception as e:
            print(f"[VulhubReward] Warning: Failed to load dataset: {e}")

    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        """
        Compute BLEU-based reward for a Vulhub trajectory.

        Args:
            trajectory: List of step dicts with 'action', 'observation', etc.
            task_id: Vulhub task ID (e.g., "apache/CVE-2021-41773")

        Returns:
            Reward score in [0, 1]
        """
        # Look up ground truth PoC
        ground_truth = self._poc_cache.get(task_id, '')
        if not ground_truth:
            print(f"[VulhubReward] No ground truth for {task_id}, reward=0.0")
            return 0.0

        # Extract action text from trajectory
        actions_text = self._extract_actions(trajectory)
        if not actions_text.strip():
            print(f"[VulhubReward] No actions in trajectory for {task_id}, reward=0.0")
            return 0.0

        # Tokenize
        hyp_tokens = self._tokenize(actions_text)
        ref_tokens = self._tokenize(ground_truth)

        if not hyp_tokens or not ref_tokens:
            print(f"[VulhubReward] Empty tokens for {task_id}, reward=0.0")
            return 0.0

        # Compute BLEU scores
        bleu2 = self._compute_bleu(hyp_tokens, ref_tokens, max_n=2)
        bleu4 = self._compute_bleu(hyp_tokens, ref_tokens, max_n=4)

        # Linear mapping
        score2 = self._linear_map(bleu2, self.BLEU2_BASELINE, self.BLEU2_CAP)
        score4 = self._linear_map(bleu4, self.BLEU4_BASELINE, self.BLEU4_CAP)

        # Weighted combination
        reward = self.WEIGHT_BLEU2 * score2 + self.WEIGHT_BLEU4 * score4

        print(
            f"[VulhubReward] {task_id}: "
            f"BLEU-2={bleu2:.4f}(mapped={score2:.4f}), "
            f"BLEU-4={bleu4:.4f}(mapped={score4:.4f}), "
            f"reward={reward:.4f}"
        )

        return reward

    # ========================================================================
    # Action extraction
    # ========================================================================

    @staticmethod
    def _extract_actions(trajectory: List[Dict[str, Any]]) -> str:
        """
        Extract action commands from trajectory and concatenate into text.

        Only extracts the commands/requests themselves (approach A),
        not the observations/outputs.
        """
        parts = []
        for step in trajectory:
            action = step.get('action')
            if action is None:
                continue

            if isinstance(action, str):
                parts.append(action)
            elif hasattr(action, 'action_type') and hasattr(action, 'arguments'):
                # StandardAction object
                args = action.arguments if isinstance(action.arguments, dict) else {}
                action_type = str(action.action_type).upper()

                if 'BASH' in action_type:
                    cmd = args.get('command', '')
                    if cmd:
                        parts.append(cmd)
                elif 'HTTP' in action_type:
                    method = args.get('method', 'GET')
                    url = args.get('url', '')
                    path = args.get('path', '')
                    data = args.get('data', '')
                    json_data = args.get('json', '')
                    http_text = f"{method} {url}{path}"
                    if data:
                        http_text += f" {data}"
                    if json_data:
                        http_text += f" {json_data}"
                    parts.append(http_text)
            elif isinstance(action, dict):
                # Dict-based action
                cmd = (
                    action.get('command', '')
                    or action.get('arguments', {}).get('command', '')
                )
                if cmd:
                    parts.append(cmd)

        return ' '.join(parts)

    # ========================================================================
    # Tokenization
    # ========================================================================

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        Tokenize text for BLEU computation.

        Lowercases text and splits into tokens on whitespace and code
        delimiters (:/{}[]()="'). Keeps meaningful fragments like path
        segments, port numbers, and percent-encoded characters.
        """
        text = text.lower()
        # Match alphanumeric sequences, dots, percent-encoded chars, hyphens, underscores
        tokens = re.findall(r'[a-z0-9_.%\-]+', text)
        # Filter out single-char non-digit tokens (noise)
        tokens = [t for t in tokens if len(t) > 1 or t.isdigit()]
        return tokens

    # ========================================================================
    # BLEU computation
    # ========================================================================

    @staticmethod
    def _get_ngrams(tokens: List[str], n: int) -> Counter:
        """Count n-grams in a token list."""
        return Counter(
            tuple(tokens[i:i + n])
            for i in range(len(tokens) - n + 1)
        )

    @classmethod
    def _compute_bleu(
        cls,
        hypothesis: List[str],
        reference: List[str],
        max_n: int
    ) -> float:
        """
        Compute modified BLEU-N score (without brevity penalty).

        Score = exp(1/N * sum(log(p_n) for n in 1..N))

        where p_n is the clipped n-gram precision.

        Brevity penalty is intentionally omitted because hypothesis
        (bash commands) and reference (Python PoC script) are
        structurally different formats — the length difference is
        inherent to the format mismatch, not agent quality.

        Args:
            hypothesis: Tokenized hypothesis (agent actions)
            reference: Tokenized reference (ground truth PoC)
            max_n: Maximum n-gram order (2 for BLEU-2, 4 for BLEU-4)

        Returns:
            Score in [0, 1]
        """
        if not hypothesis or not reference:
            return 0.0

        # N-gram precisions (no brevity penalty)
        log_precisions = []
        for n in range(1, max_n + 1):
            hyp_ngrams = cls._get_ngrams(hypothesis, n)
            ref_ngrams = cls._get_ngrams(reference, n)

            if not hyp_ngrams:
                return 0.0

            # Clipped counts
            clipped = sum(
                min(count, ref_ngrams.get(ng, 0))
                for ng, count in hyp_ngrams.items()
            )
            total = sum(hyp_ngrams.values())

            if clipped == 0:
                return 0.0

            log_precisions.append(math.log(clipped / total))

        # Geometric mean with equal weights
        log_avg = sum(log_precisions) / max_n
        return math.exp(log_avg)

    # ========================================================================
    # Reward mapping
    # ========================================================================

    @staticmethod
    def _linear_map(score: float, baseline: float, cap: float) -> float:
        """
        Linear mapping with baseline floor and cap ceiling.

        Scores <= baseline map to 0.0, scores >= cap map to 1.0,
        scores in between are linearly interpolated.
        """
        if score <= baseline:
            return 0.0
        return min(1.0, (score - baseline) / (cap - baseline))
