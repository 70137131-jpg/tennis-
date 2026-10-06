import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "evaluation", Path(__file__).resolve().parents[1] / "eval/evaluate.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_evaluation_penalizes_false_and_missed_shots(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "shots": [
                    {"type": "forehand", "contact": 1.1, "player_id": "p"},
                    {"type": "serve", "contact": 5, "player_id": "p"},
                ]
            }
        )
    )
    text = module.evaluate(
        [
            {
                "report": str(report),
                "shots": [
                    {"type": "forehand", "contact": 1, "player_id": "p"},
                    {"type": "backhand", "contact": 3, "player_id": "p"},
                ],
            }
        ]
    )
    assert "Missed shots: 1" in text and "False shots: 1" in text
    assert "Macro F1 across represented classes: 0.500" in text


def test_demo_is_excluded_from_accuracy(tmp_path):
    report = tmp_path / "report.json"
    report.write_text('{"is_demo":true}')
    with pytest.raises(ValueError, match="Synthetic"):
        module.evaluate([{"report": str(report), "shots": []}])
