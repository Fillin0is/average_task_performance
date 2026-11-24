"""Prepare checkpoint datasets; no model training or database writes.

SQL reconstructs history. This module normalizes categories, defines the
model input contract, creates class labels and chronological splits.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from data_access.config import project_path


TARGET_COLUMN = "Remaining_Duration_Hours"
CLASS_COLUMN = "Duration_Class"
CLASS_LABELS = ["0-1d", "1-7d", "7-30d", "30-365d"]
CLASS_EDGES_HOURS = [0, 24, 168, 720, 8760]

# Same semantic mapping as notebook 05. Only whitespace/case handling added.
PRIORITY_GROUPS = {
    "Unassigned": ["", "None", "To be reviewed", "Unknown", "Undefined", "Unassigned"],
    "P5": ["P5", "Trivial", "Trivial - P5", "Lowest"],
    "P4": ["P4", "Minor", "Minor - P4", "Low"],
    "P3": ["P3", "Major", "Major - P3", "Medium"],
    "P2": ["P2", "Critical", "Critical - P2", "High"],
    "P1": ["P1", "Blocker", "Blocker - P1", "Highest"],
}
PRIORITY_MAP = {
    alias.casefold(): canonical
    for canonical, aliases in PRIORITY_GROUPS.items() for alias in aliases
}

# Do not collapse genuinely different types or learn rare-category cutoffs
# on the full dataset. These are spelling aliases, not class balancing.
TYPE_NAMES = [
    "Bug", "Build Failure", "Documentation", "Enhancement Request", "Epic",
    "Improvement", "Incident", "Investigation", "Milestone", "New Feature",
    "Problem Ticket", "Public Security Vulnerability", "Question", "Release",
    "Story", "Sub-task", "Suggestion", "Support Request", "Task",
    "Technical Debt", "Technical task", "Test", "Test Task", "Wish",
]
TYPE_MAP = {name.casefold(): name for name in TYPE_NAMES}
TYPE_MAP.update({
    "subtask": "Sub-task", "sub task": "Sub-task",
    "technical-task": "Technical task", "test-task": "Test Task",
    "": "Unknown", "none": "Unknown", "undefined": "Unknown", "unknown": "Unknown",
})

CATEGORICAL_FEATURES = [
    "Project_ID", "Priority_At_Snapshot", "Type_At_Snapshot", "Status_At_Snapshot",
]
NUMERIC_FEATURES = [
    "Age_Hours", "Creation_Year", "Creation_Month", "Creation_Day_Of_Week",
    "Creation_Hour", "Created_On_Weekend", "Created_Friday_Evening",
    "Snapshot_Month", "Snapshot_Day_Of_Week", "Snapshot_Hour",
    "Title_Length_At_Snapshot", "Description_Length_At_Snapshot",
    "Has_Description_At_Snapshot", "Story_Point_At_Snapshot", "Has_Story_Point",
    "Has_Assignee_At_Snapshot", "Has_Sprint_At_Snapshot",
    "Comment_Count", "Change_Count", "Status_Change_Count", "Priority_Change_Count",
    "Assignee_Change_Count", "Description_Change_Count", "Story_Point_Change_Count",
    "Sprint_Change_Count", "Hours_Since_Last_Change",
    "Hours_Since_Last_Status_Change", "Hours_Since_Last_Comment",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
METADATA_COLUMNS = [
    "Issue_ID", "Creation_Date", "Resolution_Date", "Snapshot_Type", "Snapshot_Date",
]


def clean_category(values):
    return values.astype("string").fillna("").str.strip().str.replace(r"\s+", " ", regex=True)


def normalize_priority(values):
    clean = clean_category(values).str.replace(r"\s*-\s*", " - ", regex=True)
    # Unrecognized priorities remain visible rather than silently becoming P3.
    return clean.str.casefold().map(PRIORITY_MAP).fillna(clean)


def normalize_type(values):
    clean = clean_category(values).str.replace(r"\s*-\s*", "-", regex=True)
    return clean.str.casefold().map(TYPE_MAP).fillna(clean)


def duration_classes(values):
    target = pd.to_numeric(values, errors="raise")
    if not (np.isfinite(target) & target.gt(0) & target.le(8760)).all():
        raise ValueError("Remaining duration must be finite and in (0, 8760] hours")
    return pd.cut(target, CLASS_EDGES_HOURS, labels=CLASS_LABELS, right=True)


def prepare_snapshot_dataset(frame):
    result = frame.copy()
    for name in ("Priority", "Type", "Status"):
        result[f"Raw_{name}_At_Snapshot"] = result[f"{name}_At_Snapshot"]
    result["Priority_At_Snapshot"] = normalize_priority(result["Priority_At_Snapshot"])
    result["Type_At_Snapshot"] = normalize_type(result["Type_At_Snapshot"])
    status = clean_category(result["Status_At_Snapshot"]).str.casefold()
    result["Status_At_Snapshot"] = status.replace("", "unknown")
    for name in NUMERIC_FEATURES + [TARGET_COLUMN]:
        result[name] = pd.to_numeric(result[name], errors="raise").astype(float)
    for name in ("Creation_Date", "Resolution_Date", "Snapshot_Date"):
        result[name] = pd.to_datetime(result[name], errors="raise")
    result[CLASS_COLUMN] = duration_classes(result[TARGET_COLUMN])
    return result


def validate_snapshot_dataset(frame):
    if frame.empty:
        raise ValueError("Empty snapshot dataset")
    if frame.duplicated(["Issue_ID", "Snapshot_Type"]).any():
        raise ValueError("Duplicate issue/checkpoint")
    expected_age = frame["Snapshot_Type"].map({"created": 0, "24h": 24, "72h": 72})
    if expected_age.isna().any():
        raise ValueError("Unknown checkpoint")
    expected_date = frame["Creation_Date"] + pd.to_timedelta(expected_age, unit="h")
    if not frame["Snapshot_Date"].eq(expected_date).all():
        raise ValueError("Checkpoint timestamp differs from the expected age")
    if not frame["Age_Hours"].eq(expected_age).all():
        raise ValueError("Age_Hours differs from checkpoint")
    remaining = (frame["Resolution_Date"] - frame["Snapshot_Date"]).dt.total_seconds() / 3600
    if not np.allclose(frame[TARGET_COLUMN], remaining, rtol=0, atol=0.0001):
        raise ValueError("Target differs from resolution minus snapshot")
    duration_classes(frame[TARGET_COLUMN])
    if not frame[CLASS_COLUMN].equals(duration_classes(frame[TARGET_COLUMN])):
        raise ValueError("Class label differs from duration")
    for name in ("Hours_Since_Last_Change", "Hours_Since_Last_Comment", "Hours_Since_Last_Status_Change"):
        valid = frame[name].isna() | frame[name].between(0, frame["Age_Hours"])
        if not valid.all():
            raise ValueError(f"Invalid event recency: {name}")


def assign_chronological_splits(frame):
    """70/15/15 by issue creation, then purge unavailable historical labels.

    Whole tasks stay together. Boundary-timestamp ties stay together too.
    Excluded overlap rows are retained and labeled explicitly for audit.
    """
    result = frame.copy()
    issues = result[["Issue_ID", "Creation_Date", "Resolution_Date"]].drop_duplicates()
    if issues["Issue_ID"].duplicated().any():
        raise ValueError("Issue dates differ between snapshots")
    issues = issues.sort_values(["Creation_Date", "Issue_ID"])
    if len(issues) < 10:
        raise ValueError("At least 10 issues required for three temporal partitions")
    val_start = issues.iloc[int(len(issues) * .70)]["Creation_Date"]
    test_start = issues.iloc[int(len(issues) * .85)]["Creation_Date"]
    if not issues["Creation_Date"].min() < val_start < test_start:
        raise ValueError("Not enough distinct dates for three temporal partitions")
    issues["Split"] = "test"
    issues.loc[issues["Creation_Date"] < test_start, "Split"] = "validation"
    issues.loc[issues["Creation_Date"] < val_start, "Split"] = "train"
    train_overlap = issues["Split"].eq("train") & issues["Resolution_Date"].ge(val_start)
    val_overlap = issues["Split"].eq("validation") & issues["Resolution_Date"].ge(test_start)
    issues.loc[train_overlap, "Split"] = "excluded_train_overlap"
    issues.loc[val_overlap, "Split"] = "excluded_validation_overlap"
    result["Split"] = result["Issue_ID"].map(issues.set_index("Issue_ID")["Split"])
    result.attrs["split_boundaries"] = {"validation_start": str(val_start), "test_start": str(test_start)}
    return result


def model_inputs(frame):
    """Explicit allowlist: no stored values, future-derived audit flags or IDs."""
    features = frame[FEATURE_COLUMNS].copy()
    for name in CATEGORICAL_FEATURES:
        features[name] = features[name].astype("string").fillna("Unknown").astype(str)
    return features, frame[TARGET_COLUMN].copy(), frame[CLASS_COLUMN].copy()


def load_snapshot_dataset(connection):
    sql = project_path.query("snapshot_training_dataset.sql").read_text(encoding="utf-8").rstrip().rstrip(";")
    columns = METADATA_COLUMNS + FEATURE_COLUMNS + [TARGET_COLUMN]
    # Select only the model contract + metadata, not all wide diagnostic fields.
    query = text("SELECT " + ", ".join(f"d.`{c}`" for c in columns) + " FROM (" + sql + ") AS d")
    chunks = [prepare_snapshot_dataset(chunk) for chunk in pd.read_sql_query(query, connection, chunksize=50000)]
    if not chunks:
        raise ValueError("SQL returned no snapshots")
    result = pd.concat(chunks, ignore_index=True)
    validate_snapshot_dataset(result)
    return assign_chronological_splits(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional CSV or CSV.gz output")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output already exists; choose a new path to preserve the previous dataset")
    from data_access.connection import engine

    print("Loading and validating snapshots...", flush=True)
    frame = load_snapshot_dataset(engine)
    print("Rows:", len(frame), "Features:", len(FEATURE_COLUMNS))
    print("Split boundaries:", frame.attrs["split_boundaries"])
    print(frame.groupby(["Split", "Snapshot_Type"]).size().unstack(fill_value=0))
    print(pd.crosstab(frame["Snapshot_Type"], frame[CLASS_COLUMN]))
    print("Priorities:", frame["Priority_At_Snapshot"].value_counts().to_dict())
    print("Types:", frame["Type_At_Snapshot"].value_counts().to_dict())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False)
        print("Saved:", args.output.resolve())


if __name__ == "__main__":
    main()
