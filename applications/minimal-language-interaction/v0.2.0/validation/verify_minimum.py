"""Exact finite observation test over all projections of the ten scenes."""
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path

from run_scenes import evaluate

FIELDS = ("speaker", "recipient", "question")
ROOT = Path(__file__).resolve().parent


def expected_output(scene):
    # Include exact committed-order contents, not merely an approval flag.
    return json.dumps(scene["expected"], ensure_ascii=False, sort_keys=True)


def group_scenes(scenes, fields):
    groups = defaultdict(list)
    for scene in scenes:
        # In this corpus the same prelude and targeted dialogue induce the
        # same prior order state. The evaluated reply is always “네”.
        fixed_context = (scene.get("prelude"), scene["dialogue"])
        observation = fixed_context + tuple(scene[field] for field in fields)
        groups[observation].append(scene)
    return tuple(groups.values())


def verify(scenes, fields):
    groups = group_scenes(scenes, fields)
    conflicts = []
    unavoidable = missed_when_safe = 0
    for group in groups:
        counts = Counter(expected_output(scene) for scene in group)
        if len(counts) > 1:
            conflicts.append([scene["id"] for scene in group])
            unavoidable += len(group) - max(counts.values())
            missed_when_safe += sum(bool(scene["expected"]) for scene in group)
    return {"fields": fields, "observation_classes": len(groups), "conflicts": conflicts,
            "minimum_errors": unavoidable,
            "minimum_missed_approvals_with_zero_wrong_registrations": missed_when_safe}


def main():
    scenes = json.loads((ROOT / "scenes.json").read_text(encoding="utf-8"))
    by_id = {scene["id"]: scene for scene in scenes}
    results = [verify(scenes, fields) for size in range(len(FIELDS) + 1)
               for fields in combinations(FIELDS, size)]
    pairs = {"speaker": ("01", "03"), "recipient": ("01", "04"), "question": ("07", "08")}
    for missing, (left, right) in pairs.items():
        matched = any({left, right} <= {scene["id"] for scene in group}
                      for group in group_scenes(scenes, [field for field in FIELDS if field != missing]))
        assert matched and expected_output(by_id[left]) != expected_output(by_id[right])

    feasible = [result for result in results if result["minimum_errors"] == 0]
    assert len(feasible) == 1 and feasible[0]["fields"] == FIELDS
    assert all(evaluate(scene, "all")["correct"] for scene in scenes)
    print(json.dumps({"scenes": len(scenes), "subsets": results, "witness_pairs": pairs,
                      "minimum_fields_in_this_experiment": len(feasible[0]["fields"])},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
