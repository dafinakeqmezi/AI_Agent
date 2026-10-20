# Course materials (highest authority)

Put the professor's documents here, for example:

```
course/
  project-requirements.pdf
  professor-instructions.pdf
  grading-rubric.pdf
  lecture-materials/
policies (university-level) go in ../policies/:
  plagiarism-policy.pdf
  allowed-ai-usage.pdf
  citation-policy.pdf
```

Then run `/import-course` in Claude Code. It converts these documents into `requirements/requirements.json`, `rubric/rubric.json`, `requirements/dod.json` and the AI-usage section of `policies/integrity-policy.json`, bumps their versions, and lists anything it could not map so you can resolve it by hand. It never invents requirements or point values that are not in the documents.

Until then, the requirements and rubric are **placeholders** (`"status": "PLACEHOLDER"`), and every grade report says so.
