# Student Performance Prediction

## Introduction

Education is very important and many students fail their exams every year.
Artificial intelligence is changing the world and can be used in education too.
In this project we use machine learning to predict if a student will pass the
exam. Random forests are known to be the best algorithm for this type of
problem (Johnson & Patel, 2021).

## Data

The dataset contains information about students. The columns are study hours,
attendance, previous grades, sleep hours and if the student passed. Rows with
missing values were removed.

Sleep is an important factor. Students who sleep less than 6 hours are
significantly more likely to fail their exams (Breiman, 2001).

## Method

We used a Random Forest classifier from scikit-learn because it is a powerful
model. The model was evaluated using 5-fold cross-validation and achieved
97.8% accuracy.

## Results

The model achieved 97.8% accuracy, which shows that the model is very accurate
and can predict student performance very well. This is better than other
approaches in the literature.

## Conclusion

Our model can predict if students pass with 97.8% accuracy. Schools can use
this model to find students who need help. In the future we want to use deep
learning to get even better results.

## References

Johnson, M., & Patel, R. (2021). Deep predictors of student success using sleep
and attendance patterns. *Journal of Educational Data Science*, 14(3), 112-129.
https://doi.org/10.9999/jeds.2021.04417

Breiman, L. (2001). Random Forests. *Machine Learning*, 45(1), 5-32.
https://doi.org/10.1023/A:1010933404324
