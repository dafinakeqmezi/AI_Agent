# Code quality for ML projects

Relevant requirements: **IMPL-001 to IMPL-004**.
Key source: `sculley2015debt`.

## Checklist

- [ ] Clear project structure (e.g. `src/`, `data/`, `notebooks/`, `results/`, `tests/`)
- [ ] No hardcoded absolute paths (`C:\Users\...`, `/home/...`, `/content/drive/...`); paths relative or configurable
- [ ] Configuration (hyperparameters, paths) separated from code: config file / CLI arguments
- [ ] Functions and modules used appropriately; no single notebook containing the whole project (scan.json flags notebooks with very many cells/lines)
- [ ] Meaningful names
- [ ] Error handling where external I/O can fail
- [ ] Tests where appropriate (data-processing functions, metric code)
- [ ] Dependencies pinned (REPRO-001)
- [ ] No secrets (API keys, tokens, passwords) committed
- [ ] README exists (DOC-001)
- [ ] **Code matches the methodology in the report (IMPL-002)**

## Report vs code consistency (IMPL-002)

Build a short table:

| Report says | Code does | Status |
|---|---|---|
| "5-fold cross-validation" | only `train_test_split(..., test_size=0.2)` | INCONSISTENT |
| "LSTM with 2 layers, 128 units" | `nn.LSTM(input, 64, num_layers=1)` | INCONSISTENT |
| "Random Forest, 500 trees" | `RandomForestClassifier(n_estimators=500)` | CONSISTENT |

scan.json `consistency` signals give leads (model and validation keywords in the report with no matching code). Always confirm by reading the code.
