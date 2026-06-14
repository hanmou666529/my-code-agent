"""Unit tests for TraceMiner."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_code_agent.distill.miner import TraceMiner
from my_code_agent.distill.models import SessionTrace, TraceStep


def _make_trace(
    trace_id: str,
    user_input: str,
    steps: list[TraceStep] | None = None,
    success: bool = True,
) -> SessionTrace:
    return SessionTrace(
        trace_id=trace_id,
        user_input=user_input,
        steps=steps or [TraceStep(step_number=1)],
        success=success,
    )


class TestTraceMinerClustering:
    def test_clusters_similar_traces(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        traces = [
            _make_trace(f"t{i}", "refactor the auth module", success=True)
            for i in range(5)
        ]
        traces.append(_make_trace("t5", "write a new test file", success=True))
        traces.append(_make_trace("t6", "deploy to production", success=True))

        clusters = miner.cluster_traces(traces, min_cluster_size=3)
        # Only the "refactor auth" group should form a cluster
        assert len(clusters) == 1
        assert clusters[0].size == 5
        assert clusters[0].task_signature == "refactor auth module"

    def test_no_clusters_below_min_size(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        traces = [
            _make_trace(f"t{i}", "refactor auth module", success=True)
            for i in range(2)
        ]
        clusters = miner.cluster_traces(traces, min_cluster_size=3)
        assert len(clusters) == 0

    def test_empty_input(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        clusters = miner.cluster_traces([], min_cluster_size=3)
        assert clusters == []

    def test_all_unsuccessful(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        traces = [
            _make_trace(f"t{i}", "refactor auth", success=False)
            for i in range(5)
        ]
        clusters = miner.cluster_traces(traces, min_cluster_size=3)
        assert clusters == []

    def test_multiple_clusters(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        traces = (
            [_make_trace(f"t{i}", "refactor the auth module", success=True) for i in range(4)]
            + [_make_trace(f"t{i}", "add unit tests for module", success=True) for i in range(4)]
            + [_make_trace("t8", "completely different task", success=True)]
        )
        clusters = miner.cluster_traces(traces, min_cluster_size=3)
        assert len(clusters) == 2
        sizes = sorted(c.size for c in clusters)
        assert sizes == [4, 4]


class TestTaskSignature:
    def test_normalizes_lowercase(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        s1 = miner._compute_task_signature("REFACTOR AUTH MODULE")
        s2 = miner._compute_task_signature("refactor auth module")
        assert s1 == s2

    def test_removes_stopwords(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        sig = miner._compute_task_signature("I want to refactor the auth module please")
        assert "i" not in sig.split()
        assert "want" not in sig.split()
        assert "the" not in sig.split()
        assert "please" not in sig.split()
        assert "refactor" in sig.split()
        assert "auth" in sig.split()
        assert "module" in sig.split()

    def test_removes_punctuation(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        sig = miner._compute_task_signature("refactor(auth.module)")
        assert "(" not in sig
        assert ")" not in sig

    def test_empty_input(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        sig = miner._compute_task_signature("")
        assert sig == ""


class TestJaccardSimilarity:
    def test_identical_sets(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        j = miner._jaccard({"a", "b"}, {"a", "b"})
        assert j == 1.0

    def test_disjoint_sets(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        j = miner._jaccard({"a", "b"}, {"c", "d"})
        assert j == 0.0

    def test_partial_overlap(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        j = miner._jaccard({"a", "b", "c"}, {"a", "b", "d"})
        assert 0.0 < j < 1.0

    def test_both_empty(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        j = miner._jaccard(set(), set())
        assert j == 1.0

    def test_one_empty(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        j = miner._jaccard({"a"}, set())
        assert j == 0.0


class TestMedianTrajectory:
    def test_consistent_actions(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        traces = [
            SessionTrace(
                trace_id=f"t{i}",
                user_input="refactor",
                steps=[
                    TraceStep(step_number=1, action="read_file"),
                    TraceStep(step_number=2, action="search_replace"),
                    TraceStep(step_number=3, action="write_file"),
                ],
                success=True,
            )
            for i in range(3)
        ]
        traj = miner._extract_median_trajectory(traces)
        assert len(traj) == 3
        assert traj[0]["action"] == "read_file"
        assert traj[1]["action"] == "search_replace"
        assert traj[2]["action"] == "write_file"
        assert traj[0]["frequency"] == 3  # all 3 agree

    def test_divergent_actions(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        traces = [
            SessionTrace(
                trace_id=f"t{i}",
                user_input="refactor",
                steps=[
                    TraceStep(step_number=1, action="read_file"),
                    TraceStep(step_number=2, action=["search_replace", "write_file"][i % 2]),
                ],
                success=True,
            )
            for i in range(4)
        ]
        traj = miner._extract_median_trajectory(traces)
        assert len(traj) == 2
        assert traj[0]["action"] == "read_file"
        # Second position: 2 "search_replace" + 2 "write_file" — either is fine
        assert traj[1]["frequency"] == 2

    def test_different_lengths(self, tmp_path: Path) -> None:
        miner = TraceMiner(tmp_path)
        traces = [
            SessionTrace(
                trace_id="t1",
                user_input="refactor",
                steps=[
                    TraceStep(step_number=1, action="read_file"),
                    TraceStep(step_number=2, action="search_replace"),
                ],
                success=True,
            ),
            SessionTrace(
                trace_id="t2",
                user_input="refactor",
                steps=[TraceStep(step_number=1, action="read_file")],
                success=True,
            ),
        ]
        traj = miner._extract_median_trajectory(traces)
        assert len(traj) == 2
        assert traj[0]["action"] == "read_file"
        assert traj[0]["frequency"] == 2
        assert traj[1]["action"] == "search_replace"
        assert traj[1]["frequency"] == 1
