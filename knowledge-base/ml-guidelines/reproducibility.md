# Reproducibility checklist

Relevant requirements: **REPRO-001 to REPRO-004, DOC-001**.
Key sources: `pineau2021reproducibility`, `kapoor2024reforms`, `wilkinson2016fair`.

| Item | Requirement | Evidence to look for |
|---|---|---|
| Dependency file with pinned versions (`==`) | REPRO-001 | `requirements.txt`, `environment.yml`, `pyproject.toml` + lock file |
| Python version stated | REPRO-001 | README, `environment.yml`, `.python-version`, `pyproject.toml` |
| Random seeds set (numpy, random, framework, `random_state=`) | REPRO-002 | code; scan.json `seed` signals |
| Dataset source and download/acquisition instructions | REPRO-003, DATA-001 | README / data/README |
| Preprocessing script | REPRO-003 | `src/`, notebooks |
| Training script | REPRO-003 | `src/`, notebooks |
| Evaluation script | REPRO-003 | `src/`, notebooks |
| Hyperparameters documented | METH-004 | config file / report table |
| Model configuration saved | REPRO-004 | config / checkpoint metadata |
| README execution instructions | DOC-001 | README with exact commands |
| Experiment outputs saved | REPRO-004 | `results/`, logs, executed notebook outputs |

## Reproducibility score (Agent 1)

Agent 1 reports `reproducibility_score` as the number of the 11 rows above that are satisfied, scaled to 0-10 and rounded, plus the list of missing items. Example:

```
Reproducibility Score: 7/10
Missing:
- random seed
- Python version
- dataset download instructions
```

## Notebook-specific checks

- Execution counts in order (out-of-order execution means hidden state; the notebook may not run top to bottom). scan.json reports this.
- Outputs present for the cells that produce reported numbers.
- No reliance on Colab-only paths (`/content/drive`) without instructions.
