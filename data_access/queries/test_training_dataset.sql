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
comments_count AS (
	SELECT 
		i.ID, 
		COUNT(c.Issue_ID) AS comment_count
	FROM Issue AS i
	JOIN Comment AS c
		ON i.ID = c.Issue_ID	
	GROUP BY c.Issue_ID
)
SELECT
    i.ID,
    i.Project_ID,
    i.Creation_Date,
    CHAR_LENGTH(COALESCE(i.Description_Text, '')) AS Description_Issue_Length,
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
    END AS initial_priority,
    CASE
        WHEN ftc.Issue_ID IS NULL
            THEN COALESCE(NULLIF(TRIM(i.Type), ''), 'Unknown')
        ELSE
            COALESCE(NULLIF(TRIM(ftc.From_String), ''), 'Unknown')
    END AS initial_type,
	COALESCE(cc.comment_count, 0) AS Comment_Count,
	CHAR_LENGTH(p.Description) AS Description_Project_Length
FROM Issue AS i
LEFT JOIN first_priority_change AS fpc
    ON fpc.Issue_ID = i.ID
    AND fpc.change_number = 1
LEFT JOIN first_type_change AS ftc
    ON ftc.Issue_ID = i.ID
    AND ftc.change_number = 1
LEFT JOIN comments_count AS cc
	ON cc.ID = i.ID
JOIN Project AS p
	ON p.id = i.Project_ID
WHERE i.Resolution_Date > DATE_ADD(
        i.Creation_Date,
        INTERVAL 5 MINUTE
    )
    AND i.Resolution_Date <= DATE_ADD(
        i.Creation_Date,
        INTERVAL 365 DAY
    );
