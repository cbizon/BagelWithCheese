# Assignment System for Evaluation App

The assignment system allows you to pre-assign specific annotations to assessors, ensuring they only see and evaluate the annotations assigned to them.

## Overview

- **Assignments are annotation-level**, not abstract-level
- Only annotations meeting **skip-mode criteria** can be assigned:
  - Has at least one non-medmentions model result
  - Models disagree (multiple distinct identifiers OR presence of NULLs)
- When logged in with assignments, users enter **Assignment Mode** automatically
- Progress tracking shows completed/remaining assignments
- Assignments are marked complete when all non-NULL identifiers are assessed

## Database Setup

The `assignments` table is created automatically when you run:

### SQLite
```bash
python scripts/load_sqlite.py --run <run_name>
```

### PostgreSQL
```bash
python scripts/load_postgres.py --run <run_name> --host <host> --port <port> --dbname <dbname> --user <user> --password <password>
```

The table structure:
```sql
CREATE TABLE assignments (
    id INTEGER/SERIAL PRIMARY KEY,
    assessor TEXT NOT NULL,           -- Username of the assessor
    pmid TEXT NOT NULL,                -- PubMed ID
    idx INTEGER NOT NULL,              -- Annotation index
    span_text TEXT NOT NULL,           -- Original text span
    completed BOOLEAN DEFAULT false,   -- Auto-updated when all assessments done
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(assessor, idx)
);
```

## Loading Assignments

### Step 1: Create a TSV File

Create a TSV file with two columns:
- `assessor`: The username of the person doing the evaluation
- `pmid`: The PubMed ID of the abstract to assign

**The script automatically finds all annotations in each abstract that meet skip-mode criteria.**

Example `assignments.tsv`:
```tsv
assessor	pmid
alice	12345678
alice	12345679
bob	87654321
bob	23456789
```

### Step 2: Load the TSV

**For SQLite:**
```bash
python scripts/load_assignments.py \
    --tsv assignments.tsv \
    --backend sqlite \
    --db_path data/run_5/evaluation.db
```

**For PostgreSQL:**
```bash
python scripts/load_assignments.py \
    --tsv assignments.tsv \
    --backend postgres \
    --host localhost \
    --port 5432 \
    --dbname evaluation_db \
    --user postgres \
    --password your_password
```

### Load Output

The script will report:
- **Total abstracts processed**: Number of assessor/PMID pairs in the TSV
- **Total annotations assigned**: Number of annotations that met skip-mode criteria
- **Abstracts with no eligible annotations**: Abstracts where no annotations met the criteria

An abstract has "no eligible annotations" if all its annotations either:
- Have only medmentions results (no other models)
- Have complete agreement between all models

## Assignment Mode UI

When a user with assignments logs in:

### Visual Indicators
1. **"Assignment Mode" badge** replaces the "Enter skip mode" link
2. **Progress counter** shows: "Progress: X / Y completed (Z remaining)"
3. **Skip mode toggle is hidden** (assignment mode takes precedence)

### Navigation
- **Previous/Next annotation**: Navigate through all assigned annotations
- **Previous/Next abstract**: Navigate through abstracts with assignments
- **Prev/Next uncompleted**: Jump to uncompleted annotations only

### Completion Tracking
- As users assess identifiers, the system tracks progress
- When **all non-NULL identifiers** for an annotation are assessed, it's marked complete
- Progress counter updates automatically
- "Next uncompleted" navigation helps skip finished work

## Assignment Workflow

1. **Admin creates TSV** with assignments for each assessor
2. **Admin loads TSV** using `load_assignments.py`
3. **Assessor logs in** with their username
4. **System detects assignments** and enters Assignment Mode
5. **Assessor evaluates** their assigned annotations
6. **System auto-completes** annotations as assessments are submitted
7. **Assessor tracks progress** via the progress counter

## Navigation Priority

The system uses this priority order:
1. **Assignment Mode** - If user has assignments, use assignment navigation
2. **Skip Mode** - If no assignments and skip mode enabled, use skip navigation
3. **Regular Mode** - Show all annotations

## Example: Creating Assignments

```python
# Generate a TSV programmatically
import csv

assignments = [
    {'assessor': 'alice', 'pmid': '12345678'},
    {'assessor': 'alice', 'pmid': '12345679'},
    {'assessor': 'bob', 'pmid': '87654321'},
    {'assessor': 'bob', 'pmid': '23456789'},
]

with open('assignments.tsv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['assessor', 'pmid'], delimiter='\t')
    writer.writeheader()
    writer.writerows(assignments)
```

Then load:
```bash
python scripts/load_assignments.py --tsv assignments.tsv --backend sqlite --db_path data/run_5/evaluation.db
```

The script will automatically:
1. Find all annotations in PMID 12345678 that meet skip criteria
2. Assign them all to alice
3. Repeat for all rows in the TSV

## Querying Assignments

### Check an assessor's progress
```sql
SELECT
    assessor,
    COUNT(*) as total,
    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as completed,
    COUNT(*) - SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) as remaining
FROM assignments
WHERE assessor = 'alice'
GROUP BY assessor;
```

### Find uncompleted assignments
```sql
SELECT idx, pmid, span_text
FROM assignments
WHERE assessor = 'alice' AND completed = 0
ORDER BY idx;
```

### See all assessors
```sql
SELECT DISTINCT assessor FROM assignments;
```
