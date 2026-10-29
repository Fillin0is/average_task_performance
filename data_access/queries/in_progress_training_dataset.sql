SELECT
    i.ID AS Issue_ID,
    i.Project_ID,
    i.Creation_Date,
    i.Resolution_Date,
    i.Resolution_Time_Minutes,
    CHAR_LENGTH(COALESCE(i.Description_Text, '')) AS Description_Issue_Length,
    TIMESTAMPDIFF(
    	SECOND,
    	i.Creation_Date,
    	i.Resolution_Date
    ) / 86400.0 AS Duration_Days
FROM Issue i
WHERE i.Resolution_Date > DATE_ADD(
		i.Creation_Date,
		INTERVAL 5 MINUTE
	)
	AND i.Resolution_Date <= DATE_ADD(
		i.Creation_Date,
		INTERVAL 365 DAY
	)
	AND i.Creation_Date >= '2004-01-01';