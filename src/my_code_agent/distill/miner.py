"""TraceMiner — clusters successful traces and extracts median trajectories.

Uses lightweight heuristic clustering (Jaccard word-overlap similarity)
to group similar successful sessions, then extracts the median (most
common) tool call sequence within each cluster.

No external ML dependencies — pure stdlib.
"""

from __future__ import annotations

import re
import string
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .models import SessionTrace, TraceCluster, TraceStep

# Common English stopwords to filter from task signatures
_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "this", "that", "these", "those", "i", "you", "he", "she",
    "it", "we", "they", "what", "which", "who", "how", "why",
    "not", "no", "nor", "but", "and", "or", "for", "yet", "so",
    "at", "by", "in", "on", "to", "of", "with", "from", "as",
    "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "up", "down",
    "want", "please", "need", "help", "can",
})


class TraceMiner:
    """Clusters successful traces by task similarity and extracts patterns."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()

    def cluster_traces(
        self,
        traces: list[SessionTrace],
        min_cluster_size: int = 3,
    ) -> list[TraceCluster]:
        """Cluster successful traces and return clusters of sufficient size.

        Args:
            traces: List of successful SessionTrace objects.
            min_cluster_size: Minimum traces per cluster to be kept.

        Returns:
            List of TraceCluster objects, each with median trajectory.
        """
        # Filter to successful traces only
        successful = [t for t in traces if t.success]
        if not successful:
            return []

        # Assign each trace to a cluster based on task signature similarity
        clusters: list[list[SessionTrace]] = []

        for trace in successful:
            sig = self._compute_task_signature(trace.user_input)
            trace_terms = self._tokenize(sig)

            # Find best matching cluster
            best_cluster_idx = -1
            best_jaccard = 0.0

            for idx, cluster in enumerate(clusters):
                # Compute avg Jaccard similarity to cluster members
                similarities = []
                for member in cluster:
                    member_sig = self._compute_task_signature(member.user_input)
                    member_terms = self._tokenize(member_sig)
                    j = self._jaccard(trace_terms, member_terms)
                    similarities.append(j)
                avg_sim = sum(similarities) / len(similarities) if similarities else 0.0

                if avg_sim > best_jaccard and avg_sim > 0.3:
                    best_jaccard = avg_sim
                    best_cluster_idx = idx

            if best_cluster_idx >= 0:
                clusters[best_cluster_idx].append(trace)
            else:
                clusters.append([trace])

        # Filter clusters by minimum size and compute median trajectories
        result: list[TraceCluster] = []
        for idx, cluster in enumerate(clusters):
            if len(cluster) < min_cluster_size:
                continue

            cluster_id = f"cluster_{idx}_{int(hash(frozenset(t.trace_id for t in cluster)) % 1e9):08x}"
            # Use the median signature of the cluster (most common terms)
            all_sigs = [self._compute_task_signature(t.user_input) for t in cluster]
            task_sig = self._median_signature(all_sigs)
            trace_ids = [t.trace_id for t in cluster]

            median_traj = self._extract_median_trajectory(cluster)

            result.append(TraceCluster(
                cluster_id=cluster_id,
                task_signature=task_sig,
                trace_ids=trace_ids,
                median_trajectory=median_traj,
                size=len(cluster),
            ))

        return result

    # ---- Internal helpers ----

    def _compute_task_signature(self, user_input: str) -> str:
        """Extract a normalized task signature from user input.

        Converts to lowercase, removes punctuation, filters stopwords.
        """
        text = user_input.lower()
        # Remove punctuation
        text = text.translate(str.maketrans(string.punctuation, " " * len(string.punctuation)))
        # Filter stopwords
        terms = [w for w in text.split() if w not in _STOPWORDS and len(w) > 1]
        return " ".join(terms)

    def _median_signature(self, signatures: list[str]) -> str:
        """Compute the median signature from a list of signatures.

        Uses term frequency across all signatures to find the most
        representative term set.
        """
        term_freq: Counter = Counter()
        for sig in signatures:
            term_freq.update(sig.split())
        # Take the top terms (up to 3)
        top_terms = [t for t, _ in term_freq.most_common(3)]
        return " ".join(top_terms)

    def _tokenize(self, text: str) -> Set[str]:
        """Tokenize a task signature into a set of terms."""
        return set(text.split()) if text.strip() else set()

    def _jaccard(self, a: Set[str], b: Set[str]) -> float:
        """Compute Jaccard similarity between two term sets."""
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        intersection = a & b
        union = a | b
        return len(intersection) / len(union) if union else 0.0

    def _extract_median_trajectory(
        self,
        cluster: list[SessionTrace],
    ) -> list[dict]:
        """Extract the median (most common) trajectory from a cluster.

        For each step position, finds the most common action.
        """
        # Collect all step sequences aligned by position
        max_steps = max(len(t.steps) for t in cluster) if cluster else 0

        trajectory: list[dict] = []
        for pos in range(max_steps):
            # Gather all actions at this position
            actions_at_pos: list[str] = []
            for trace in cluster:
                if pos < len(trace.steps):
                    step = trace.steps[pos]
                    actions_at_pos.append(step.action or "none")

            # Find the mode (most common action)
            if actions_at_pos:
                counter = Counter(actions_at_pos)
                most_common_action, count = counter.most_common(1)[0]
            else:
                most_common_action = "none"
                count = 0

            trajectory.append({
                "position": pos,
                "action": most_common_action,
                "frequency": count,
                "total": len(actions_at_pos),
            })

        return trajectory
