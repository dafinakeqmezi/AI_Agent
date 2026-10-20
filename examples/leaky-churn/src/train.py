import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

df = pd.read_csv("C:\\Users\\student\\Desktop\\churn.csv")
X = df.drop(columns=["churn"])
y = df["churn"]

scaler = StandardScaler()
X = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

model = RandomForestClassifier(n_estimators=500)
model.fit(X_train, y_train)
print("accuracy", accuracy_score(y_test, model.predict(X_test)))
