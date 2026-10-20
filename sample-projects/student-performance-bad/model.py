import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# load data
df = pd.read_csv("C:/Users/student/Desktop/ml project/data.csv")

df = df.dropna()

# features
X = df[["study_hours", "attendance", "previous_grade", "sleep_hours"]]
X["final_exam_score"] = df["final_exam_score"]
y = df["passed"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2
)

model = RandomForestClassifier(n_estimators=100)
model.fit(X_train, y_train)

pred = model.predict(X_test)
acc = accuracy_score(y_test, pred)
print("Accuracy:", acc)
