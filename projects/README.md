# Student projects

To register a GitHub repo without editing JSON, run `python3 -m grader roster add`
from the project root and enter its URL, student name, and assignment ID.
Repeat for each repo; `python3 -m grader roster list` shows saved entries in
`projects/roster.json`. Registration alone does not fetch, review, or grade repos.
See [the AI tools guide](../docs/ai-tools.md) for the prompt to review the roster.

Put each student's working project in its own folder here (e.g. `projects/ana-churn-prediction/`), or point `/review` at any folder on disk.

Expected (not required) structure, as described in the project brief:

```
proposal.md
README.md
report.pdf | report.docx | report.md
notebooks/
src/
results/
data/            (or download instructions)
presentation/
requirements.txt | environment.yml
```

The folder name becomes the project key used in `state/registry.json`, `reviews/` and submission IDs.
