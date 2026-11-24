import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_access.snapshot_dataset import (
    CATEGORICAL_FEATURES, CLASS_COLUMN, FEATURE_COLUMNS, NUMERIC_FEATURES,
    TARGET_COLUMN, assign_chronological_splits, duration_classes, model_inputs,
    normalize_priority, normalize_type, prepare_snapshot_dataset,
    validate_snapshot_dataset,
)


def test_priority_matches_notebook_05_exactly():
    path = Path(__file__).resolve().parents[1] / "data_access/notebooks/05_slice_2010_2020_baseline.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    source = next("".join(c["source"]) for c in notebook["cells"]
                  if 'issue_df["Initial_Priority"].replace({' in "".join(c.get("source", [])))
    mapping = next(ast.literal_eval(n) for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Dict))
    assert normalize_priority(pd.Series(mapping.keys())).tolist() == list(mapping.values())


def test_category_cleanup_does_not_guess_unknown_semantics():
    values = pd.Series([None, " critical-P2 ", "  to BE   reviewed ", "Urgent"])
    assert normalize_priority(values).tolist() == ["Unassigned", "P2", "Unassigned", "Urgent"]
    types = pd.Series([" BUG ", "subtask", "Technical   Task", "Improvement", "New Feature", None])
    assert normalize_type(types).tolist() == ["Bug", "Sub-task", "Technical task", "Improvement", "New Feature", "Unknown"]


def test_duration_classes_no_boundary_overlap():
    values = pd.Series([.001, 24, 24.001, 168, 168.001, 720, 720.001, 8760])
    assert duration_classes(values).tolist() == ["0-1d", "0-1d", "1-7d", "1-7d", "7-30d", "7-30d", "30-365d", "30-365d"]


@pytest.mark.parametrize("value", [0, -1, 8761, np.nan, np.inf])
def test_invalid_target_rejected(value):
    with pytest.raises(ValueError):
        duration_classes(pd.Series([value]))


def example_dataset():
    row = {name: 0 for name in NUMERIC_FEATURES}
    row.update({
        "Issue_ID": 1, "Project_ID": 1, "Creation_Date": "2020-01-01",
        "Resolution_Date": "2020-01-03", "Snapshot_Date": "2020-01-01",
        "Snapshot_Type": "created", TARGET_COLUMN: 48,
        "Priority_At_Snapshot": "Major", "Type_At_Snapshot": "bug",
        "Status_At_Snapshot": "Open", "Stored_Status": "Closed",
        "Status_Source": "first_change_after", "Story_Point_At_Snapshot": None,
        "Hours_Since_Last_Comment": None,
    })
    return prepare_snapshot_dataset(pd.DataFrame([row]))


def test_model_allowlist_excludes_future_and_audit_columns():
    frame = example_dataset()
    validate_snapshot_dataset(frame)
    x, y, classes = model_inputs(frame)
    assert list(x.columns) == FEATURE_COLUMNS
    assert all(not c.startswith(("Stored_", "Raw_")) for c in x)
    assert not {TARGET_COLUMN, CLASS_COLUMN, "Issue_ID", "Resolution_Date", "Status_Source"}.intersection(x)
    assert all(isinstance(x.iloc[0][c], str) for c in CATEGORICAL_FEATURES)
    assert y.iloc[0] == 48
    assert classes.iloc[0] == "1-7d"


def test_validation_rejects_duplicate_and_inconsistent_rows():
    frame = example_dataset()
    with pytest.raises(ValueError, match="Duplicate"):
        validate_snapshot_dataset(pd.concat([frame, frame]))
    frame["Snapshot_Date"] += pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="timestamp"):
        validate_snapshot_dataset(frame)


def test_temporal_split_groups_issues_and_purges_future_labels():
    dates = pd.date_range("2020-01-01", periods=20, freq="D")
    issues = pd.DataFrame({"Issue_ID": range(20), "Creation_Date": dates,
                           "Resolution_Date": dates + pd.Timedelta(hours=3)})
    issues.loc[0, "Resolution_Date"] = dates[15]  # unavailable at validation start
    issues.loc[14, "Resolution_Date"] = dates[18]  # unavailable at test start
    frame = pd.concat([issues.assign(Snapshot_Type="created"), issues.assign(Snapshot_Type="24h")])
    result = assign_chronological_splits(frame)
    assert result.groupby("Issue_ID")["Split"].nunique().eq(1).all()
    assert result.loc[result.Issue_ID.eq(0), "Split"].eq("excluded_train_overlap").all()
    assert result.loc[result.Issue_ID.eq(14), "Split"].eq("excluded_validation_overlap").all()
    assert result.loc[result.Split.eq("train"), "Resolution_Date"].lt(dates[14]).all()
    assert result.loc[result.Split.eq("validation"), "Resolution_Date"].lt(dates[17]).all()


def test_creation_date_ties_are_not_split():
    dates = pd.to_datetime(["2020-01-01"] * 7 + ["2020-01-02"] * 8 + ["2020-01-03"] * 2 + ["2020-01-04"] * 3)
    frame = pd.DataFrame({"Issue_ID": range(20), "Creation_Date": dates,
                          "Resolution_Date": dates + pd.Timedelta(hours=1)})
    result = assign_chronological_splits(frame)
    assert result.groupby("Creation_Date")["Split"].nunique().eq(1).all()
