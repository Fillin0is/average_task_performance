import pandas as pd
from sqlalchemy import text

from data_access.connection import engine


query = text("""
            SELECT
        Issue_Key,
        Title,
        Type,
        Priority,
        Status,
        Resolution_Time_Minutes
    FROM Issue
    LIMIT 100
""")

df = pd.read_sql_query(query, engine)

print(df.shape)
print(df.head())
