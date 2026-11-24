"""Small read-only MySQL check for the first transition query."""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from data_access.connection import database_url

pytestmark = pytest.mark.skipif(os.getenv("RUN_MYSQL_TESTS") != "1", reason="Requires local MySQL")


def test_first_transition_and_remaining_time():
    fixtures = """
    Issue AS (
      SELECT 1 ID, 1 Project_ID, NULL Creator_ID, NULL Reporter_ID,
        NULL Assignee_ID, NULL Sprint_ID, CAST('2020-01-01' AS DATETIME) Creation_Date,
        CAST('2020-01-06' AS DATETIME) Resolution_Date, NULL Estimation_Date,
        'Title' Title, 'Description' Description, '' Description_Text, '' Description_Code,
        'Bug' Type, 'Major' Priority, 'Closed' Status, NULL Story_Point, NULL Pull_Request_URL,
        0 Title_Changed_After_Estimation, 0 Description_Changed_After_Estimation,
        0 Story_Point_Changed_After_Estimation
    ),
    Change_Log AS (
      SELECT 1 ID, 1 Issue_ID, 'status' Field, CAST('2020-01-03' AS DATETIME) Creation_Date,
        'Open' From_String, 'In Progress' To_String, NULL From_Value, NULL To_Value
      UNION ALL
      SELECT 2, 1, 'status', CAST('2020-01-04' AS DATETIME),
        'Open', 'In Progress', NULL, NULL
    ),
    Project AS (SELECT 1 ID, '' Description),
    Sprint AS (SELECT 1 ID, 1 JiraID),
    Comment AS (SELECT 1 ID, 999 Issue_ID, CAST('2020-01-01' AS DATETIME) Creation_Date, '' Comment)
    """
    path = Path(__file__).resolve().parents[1] / "data_access/queries/in_progress_training_dataset.sql"
    sql = path.read_text(encoding="utf-8").replace(
        "WITH eligible_issues AS (", "WITH " + fixtures + ", eligible_issues AS (", 1
    )
    engine = create_engine(database_url, connect_args={"connect_timeout": 5, "read_timeout": 30})
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(sql)).mappings().all()
        assert len(rows) == 1
        assert str(rows[0]["Snapshot_Date"]) == "2020-01-03 00:00:00"
        assert float(rows[0]["Remaining_Duration_Hours"]) == 72
        assert rows[0]["Snapshot_Type"] == "in_progress"
    finally:
        engine.dispose()
