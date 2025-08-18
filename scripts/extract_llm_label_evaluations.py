import csv
import json

BLANKS_PATH = "data/run_3/blanks.txt"
RESPONSES_PATH = "data/run_3/ollama_results/gpt-oss__bodies_10_message_output.jsonl"
OUTPUT_PATH = "data/run_3/llm_label_evaluations.csv"

# Step 1: Read blanks.txt
rows = []
with open(BLANKS_PATH, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter='|')
    for row in reader:
        # Use the first idx column (column 0)
        rows.append({
            'idx': int(row['idx']),
            'original_text': row['original_text'],
            'label': row['label']
        })

# Step 2: Read LLM responses into a dict
responses = {}
with open(RESPONSES_PATH, encoding='utf-8') as f:
    for line in f:
        obj = json.loads(line)
        idx = obj['index']
        try:
            content = json.loads(obj['content'])
        except Exception:
            continue
        responses[idx] = content

# Step 3: For each row, find the evaluation for the label
output_rows = []
for row in rows:
    idx = row['idx']
    label = row['label']
    evaluation = ''
    if idx in responses:
        candidates = responses[idx].get('candidates', [])
        for cand in candidates:
            if cand.get('candidate', '').strip() == label.strip():
                evaluation = cand.get('evaluation', '')
                break
        else:
            evaluation = 'NOT FOUND'
    else:
        evaluation = 'NO LLM RESPONSE'
    output_rows.append({
        'idx': idx,
        'original_text': row['original_text'],
        'label': label,
        'evaluation': evaluation
    })

# Step 4: Write output
with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['idx', 'original_text', 'label', 'evaluation'])
    writer.writeheader()
    for row in output_rows:
        writer.writerow(row)

print(f"Wrote {len(output_rows)} rows to {OUTPUT_PATH}")
