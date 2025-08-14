import sqlite3
import json
import os
import argparse
import re

def build_abstracts_db(jsonl_path, db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS abstracts (
        pmid TEXT PRIMARY KEY,
        abstract TEXT
    )''')
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    pmid = str(obj.get('pmid'))
                    abstract = obj.get('text')
                    if pmid and abstract:
                        c.execute('INSERT OR REPLACE INTO abstracts (pmid, abstract) VALUES (?, ?)', (pmid, abstract))
                except Exception:
                    print(f"Error processing line: {line.strip()}", obj.keys())
    conn.commit()
    conn.close()

def build_index_to_pmid(annotations_path, db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS index_to_pmid (
        idx INTEGER PRIMARY KEY,
        pmid TEXT
    )''')
    with open(annotations_path) as f:
        for idx, line in enumerate(f):
            if line.strip():
                try:
                    obj = json.loads(line)
                    pmid = str(obj.get('pmid'))
                    if pmid:
                        c.execute('INSERT OR REPLACE INTO index_to_pmid (idx, pmid) VALUES (?, ?)', (idx, pmid))
                except Exception:
                    print(f"Error processing line: {line.strip()}")
    conn.commit()
    conn.close()

def get_available_thresholds(run_dir):
    import sys
    thresholds = set()
    # Check parsed_inputs for bodies_{threshold}_colormap.jsonl
    parsed_inputs_dir = os.path.join(run_dir, 'parsed_inputs')
    if os.path.exists(parsed_inputs_dir):
        for fname in os.listdir(parsed_inputs_dir):
            m = re.match(r'bodies_(\d+)_colormap\.jsonl', fname)
            if m:
                t = int(m.group(1))
                print(f"Found threshold {t} in parsed_inputs: {fname}")
                thresholds.add(t)
    if not thresholds:
        print(f"Error: No thresholds found in {run_dir}. Exiting.")
        sys.exit(1)
    print(f"Final thresholds found: {sorted(thresholds)}")
    return sorted(thresholds)

def build_entities_and_sequence_tables(db_path, data_dir, thresholds):
    import glob
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Create entities_by_index table with entity column and dynamic threshold columns
    cols = ', '.join([f'entities_{t} TEXT' for t in thresholds])
    c.execute(f'''CREATE TABLE IF NOT EXISTS entities_by_index (
        idx INTEGER PRIMARY KEY,
        entity TEXT,
        {cols}
    )''')
    entities_dict = {}
    for threshold in thresholds:
        filename = os.path.join(data_dir, f"bodies_{threshold}_colormap.jsonl")
        if not os.path.exists(filename):
            continue
        with open(filename) as f:
            for line in f:
                obj = json.loads(line)
                idx = obj.get('index')
                if idx is not None:
                    if idx not in entities_dict:
                        entities_dict[idx] = {}
                        entities_dict[idx]['entity'] = obj.get('entity', None)
                    labels = obj.get('labels', {})
                    taxons = obj.get('taxons', {})
                    display_labels = []
                    for color in labels:
                        label = labels[color]
                        taxon = taxons.get(color, "")
                        if taxon:
                            display_labels.append(f"{label} ({taxon})")
                        else:
                            display_labels.append(label)
                    entities_dict[idx][f'entities_{threshold}'] = json.dumps(display_labels)
    # Insert into entities_by_index
    for idx, ents in entities_dict.items():
        values = [idx, ents.get('entity')] + [ents.get(f'entities_{t}') for t in thresholds]
        placeholders = ', '.join(['?'] * (2 + len(thresholds)))
        c.execute(f'INSERT OR REPLACE INTO entities_by_index (idx, entity, {", ".join([f"entities_{t}" for t in thresholds])}) VALUES ({placeholders})', values)
    # Create index_sequence table with both next and previous indices
    c.execute('''CREATE TABLE IF NOT EXISTS index_sequence (
        idx INTEGER PRIMARY KEY,
        next_idx INTEGER,
        prev_idx INTEGER
    )''')
    sorted_indices = sorted(entities_dict.keys())
    for i, idx in enumerate(sorted_indices):
        next_idx = sorted_indices[i+1] if i+1 < len(sorted_indices) else None
        prev_idx = sorted_indices[i-1] if i-1 >= 0 else None
        c.execute('INSERT OR REPLACE INTO index_sequence (idx, next_idx, prev_idx) VALUES (?, ?, ?)', (idx, next_idx, prev_idx))
    conn.commit()
    conn.close()

def build_results_table(db_path, data_dir, thresholds):
    import csv
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Create results table with TEXT columns for color code lists, dynamic thresholds
    cols = []
    for t in thresholds:
        for rtype in ['exact', 'superclass', 'subclass', 'related', 'none']:
            cols.append(f'{rtype}_matches_{t} TEXT')
    cols_str = ', '.join(cols)
    c.execute(f'''CREATE TABLE IF NOT EXISTS results (
        idx INTEGER,
        model TEXT,
        {cols_str},
        PRIMARY KEY (idx, model)
    )''')
    agg_path = os.path.join(data_dir, 'results_all.tsv')
    if not os.path.exists(agg_path):
        print(f"No aggregated summary found at {agg_path}")
        conn.close()
        return
    with open(agg_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            try:
                idx = int(row['index'])
            except Exception:
                print(f"Skipping screwy row")
                continue
            model = row['model']
            threshold = int(row['threshold'])
            tstr = str(threshold)
            update_dict = {
                f'exact_matches_{tstr}': row['exact_matches'],
                f'subclass_matches_{tstr}': row['subclass_matches'],
                f'superclass_matches_{tstr}': row['superclass_matches'],
                f'related_matches_{tstr}': row['related_matches'],
                f'none_matches_{tstr}': row['none_matches'],
            }
            set_clause = ', '.join([f'{k}=?' for k in update_dict.keys()])
            values = list(update_dict.values())
            c.execute('SELECT 1 FROM results WHERE idx=? AND model=?', (idx, model))
            exists = c.fetchone()
            if exists:
                c.execute(f'UPDATE results SET {set_clause} WHERE idx=? AND model=?', values + [idx, model])
            else:
                insert_cols = ['idx', 'model'] + list(update_dict.keys())
                insert_vals = [idx, model] + values
                # Fill in empty lists for other thresholds
                for t in thresholds:
                    if str(t) == tstr:
                        continue
                    for rtype in ['exact', 'superclass', 'subclass', 'related', 'none']:
                        col = f'{rtype}_matches_{t}'
                        insert_cols.append(col)
                        insert_vals.append('')
                c.execute(f'INSERT OR REPLACE INTO results ({', '.join(insert_cols)}) VALUES ({', '.join(['?']*len(insert_cols))})', insert_vals)
    conn.commit()
    conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', help='Run directory name')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)
    db_path = os.path.join(run_dir, 'results.db')
    jsonl_path = os.path.join('input_data', 'corpus_pubtator_normalized_8-4-2025.jsonl')
    annotations_path = os.path.join('input_data', 'annotations-7-30-25.jsonl')
    thresholds = get_available_thresholds(run_dir)
    build_abstracts_db(jsonl_path, db_path)
    build_index_to_pmid(annotations_path, db_path)
    build_entities_and_sequence_tables(db_path, os.path.join(run_dir, 'parsed_inputs'), thresholds)
    build_results_table(db_path, run_dir, thresholds)

if __name__ == "__main__":
    main()
