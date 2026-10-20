# Evaluation metric selection

Relevant requirement: **EVAL-001** (also PROB-002).
Key sources: `saito2015prplot`, `sokolova2009measures`, `chicco2020mcc`.

The question is never only "did the student use a metric?" but **"why is this metric appropriate for this problem?"** Check that the justification exists and is correct.

## By task

| Task | Typical metrics | Pitfalls to flag |
|---|---|---|
| Binary classification, balanced | Accuracy, F1, ROC-AUC | Threshold not discussed when costs differ |
| Binary classification, imbalanced | PR-AUC, F1 / F-beta, recall at fixed precision, MCC, balanced accuracy | **Accuracy alone is misleading** (a majority-class predictor scores high). ROC-AUC can look optimistic under heavy imbalance (Saito & Rehmsmeier 2015) |
| Multi-class | Macro/micro/weighted F1, per-class precision/recall, confusion matrix | Reporting only micro averages hides poor minority-class performance |
| Regression | MAE, RMSE, R², MAPE (careful near zero) | RMSE vs MAE choice should reflect whether large errors matter more; R² alone does not show error magnitude |
| Ranking / recommendation | Precision@K, Recall@K, MAP, NDCG | K must be justified; offline metrics vs online behaviour |
| Text generation / summarization | ROUGE, BLEU, BERTScore, plus human evaluation | n-gram metrics correlate weakly with quality; report human or LLM-judge protocols transparently |
| LLM / RAG systems | Task accuracy, faithfulness/groundedness, retrieval recall@K, human ratings | Evaluation set leakage into prompts; judge-model bias |
| Clustering | Silhouette, Davies-Bouldin, ARI/NMI (with labels) | Internal metrics alone do not show usefulness |
| Detection / segmentation | mAP@IoU, IoU / Dice | IoU threshold must be stated |

## Checks

1. The metric matches the stated objective (PROB-002) and the cost of errors in the domain (e.g. medical screening: recall matters).
2. Class distribution is reported, so the reader can judge accuracy (DATA-002).
3. A baseline score is given on the same metric (METH-001); for imbalanced data, report the majority-class baseline.
4. Results are on the **test** set, not training/validation.
5. Variability is reported where feasible (EXP-002).
