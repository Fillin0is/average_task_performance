WITH eligible_issues AS (
    SELECT
        i.ID,
        i.Project_ID,
        i.Creator_ID,
        i.Reporter_ID,
        i.Assignee_ID,
        i.Sprint_ID,
        i.Creation_Date,
        i.Resolution_Date,
        i.Estimation_Date,
        i.Title,
        i.Description_Text,
        i.Description_Code,
        CHAR_LENGTH(COALESCE(i.Description, '')) AS Stored_Description_Length,
        i.Type,
        i.Priority,
        i.Status,
        i.Story_Point,
        i.Pull_Request_URL,
        i.Title_Changed_After_Estimation,
        i.Description_Changed_After_Estimation,
        i.Story_Point_Changed_After_Estimation
    FROM Issue AS i
    WHERE i.Resolution_Date > DATE_ADD(
            i.Creation_Date,
            INTERVAL 5 MINUTE
        )
        AND i.Resolution_Date <= DATE_ADD(
            i.Creation_Date,
            INTERVAL 365 DAY
        )
        AND i.Creation_Date >= '2004-01-01'
),
snapshots AS (
    SELECT
        ei.*,
        'created' AS Snapshot_Type,
        ei.Creation_Date AS Snapshot_Date,
        0 AS Age_Hours,
        TIMESTAMPDIFF(
            SECOND,
            ei.Creation_Date,
            ei.Resolution_Date
        ) / 3600.0 AS Remaining_Duration_Hours
    FROM eligible_issues AS ei

    UNION ALL

    SELECT
        ei.*,
        '24h' AS Snapshot_Type,
        DATE_ADD(
            ei.Creation_Date,
            INTERVAL 24 HOUR
        ) AS Snapshot_Date,
        24 AS Age_Hours,
        TIMESTAMPDIFF(
            SECOND,
            DATE_ADD(ei.Creation_Date, INTERVAL 24 HOUR),
            ei.Resolution_Date
        ) / 3600.0 AS Remaining_Duration_Hours
    FROM eligible_issues AS ei
    WHERE ei.Resolution_Date > DATE_ADD(
        ei.Creation_Date,
        INTERVAL 24 HOUR
    )

    UNION ALL

    SELECT
        ei.*,
        '72h' AS Snapshot_Type,
        DATE_ADD(
            ei.Creation_Date,
            INTERVAL 72 HOUR
        ) AS Snapshot_Date,
        72 AS Age_Hours,
        TIMESTAMPDIFF(
            SECOND,
            DATE_ADD(ei.Creation_Date, INTERVAL 72 HOUR),
            ei.Resolution_Date
        ) / 3600.0 AS Remaining_Duration_Hours
    FROM eligible_issues AS ei
    WHERE ei.Resolution_Date > DATE_ADD(
        ei.Creation_Date,
        INTERVAL 72 HOUR
    )
),
static_features AS (
    SELECT
        s.ID AS Issue_ID,
        s.Project_ID,
        s.Creator_ID,
        s.Reporter_ID,
        s.Assignee_ID AS Stored_Assignee_ID,
        s.Sprint_ID AS Stored_Sprint_ID,
        s.Creation_Date,
        s.Resolution_Date,
        s.Estimation_Date,
        s.Snapshot_Type,
        s.Snapshot_Date,
        s.Age_Hours,
        s.Remaining_Duration_Hours,

        -- These are the values stored in the final Issue row. They are kept
        -- for audit and later state reconstruction, not as snapshot features.
        s.Type AS Stored_Type,
        s.Priority AS Stored_Priority,
        s.Status AS Stored_Status,
        s.Story_Point AS Stored_Story_Point,
        s.Story_Point_Changed_After_Estimation,
        s.Stored_Description_Length,

        -- Audit-only until text history is restored: these lengths describe
        -- the stored texts, not necessarily the texts at Snapshot_Date.
        CHAR_LENGTH(COALESCE(s.Title, '')) AS Title_Length,
        CHAR_LENGTH(
            COALESCE(s.Description_Text, '')
        ) AS Description_Text_Length,
        CHAR_LENGTH(
            COALESCE(s.Description_Code, '')
        ) AS Description_Code_Length,
        CHAR_LENGTH(
            COALESCE(p.Description, '')
        ) AS Project_Description_Length,

        CASE
            WHEN NULLIF(TRIM(s.Description_Text), '') IS NOT NULL
                THEN 1
            ELSE 0
        END AS Has_Description,
        CASE
            WHEN NULLIF(TRIM(s.Description_Code), '') IS NOT NULL
                THEN 1
            ELSE 0
        END AS Has_Code,
        CASE
            WHEN NULLIF(TRIM(s.Pull_Request_URL), '') IS NOT NULL
                THEN 1
            ELSE 0
        END AS Stored_Has_Pull_Request,

        CASE
            WHEN s.Creator_ID IS NOT NULL
                AND s.Reporter_ID IS NOT NULL
                AND s.Creator_ID = s.Reporter_ID
                THEN 1
            ELSE 0
        END AS Creator_Equals_Reporter,

        YEAR(s.Creation_Date) AS Creation_Year,
        MONTH(s.Creation_Date) AS Creation_Month,
        WEEKDAY(s.Creation_Date) AS Creation_Day_Of_Week,
        HOUR(s.Creation_Date) AS Creation_Hour,
        CASE
            WHEN WEEKDAY(s.Creation_Date) IN (5, 6)
                THEN 1
            ELSE 0
        END AS Created_On_Weekend,
        CASE
            WHEN WEEKDAY(s.Creation_Date) = 4
                AND HOUR(s.Creation_Date) >= 18
                THEN 1
            ELSE 0
        END AS Created_Friday_Evening
    FROM snapshots AS s
    LEFT JOIN Project AS p
        ON p.ID = s.Project_ID
),
estimation_features AS (
    SELECT
        sf.*,
        CASE
            WHEN sf.Estimation_Date BETWEEN sf.Creation_Date AND sf.Snapshot_Date
                THEN TIMESTAMPDIFF(
                    SECOND,
                    sf.Creation_Date,
                    sf.Estimation_Date
                ) / 3600.0
            ELSE NULL
        END AS Hours_To_Estimation
    FROM static_features AS sf
),
state_changes AS (
    -- Keep history after Snapshot_Date too: the earliest later From_String
    -- can describe the state before the first recorded change.
    SELECT
        cl.ID AS Change_ID,
        cl.Issue_ID,
        LOWER(TRIM(cl.Field)) AS Field_Name,
        cl.Creation_Date AS Changed_At,
        -- Text histories are reduced to lengths BEFORE window sorting.
        -- We reconstruct the raw description, not its later Text/Code split.
        CASE WHEN LOWER(TRIM(cl.Field)) IN ('summary', 'description')
             THEN CAST(CHAR_LENGTH(COALESCE(cl.From_String, '')) AS CHAR)
             ELSE cl.From_String END AS From_String,
        CASE WHEN LOWER(TRIM(cl.Field)) IN ('summary', 'description')
             THEN CAST(CHAR_LENGTH(COALESCE(cl.To_String, '')) AS CHAR)
             ELSE cl.To_String END AS To_String,
        cl.From_Value,
        cl.To_Value
    FROM Change_Log AS cl
    JOIN eligible_issues AS ei ON ei.ID = cl.Issue_ID
    WHERE LOWER(TRIM(cl.Field)) IN (
        'priority', 'issuetype', 'status', 'assignee', 'sprint',
        'summary', 'description', 'story points'
    )
),
ranked_state_changes AS (
    SELECT
        s.ID AS Issue_ID,
        s.Snapshot_Type,
        s.Snapshot_Date,
        s.Creation_Date,
        sc.Field_Name,
        sc.Change_ID,
        sc.Changed_At,
        sc.From_String,
        sc.To_String,
        sc.From_Value,
        sc.To_Value,
        ROW_NUMBER() OVER (
            PARTITION BY s.ID, s.Snapshot_Type, sc.Field_Name
            ORDER BY
                CASE WHEN sc.Changed_At <= s.Snapshot_Date THEN 0
                     WHEN sc.Changed_At > s.Snapshot_Date THEN 1
                     ELSE 2 END,
                CASE WHEN sc.Changed_At <= s.Snapshot_Date
                     THEN sc.Changed_At END DESC,
                CASE WHEN sc.Changed_At <= s.Snapshot_Date
                     THEN sc.Change_ID END DESC,
                CASE WHEN sc.Changed_At > s.Snapshot_Date
                     THEN sc.Changed_At END ASC,
                sc.Change_ID ASC
        ) AS Change_Rank
    FROM snapshots AS s
    JOIN state_changes AS sc ON sc.Issue_ID = s.ID
),
selected_state_changes AS (
    SELECT
        Issue_ID,
        Snapshot_Type,
        Field_Name,
        Change_ID,
        CASE
            WHEN Changed_At IS NULL OR Changed_At < Creation_Date
                THEN 'invalid_history'
            WHEN Changed_At <= Snapshot_Date THEN 'last_change_before'
            ELSE 'first_change_after'
        END AS Value_Source,
        CASE
            WHEN Changed_At IS NULL OR Changed_At < Creation_Date THEN NULL
            WHEN Changed_At <= Snapshot_Date THEN To_String
            ELSE From_String
        END AS State_String,
        CASE
            WHEN Changed_At IS NULL OR Changed_At < Creation_Date THEN NULL
            WHEN Changed_At <= Snapshot_Date THEN To_Value
            ELSE From_Value
        END AS State_Value
    FROM ranked_state_changes
    WHERE Change_Rank = 1
),
snapshot_states AS (
    SELECT
        sf.*,
        -- Check the presence of the change row, NOT whether its value is NULL.
        -- A NULL/empty From_String can mean the field had not been assigned.
        CASE WHEN pc.Change_ID IS NOT NULL THEN pc.State_String
             ELSE sf.Stored_Priority END AS Priority_At_Snapshot,
        CASE WHEN tc.Change_ID IS NOT NULL THEN tc.State_String
             ELSE sf.Stored_Type END AS Type_At_Snapshot,
        CASE WHEN stc.Change_ID IS NOT NULL THEN stc.State_String
             ELSE sf.Stored_Status END AS Status_At_Snapshot,
        CASE WHEN title_change.Change_ID IS NOT NULL
                 THEN CAST(title_change.State_String AS UNSIGNED)
             ELSE sf.Title_Length END AS Title_Length_At_Snapshot,
        CASE WHEN description_change.Change_ID IS NOT NULL
                 THEN CAST(description_change.State_String AS UNSIGNED)
             ELSE sf.Stored_Description_Length END AS Description_Length_At_Snapshot,
        CASE WHEN estimate_change.Change_ID IS NOT NULL
                 THEN estimate_change.State_String
             WHEN sf.Estimation_Date BETWEEN sf.Creation_Date AND sf.Snapshot_Date
                 THEN CAST(sf.Stored_Story_Point AS CHAR)
             ELSE NULL END AS Story_Point_Raw_At_Snapshot,
        CASE WHEN ac.Change_ID IS NOT NULL
                 THEN COALESCE(NULLIF(TRIM(ac.State_Value), ''),
                               NULLIF(TRIM(ac.State_String), ''))
             ELSE CAST(sf.Stored_Assignee_ID AS CHAR)
        END AS Assignee_At_Snapshot,
        -- Preserve multiple sprint IDs; never cast a list such as '103, 106'
        -- to a single number. Sprint.JiraID and Sprint.ID are different keys.
        CASE WHEN spc.Change_ID IS NOT NULL
                 THEN COALESCE(NULLIF(TRIM(spc.State_Value), ''),
                               NULLIF(TRIM(spc.State_String), ''))
             ELSE COALESCE(CAST(sp.JiraID AS CHAR),
                           CAST(sf.Stored_Sprint_ID AS CHAR))
        END AS Sprint_At_Snapshot,

        COALESCE(pc.Value_Source, 'stored_no_history') AS Priority_Source,
        COALESCE(tc.Value_Source, 'stored_no_history') AS Type_Source,
        COALESCE(stc.Value_Source, 'stored_no_history') AS Status_Source,
        COALESCE(ac.Value_Source, 'stored_no_history') AS Assignee_Source,
        COALESCE(spc.Value_Source, 'stored_no_history') AS Sprint_Source,
        COALESCE(title_change.Value_Source, 'stored_no_history') AS Title_Source,
        COALESCE(description_change.Value_Source, 'stored_no_history') AS Description_Source,
        COALESCE(estimate_change.Value_Source, 'stored_with_estimation_date') AS Story_Point_Source,
        pc.Change_ID AS Priority_Change_ID,
        tc.Change_ID AS Type_Change_ID,
        stc.Change_ID AS Status_Change_ID,
        ac.Change_ID AS Assignee_Change_ID,
        spc.Change_ID AS Sprint_Change_ID,
        title_change.Change_ID AS Title_Change_ID,
        description_change.Change_ID AS Description_Change_ID,
        estimate_change.Change_ID AS Story_Point_Change_ID,

        -- Diagnostic key domains: do not join arbitrary log keys to User.ID
        -- or Sprint.ID, or mix them as a single categorical model feature.
        CASE WHEN ac.Change_ID IS NULL THEN 'tawos_user_id'
             WHEN NULLIF(TRIM(ac.State_Value), '') IS NOT NULL THEN 'log_value'
             WHEN NULLIF(TRIM(ac.State_String), '') IS NOT NULL THEN 'log_string'
             ELSE 'missing' END AS Assignee_Key_Source,
        CASE WHEN spc.Change_ID IS NULL AND sp.JiraID IS NOT NULL THEN 'sprint_jira_id'
             WHEN spc.Change_ID IS NULL THEN 'tawos_sprint_id'
             WHEN NULLIF(TRIM(spc.State_Value), '') IS NOT NULL THEN 'log_value'
             WHEN NULLIF(TRIM(spc.State_String), '') IS NOT NULL THEN 'log_string'
             ELSE 'missing' END AS Sprint_Key_Source
    FROM estimation_features AS sf
    LEFT JOIN selected_state_changes AS pc
        ON pc.Issue_ID = sf.Issue_ID AND pc.Snapshot_Type = sf.Snapshot_Type
        AND pc.Field_Name = 'priority'
    LEFT JOIN selected_state_changes AS tc
        ON tc.Issue_ID = sf.Issue_ID AND tc.Snapshot_Type = sf.Snapshot_Type
        AND tc.Field_Name = 'issuetype'
    LEFT JOIN selected_state_changes AS stc
        ON stc.Issue_ID = sf.Issue_ID AND stc.Snapshot_Type = sf.Snapshot_Type
        AND stc.Field_Name = 'status'
    LEFT JOIN selected_state_changes AS ac
        ON ac.Issue_ID = sf.Issue_ID AND ac.Snapshot_Type = sf.Snapshot_Type
        AND ac.Field_Name = 'assignee'
    LEFT JOIN selected_state_changes AS spc
        ON spc.Issue_ID = sf.Issue_ID AND spc.Snapshot_Type = sf.Snapshot_Type
        AND spc.Field_Name = 'sprint'
    LEFT JOIN Sprint AS sp ON sp.ID = sf.Stored_Sprint_ID
    LEFT JOIN selected_state_changes AS title_change
        ON title_change.Issue_ID = sf.Issue_ID
        AND title_change.Snapshot_Type = sf.Snapshot_Type
        AND title_change.Field_Name = 'summary'
    LEFT JOIN selected_state_changes AS description_change
        ON description_change.Issue_ID = sf.Issue_ID
        AND description_change.Snapshot_Type = sf.Snapshot_Type
        AND description_change.Field_Name = 'description'
    LEFT JOIN selected_state_changes AS estimate_change
        ON estimate_change.Issue_ID = sf.Issue_ID
        AND estimate_change.Snapshot_Type = sf.Snapshot_Type
        AND estimate_change.Field_Name = 'story points'
),
change_activity AS (
    -- Separate aggregation prevents Comment x Change_Log row multiplication.
    SELECT
        s.ID AS Issue_ID,
        s.Snapshot_Type,
        COUNT(*) AS Change_Count,
        SUM(LOWER(TRIM(cl.Field)) = 'status') AS Status_Change_Count,
        SUM(LOWER(TRIM(cl.Field)) = 'priority') AS Priority_Change_Count,
        SUM(LOWER(TRIM(cl.Field)) = 'assignee') AS Assignee_Change_Count,
        SUM(LOWER(TRIM(cl.Field)) = 'description') AS Description_Change_Count,
        SUM(LOWER(TRIM(cl.Field)) = 'story points') AS Story_Point_Change_Count,
        SUM(LOWER(TRIM(cl.Field)) = 'sprint') AS Sprint_Change_Count,
        MAX(cl.Creation_Date) AS Last_Change_Date,
        MAX(CASE WHEN LOWER(TRIM(cl.Field)) = 'status'
                 THEN cl.Creation_Date END) AS Last_Status_Change_Date
    FROM snapshots AS s
    JOIN Change_Log AS cl ON cl.Issue_ID = s.ID
        AND cl.Creation_Date BETWEEN s.Creation_Date AND s.Snapshot_Date
    GROUP BY s.ID, s.Snapshot_Type
),
comment_activity AS (
    SELECT
        s.ID AS Issue_ID,
        s.Snapshot_Type,
        COUNT(*) AS Comment_Count,
        -- Audit only: publication dates are known, but edit history is not.
        SUM(CHAR_LENGTH(COALESCE(c.Comment, ''))) AS Stored_Comment_Total_Length,
        MAX(c.Creation_Date) AS Last_Comment_Date
    FROM snapshots AS s
    JOIN Comment AS c ON c.Issue_ID = s.ID
        AND c.Creation_Date BETWEEN s.Creation_Date AND s.Snapshot_Date
    GROUP BY s.ID, s.Snapshot_Type
),
snapshot_features AS (
    SELECT
        ss.*,
        -- Guard casts: empty/negative/non-numeric estimates are not zero.
        CASE WHEN TRIM(ss.Story_Point_Raw_At_Snapshot)
                      REGEXP '^[0-9]+([.][0-9]+)?$'
             THEN CAST(ss.Story_Point_Raw_At_Snapshot AS DECIMAL(20, 4))
             ELSE NULL END AS Story_Point_At_Snapshot,
        COALESCE(ca.Change_Count, 0) AS Change_Count,
        COALESCE(ca.Status_Change_Count, 0) AS Status_Change_Count,
        COALESCE(ca.Priority_Change_Count, 0) AS Priority_Change_Count,
        COALESCE(ca.Assignee_Change_Count, 0) AS Assignee_Change_Count,
        COALESCE(ca.Description_Change_Count, 0) AS Description_Change_Count,
        COALESCE(ca.Story_Point_Change_Count, 0) AS Story_Point_Change_Count,
        COALESCE(ca.Sprint_Change_Count, 0) AS Sprint_Change_Count,
        COALESCE(cm.Comment_Count, 0) AS Comment_Count,
        COALESCE(cm.Stored_Comment_Total_Length, 0) AS Stored_Comment_Total_Length,
        TIMESTAMPDIFF(SECOND, ca.Last_Change_Date, ss.Snapshot_Date)
            / 3600.0 AS Hours_Since_Last_Change,
        TIMESTAMPDIFF(SECOND, ca.Last_Status_Change_Date, ss.Snapshot_Date)
            / 3600.0 AS Hours_Since_Last_Status_Change,
        TIMESTAMPDIFF(SECOND, cm.Last_Comment_Date, ss.Snapshot_Date)
            / 3600.0 AS Hours_Since_Last_Comment,
        MONTH(ss.Snapshot_Date) AS Snapshot_Month,
        WEEKDAY(ss.Snapshot_Date) AS Snapshot_Day_Of_Week,
        HOUR(ss.Snapshot_Date) AS Snapshot_Hour
    FROM snapshot_states AS ss
    LEFT JOIN change_activity AS ca
        ON ca.Issue_ID = ss.Issue_ID AND ca.Snapshot_Type = ss.Snapshot_Type
    LEFT JOIN comment_activity AS cm
        ON cm.Issue_ID = ss.Issue_ID AND cm.Snapshot_Type = ss.Snapshot_Type
)
SELECT
    ss.*,
    CASE WHEN ss.Assignee_Source = 'invalid_history' THEN NULL
         WHEN ss.Assignee_At_Snapshot IS NOT NULL THEN 1
         ELSE 0 END AS Has_Assignee_At_Snapshot,
    CASE WHEN ss.Sprint_Source = 'invalid_history' THEN NULL
         WHEN ss.Sprint_At_Snapshot IS NOT NULL THEN 1
         ELSE 0 END AS Has_Sprint_At_Snapshot,
    CASE WHEN ss.Story_Point_Source = 'invalid_history' THEN NULL
         WHEN ss.Story_Point_At_Snapshot IS NOT NULL THEN 1
         ELSE 0 END AS Has_Story_Point,
    CASE WHEN ss.Description_Length_At_Snapshot IS NULL THEN NULL
         WHEN ss.Description_Length_At_Snapshot > 0 THEN 1
         ELSE 0 END AS Has_Description_At_Snapshot
FROM snapshot_features AS ss;
