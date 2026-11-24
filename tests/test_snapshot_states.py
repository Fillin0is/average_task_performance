"""Read-only MySQL integration tests for the actual dataset query.

Run with RUN_MYSQL_TESTS=1. Fixture CTEs shadow source tables inside the
statement; no tables or records are created or modified in the database.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_TESTS") != "1", reason="Requires local MySQL"
)


def fixture_cte(name, rows, parameters):
    selects = []
    for index, row in enumerate(rows):
        fields = []
        for column, value in row.items():
            key = f"{name}_{index}_{column}"
            parameters[key] = value
            fields.append(f":{key} AS `{column}`")
        selects.append("SELECT " + ", ".join(fields))
    return f"{name} AS (" + " UNION ALL ".join(selects) + ")"


@pytest.fixture(scope="module")
def snapshots():
    from data_access.connection import database_url

    base = dict(
        ID=1, Project_ID=1, Creator_ID=10, Reporter_ID=10,
        Assignee_ID=99, Sprint_ID=1, Creation_Date="2020-01-01 00:00:00",
        Resolution_Date="2020-01-06 00:00:00", Estimation_Date=None,
        Title="Example", Description="Final description", Description_Text="Text", Description_Code=None,
        Type="Bug", Priority="Critical", Status="Closed", Story_Point=None,
        Pull_Request_URL=None, Title_Changed_After_Estimation=0,
        Description_Changed_After_Estimation=0,
        Story_Point_Changed_After_Estimation=0,
    )
    issues = [dict(base, ID=i) for i in range(1, 7)]
    issues[3]["Resolution_Date"] = "2020-01-02 00:00:00"
    issues[4]["Resolution_Date"] = "2020-01-01 00:05:00"
    changes = []

    def change(id_, issue, field, date, before, after, raw_before=None, raw_after=None):
        changes.append(dict(
            ID=id_, Issue_ID=issue, Field=field, Creation_Date=date,
            From_String=before, To_String=after,
            From_Value=raw_before, To_Value=raw_after,
        ))

    # Changes exactly on the checkpoint are included. At equal timestamps,
    # highest ID wins for past changes; lowest ID wins for future changes.
    change(1, 1, " Priority ", "2020-01-02 00:00:00", "Minor", "Major")
    change(2, 1, "priority", "2020-01-02 00:00:00", "Major", "Critical")
    change(3, 1, "assignee", "2020-01-02 06:00:00", None, "Person", None, "42")
    change(4, 1, "assignee", "2020-01-03 00:00:00", "Person", None, "42", None)
    change(5, 1, "sprint", "2020-01-02 06:00:00", None, "S1, S2", None, "103, 106")
    change(6, 1, "issuetype", "2020-01-02 06:00:00", "Task", "Bug")
    change(7, 1, "status", "2020-01-01 00:00:00", "New", "Open")
    change(8, 1, "status", "2020-01-02 12:00:00", "Open", "In Progress")
    # A future record may reconstruct the initial value, including NULL.
    change(9, 2, "priority", "2020-01-07 00:00:00", None, "Critical")
    # Invalid historical date must not be replaced with the stored value.
    change(10, 6, "status", "2019-12-31 00:00:00", "New", "Open")
    change(11, 1, "summary", "2020-01-02 06:00:00", "Old", "New title")
    change(12, 1, "description", "2020-01-02 06:00:00", None, "New description")
    change(13, 1, "story points", "2020-01-02 00:00:00", None, "3")
    change(14, 1, "story points", "2020-01-03 00:00:00", "3", "8")
    change(15, 2, "story points", "2020-01-01 10:00:00", None, "not a number")
    comments = [
        dict(ID=1, Issue_ID=1, Creation_Date="2020-01-01 12:00:00", Comment="abc"),
        dict(ID=2, Issue_ID=1, Creation_Date="2020-01-02 00:00:00", Comment="abcde"),
        dict(ID=3, Issue_ID=1, Creation_Date="2020-01-05 00:00:00", Comment="Future"),
    ]

    parameters = {}
    fixtures = [
        fixture_cte("Issue", issues, parameters),
        fixture_cte("Change_Log", changes, parameters),
        fixture_cte("Comment", comments, parameters),
        fixture_cte("Project", [dict(ID=1, Description="Project")], parameters),
        fixture_cte("Sprint", [dict(ID=1, JiraID=108)], parameters),
    ]
    path = Path(__file__).resolve().parents[1] / "data_access/queries/snapshot_training_dataset.sql"
    sql = path.read_text(encoding="utf-8")
    sql = sql.replace("WITH eligible_issues AS (", "WITH " + ",\n".join(fixtures) + ",\neligible_issues AS (", 1)
    engine = create_engine(database_url, connect_args={"connect_timeout": 5, "read_timeout": 30})
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(sql), parameters).mappings().all()
        result = {(r["Issue_ID"], r["Snapshot_Type"]): r for r in rows}
        assert len(rows) == len(result), "Duplicate snapshots"
        return result
    finally:
        engine.dispose()


def test_checkpoint_and_same_timestamp_order(snapshots):
    assert snapshots[1, "created"]["Priority_At_Snapshot"] == "Minor"
    row = snapshots[1, "24h"]
    assert row["Priority_At_Snapshot"] == "Critical"
    assert row["Priority_Change_ID"] == 2
    assert row["Priority_Source"] == "last_change_before"


def test_null_is_state_not_fallback(snapshots):
    assert snapshots[2, "created"]["Priority_At_Snapshot"] is None
    assert snapshots[2, "created"]["Priority_Source"] == "first_change_after"
    assert snapshots[1, "created"]["Has_Assignee_At_Snapshot"] == 0
    assert snapshots[1, "72h"]["Has_Assignee_At_Snapshot"] == 0


def test_sprint_list_and_key_domain(snapshots):
    assert snapshots[1, "72h"]["Sprint_At_Snapshot"] == "103, 106"
    assert snapshots[1, "created"]["Has_Sprint_At_Snapshot"] == 0
    assert snapshots[3, "created"]["Sprint_At_Snapshot"] == "108"
    assert snapshots[3, "created"]["Sprint_Key_Source"] == "sprint_jira_id"


def test_type_and_status(snapshots):
    assert snapshots[1, "24h"]["Type_At_Snapshot"] == "Task"
    assert snapshots[1, "72h"]["Type_At_Snapshot"] == "Bug"
    assert snapshots[1, "created"]["Status_At_Snapshot"] == "Open"
    assert snapshots[1, "72h"]["Status_At_Snapshot"] == "In Progress"


def test_stored_fallback_only_without_history(snapshots):
    row = snapshots[3, "created"]
    assert row["Priority_At_Snapshot"] == "Critical"
    assert row["Priority_Source"] == "stored_no_history"
    assert row["Assignee_At_Snapshot"] == "99"
    assert row["Assignee_Key_Source"] == "tawos_user_id"


def test_invalid_history_is_visible(snapshots):
    assert snapshots[6, "created"]["Status_At_Snapshot"] is None
    assert snapshots[6, "created"]["Status_Source"] == "invalid_history"


def test_snapshot_boundaries(snapshots):
    assert (4, "created") in snapshots
    assert (4, "24h") not in snapshots
    assert not any(key[0] == 5 for key in snapshots)
    for row in snapshots.values():
        assert row["Remaining_Duration_Hours"] > 0


def test_text_lengths_follow_history(snapshots):
    assert snapshots[1, "created"]["Title_Length_At_Snapshot"] == 3
    assert snapshots[1, "72h"]["Title_Length_At_Snapshot"] == 9
    assert snapshots[1, "created"]["Description_Length_At_Snapshot"] == 0
    assert snapshots[1, "72h"]["Description_Length_At_Snapshot"] == 15


def test_story_points_follow_history_not_current_estimate(snapshots):
    assert snapshots[1, "created"]["Story_Point_At_Snapshot"] is None
    assert snapshots[1, "24h"]["Story_Point_At_Snapshot"] == 3
    assert snapshots[1, "72h"]["Story_Point_At_Snapshot"] == 8
    assert snapshots[2, "24h"]["Story_Point_At_Snapshot"] is None


def test_activity_cutoff_and_no_join_multiplication(snapshots):
    row = snapshots[1, "24h"]
    assert row["Comment_Count"] == 2
    assert row["Stored_Comment_Total_Length"] == 8
    assert row["Change_Count"] == 4  # status + two priorities + estimate
    assert row["Hours_Since_Last_Comment"] == 0
    assert row["Hours_Since_Last_Status_Change"] == 24
    assert snapshots[1, "created"]["Comment_Count"] == 0
    assert snapshots[1, "created"]["Hours_Since_Last_Comment"] is None
    assert snapshots[1, "72h"]["Comment_Count"] == 2
