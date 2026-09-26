from sklearn.model_selection import KFold, cross_val_score
from sklearn.ensemble import RandomForestRegressor


df = df.sort_values("date")

df["city_target_mean"] = df.groupby("city")["target_next_day"].transform("mean")
df["target_next_day"] = df["price"].shift(-1)
df["rolling_mean_7"] = df["price"].rolling(7).mean()
df = df.dropna()


X = df.drop(columns=["target_next_day", "date"])
y = df["target_next_day"]

cv = KFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(RandomForestRegressor(n_estimators=200), X, y, cv=cv, scoring="r2")
print(scores.mean())