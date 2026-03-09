# CLAUDE.md — Nefeli Repository Guide

## Project Overview

This is a **data science dataset repository** containing Amazon product reviews for Intex inflatable pools. The dataset is designed for **sentiment analysis / review classification** tasks.

The repository contains two CSV files:
- A hand-labeled set (with star ratings) used as ground truth or training data
- An unlabeled set (without ratings) used for inference or evaluation

## Repository Structure

```
nefeli/
├── reviews_hand_labeled.csv      # 20 reviews with sentiment scores (1–5 stars)
├── reviews_unlabeled_short.csv   # 20 reviews without scores (for prediction)
└── CLAUDE.md                     # This file
```

There is no application code, build system, or test suite — this is a **pure data repository**.

## Dataset Details

### `reviews_hand_labeled.csv`

| Column          | Type    | Description                                      |
|-----------------|---------|--------------------------------------------------|
| `review_number` | integer | Sequential row identifier (1–20)                 |
| `review_id`     | string  | Amazon review ID (e.g., `R1OGKCTD3Z7AZM`)       |
| `review_title`  | string  | Short review headline                            |
| `review_text`   | string  | Full review body text                            |
| `Score`         | integer | Star rating from 1 (worst) to 5 (best)          |

### `reviews_unlabeled_short.csv`

Same schema as above, but **without the `Score` column**. These 20 reviews are meant to be predicted/classified.

Both files share the same 20 `review_id` values — the unlabeled file is a subset of the same reviews stripped of their labels.

## Data Characteristics

- **Domain:** Intex inflatable pool products (consumer goods)
- **Source:** Amazon product reviews
- **Volume:** 20 rows per file (small-scale dataset)
- **Encoding:** UTF-8
- **Format:** Comma-separated values (CSV), with quoted fields containing commas

## Typical Use Cases

1. **Few-shot / zero-shot classification** — Use the labeled set as examples to prompt an LLM and predict scores for the unlabeled set.
2. **Fine-tuning training data** — Use labeled reviews as supervised training examples for a sentiment classifier.
3. **Evaluation benchmark** — Compare model predictions on unlabeled reviews against held-out gold labels.
4. **Annotation workflows** — Extend the unlabeled set with additional reviews to be labeled.

## Development Workflows

Since this is a data-only repository, typical workflows involve:

### Adding new data
- Append rows to either CSV, maintaining column order and types.
- Keep `review_number` sequential and `review_id` unique.
- Ensure text fields with commas or quotes are properly CSV-escaped.

### Running analysis or models
- There is no built-in runner. Scripts or notebooks should be created separately.
- Recommended: load data with `pandas.read_csv()` in Python.
- Example:
  ```python
  import pandas as pd
  labeled   = pd.read_csv("reviews_hand_labeled.csv")
  unlabeled = pd.read_csv("reviews_unlabeled_short.csv")
  ```

### Validating data integrity
- Verify `Score` values are integers in range [1, 5].
- Verify `review_id` uniqueness within each file.
- Check that the same 20 `review_id` values appear in both files.

## Conventions

- **No trailing spaces** in CSV fields (leading spaces after commas are present in the source data — preserve as-is unless cleaning).
- **Score column** only exists in `reviews_hand_labeled.csv`; never add it to the unlabeled file.
- **Do not reorder columns** — downstream scripts may rely on column position.
- **Commit data changes with descriptive messages** explaining what was added, corrected, or removed.

## Git Conventions

- Branch names follow the pattern `claude/<task-id>` for AI-assisted work.
- Commit messages should be concise and describe the data change (e.g., `"Add 10 additional labeled reviews for pool pumps"`).
- The `master` branch holds the canonical dataset.

## Contact

Project author: s-eleni (elenigkini@g.ucla.edu) — UCLA
