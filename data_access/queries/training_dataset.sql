WITH first_priority_change AS (
    SELECT
        cl.Issue_ID,
        cl.From_String,
        cl.Creation_Date,
        ROW_NUMBER() OVER (
            PARTITION BY cl.Issue_ID
            ORDER BY cl.Creation_Date, cl.ID
        ) AS change_number
    FROM Change_Log AS cl
    WHERE LOWER(cl.Field) = 'priority'
),
first_type_change AS (
    SELECT
        cl.Issue_ID,
        cl.From_String,
        cl.Creation_Date,
        ROW_NUMBER() OVER (
            PARTITION BY cl.Issue_ID
            ORDER BY cl.Creation_Date, cl.ID
        ) AS change_number
    FROM Change_Log AS cl
    WHERE LOWER(cl.Field) = 'issuetype'
),
comment_stats AS (
    SELECT
        c.Issue_ID,
        COUNT(*) AS Comment_Count,
        SUM(
            CHAR_LENGTH(COALESCE(c.Comment, ''))
        ) AS Comment_Total_Length
    FROM Comment AS c
    GROUP BY c.Issue_ID
),
change_stats AS (
    SELECT
        cl.Issue_ID,
        COUNT(*) AS Change_Count
    FROM Change_Log AS cl
    GROUP BY cl.Issue_ID
)
SELECT
    i.ID,
    i.Project_ID,
    i.Creation_Date,
    CHAR_LENGTH(COALESCE(i.Description_Text, '')) AS Description_Issue_Length,
    i.Resolution_Date,
    TIMESTAMPDIFF(
        SECOND,
        i.Creation_Date,
        i.Resolution_Date
    ) / 86400.0 AS Duration_Days,
    CASE
        WHEN fpc.Issue_ID IS NULL
            THEN COALESCE(NULLIF(TRIM(i.Priority), ''), 'Unknown')
        ELSE
            COALESCE(NULLIF(TRIM(fpc.From_String), ''), 'Unknown')
    END AS Initial_Priority,
    CASE
        WHEN ftc.Issue_ID IS NULL
            THEN COALESCE(NULLIF(TRIM(i.Type), ''), 'Unknown')
        ELSE
            COALESCE(NULLIF(TRIM(ftc.From_String), ''), 'Unknown')
    END AS Initial_Type,
    CHAR_LENGTH(p.Description) AS Description_Project_Length,
    COALESCE(cs.Comment_Count, 0) AS Comment_Count,
    COALESCE(cs.Comment_Total_Length, 0) AS Comment_Total_Length,
    COALESCE(chs.Change_Count, 0) AS Change_Count
FROM Issue AS i
LEFT JOIN first_priority_change AS fpc
    ON fpc.Issue_ID = i.ID
    AND fpc.change_number = 1
LEFT JOIN first_type_change AS ftc
    ON ftc.Issue_ID = i.ID
    AND ftc.change_number = 1
LEFT JOIN comment_stats AS cs
    ON cs.Issue_ID = i.ID
LEFT JOIN change_stats AS chs
    ON chs.Issue_ID = i.ID
JOIN Project AS p
    ON p.ID = i.Project_ID
WHERE i.Resolution_Date > DATE_ADD(
        i.Creation_Date,
        INTERVAL 5 MINUTE
    )
    AND i.Resolution_Date <= DATE_ADD(
        i.Creation_Date,
        INTERVAL 365 DAY
    )
    AND i.Creation_Date >= '2004-01-01';
