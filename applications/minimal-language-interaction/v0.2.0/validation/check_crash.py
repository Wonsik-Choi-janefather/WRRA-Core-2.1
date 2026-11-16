"""Run real process interruption and retry tests using two SQLite files."""
from pathlib import Path
import json
import subprocess
import sys
from tempfile import TemporaryDirectory

from durable_orders import approve, dispatch, initialize, receipt, registry

KEY = "session-A/question-7"
ORDER = {"품목": "녹차", "수량": "한잔"}
CRASH_POINTS = (
    ("before_approval_commit", "approve", 0, False),
    ("after_approval_commit", "approve", 0, True),
    ("before_registry_commit", "dispatch", 0, True),
    ("after_registry_commit_before_reply", "dispatch", 1, True),
    ("after_registry_reply", "dispatch", 1, True),
    ("before_ack_commit", "dispatch", 1, True),
    ("after_ack_commit", "dispatch", 1, False),
)


def invocation(directory, mode, point=None):
    return subprocess.Popen([sys.executable, __file__, mode, str(directory), point or "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def check():
    rows = []
    for point, mode, orders_before, expects_recovery in CRASH_POINTS:
        with TemporaryDirectory() as path:
            directory = Path(path)
            initialize(directory)
            if mode == "dispatch":
                approve(directory, KEY, ORDER)
            child = invocation(directory, mode, point)
            _, error = child.communicate(timeout=10)
            assert child.returncode == 77, (point, error)
            snapshot = registry(directory)
            assert len(snapshot) == orders_before, (point, snapshot)
            first = dispatch(directory)
            assert bool(first) == expects_recovery
            if point == "before_approval_commit":
                assert not registry(directory)
            approve(directory, KEY, ORDER)  # Upstream is safe to replay.
            dispatch(directory)
            approve(directory, KEY, ORDER)
            assert dispatch(directory) == {}
            final = registry(directory)
            assert final == {KEY: (1, ORDER)}
            assert receipt(directory, KEY) == 1
            if snapshot:
                assert final == snapshot
            rows.append({"test": point, "orders_after_interruption": orders_before,
                         "recovered_on_first_dispatch": bool(first), "final_orders": len(final)})

    with TemporaryDirectory() as path:
        directory = Path(path)
        initialize(directory)
        approve(directory, KEY, ORDER)
        children = [invocation(directory, "dispatch") for _ in range(2)]
        for child in children:
            _, error = child.communicate(timeout=10)
            assert child.returncode == 0, error
        assert registry(directory) == {KEY: (1, ORDER)}
        assert receipt(directory, KEY) == 1
        try:
            approve(directory, KEY, {"품목": "물", "수량": "한병"})
        except ValueError:
            pass
        else:
            raise AssertionError("A reused approval ID changed the order.")
        assert registry(directory) == {KEY: (1, ORDER)}
        rows.append({"test": "two_workers_and_conflicting_reuse", "final_orders": 1})
    with TemporaryDirectory() as path:
        directory = Path(path)
        initialize(directory)
        approve(directory, KEY, ORDER)
        approve(directory, "session-B/question-7", ORDER)
        assert len(dispatch(directory)) == 2
        assert sorted(order_id for order_id, _ in registry(directory).values()) == [1, 2]
        rows.append({"test": "two_valid_approvals_same_order_details", "final_orders": 2})
    return rows


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(json.dumps(check(), indent=2))
    else:
        _, mode, path, point = sys.argv
        if mode == "approve":
            approve(Path(path), KEY, ORDER, point)
        else:
            dispatch(Path(path), point)
