# AIMA 4th ed. topic map for project review

Russell, S., & Norvig, P. (2021). *Artificial Intelligence: A Modern Approach* (4th ed.). Pearson.
Cite as **Russell & Norvig (2021), AIMA 4th ed., §x.y**. Pages below are pdf pages of `aima4.pdf` (Read with `pages: "a-b"`, max 20 per call).
Text for Grep is in `text/` (ligatures normalized; occasional stray spaces inside words, so search with short stems such as `overfit`, `cross-valid`, `hyperparam`).

**Authority.** This textbook is level 4 of the hierarchy in `policies/agent-rules.md` (established literature). Course requirements override it. Use it to explain *why* something is a problem and to point students to the right section. Never deduct points for not following the book.

| Requirement(s) | Topic | AIMA section | pdf pages |
|---|---|---|---|
| PROB-001..004 | Framing an ML problem, what to learn, inputs/outputs, whether ML is the right tool | §19.1 Forms of Learning; §19.2 Supervised Learning; **§19.9.1 Problem formulation** | 664-669; 717-718 |
| DATA-001..003, DATA-005 | Data collection, assessment and management; data quality; bias in data | **§19.9.2 Data collection, assessment, and management** | 718-722 |
| DATA-004 | Train/validation/test separation; "peeking" at the test set (leakage) | §19.4 intro (test-set "peeking", p. 679) and **§19.4.1 Model selection** (validation set, k-fold cross-validation) | 678-682 |
| METH-002 | Choosing a model family | §19.3 Decision trees; §19.6 Linear regression & classification; §19.7 Nonparametric models (k-NN, SVM); §19.8 Ensembles (bagging, random forests, boosting); Ch. 21 Deep learning | 670-716; 763-801 |
| METH-004 | Hyperparameter tuning, model selection, regularization | **§19.4.1 Model selection; §19.4.3 Regularization; §19.4.4 Hyperparameter tuning** | 678-684 |
| METH-003 | Training procedure, optimization | §19.6 (gradient descent); §21.4 Learning algorithms (SGD, momentum, batch normalization) | 689-698; 778-780 |
| EVAL-001 | From error rates to loss; choosing a loss | **§19.4.2 From error rates to loss** (AIMA covers metric choice only briefly; use `ml-guidelines/metric-selection.md` and its references) | 682-684 |
| EVAL-002 | Error analysis, confusion matrix, debugging an ML system | **§19.9.3 Model selection and training** (confusion matrix p. 723; learning curves, Fig. 19.7) | 722-723 |
| EVAL-003 | Overfitting, generalization, learning curves | §19.3 (overfitting, pruning, early stopping); §19.4; §19.5 Theory of learning; **§21.5 Generalization** (architecture choice, weight decay, dropout) | 674-677; 678-688; 781-785 |
| EXP-001..003 | Baseline vs proposed model, controlled comparison, ablation | Not covered as such in AIMA; use `ml-guidelines/experimental-design.md` (Dietterich 1998, Demšar 2006, Dodge et al. 2019) | — |
| IMPL-* / REPRO-* | ML engineering, deployment, monitoring | §19.9.5 Operation, monitoring, and maintenance; complement with `sculley2015debt` and `pineau2021reproducibility` | 725-726 |
| DOC-003 | Interpretability and explainability | **§19.9.4 Trust, interpretability, and explainability** | 723-725 |
| DOC-003, DATA-005 | Ethics: privacy, fairness and bias, trust and transparency, safety | **§27.3.2 Surveillance, security, and privacy; §27.3.3 Fairness and bias; §27.3.4 Trust and transparency; §27.3.7 AI Safety** | 1003-1011; 1014-1017 |

## By project type (for METH-002 / LIT-001 context)

| Project type | Sections |
|---|---|
| Classical supervised ML (tabular) | Ch. 19 (§19.3-19.8), §19.9 |
| Probabilistic models / Bayesian learning / EM | Ch. 20 (§20.1-20.3); background Ch. 12-13 |
| Deep learning (MLP, CNN, RNN) | Ch. 21 (§21.1-21.6) |
| Unsupervised and transfer learning | §21.7 |
| Reinforcement learning | Ch. 22 (§22.1-22.7) |
| NLP: language models, classic NLP | Ch. 23 (§23.1 Language models) |
| Deep NLP / Transformers / pretrained LLMs | Ch. 24 (§24.1 embeddings, §24.3 seq2seq, **§24.4 Transformer**, **§24.5 Pretraining and transfer learning**) |
| Computer vision | Ch. 25 (§25.3-25.5 features, image classification, object detection) |
| Search, planning, agents, games | Ch. 3-6, 11, 2 |
| Decision making under uncertainty | Ch. 16-18 |

## Limits of this source

- AIMA is a general AI textbook (2021). It does not cover recent LLM practice (instruction tuning, RAG, LLM evaluation) or detailed ML evaluation methodology. For those, LIT-002 still expects recent papers.
- A textbook is a valid citation for foundations. A student project whose literature review cites *only* textbooks is weak on LIT-001/LIT-002.
