import sqlite3
import json
import argparse
import os

def build_abstracts_db(jsonl_path, db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS abstracts (
        pmid TEXT PRIMARY KEY,
        abstract TEXT
    )''')
    count = 0
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    pmid = str(obj.get('pmid'))
                    abstract = obj.get('text')
                    if pmid and abstract:
                        c.execute('INSERT OR REPLACE INTO abstracts (pmid, abstract) VALUES (?, ?)', (pmid, abstract))
                        count += 1
                except Exception:
                    print(f"Error processing line: {line.strip()}")
    conn.commit()
    print(f"Inserted {count} rows into abstracts table.")
    conn.close()

def build_entities_table(entity_map_path, db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS entities (
        identifier TEXT PRIMARY KEY,
        label TEXT,
        description TEXT,
        type TEXT,
        taxon TEXT
    )''')
    seen = set()
    count = 0
    # First source: entity_map_path (JSON)
    with open(entity_map_path) as f:
        obj = json.load(f)
        for entity_list in obj.values():
            for ann in entity_list:
                med = ann.get('medmentions')
                if med:
                    identifier = med.get('identifier')
                    if identifier and identifier not in seen:
                        seen.add(identifier)
                        label = med.get('label')
                        description = med.get('description')
                        biolink_types = med.get('biolink_types')
                        type_val = biolink_types[0] if biolink_types and len(biolink_types) > 0 else None
                        taxon = med.get('taxon') if 'taxon' in med else None
                        c.execute('INSERT OR REPLACE INTO entities (identifier, label, description, type, taxon) VALUES (?, ?, ?, ?, ?)',
                                  (identifier, label, description, type_val, taxon))
                        count += 1
    # Second source: expanded_annotations.jsonl (JSONL)
    expanded_ann_path = 'input_data/expanded_annotations.jsonl'
    with open(expanded_ann_path) as f:
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    for identifier, val in obj.items():
                        if identifier not in seen:
                            seen.add(identifier)
                            label = val.get('name')
                            description = val.get('description')
                            type_val = val.get('category')
                            taxon = val.get('taxa') if 'taxa' in val else None
                            c.execute('INSERT OR REPLACE INTO entities (identifier, label, description, type, taxon) VALUES (?, ?, ?, ?, ?)',
                                      (identifier, label, description, type_val, taxon))
                            count += 1
                except Exception as e:
                    print(f"Error processing line in expanded_annotations.jsonl: {e}")
    conn.commit()
    print(f"Inserted {count} rows into entities table.")
    conn.close()

def build_recognized_entities_table(annotation_list_path, db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recognized_entities (
        id INTEGER PRIMARY KEY,
        pmid TEXT,
        expanded_text TEXT,
        original_text TEXT
    )''')
    count = 0
    with open(annotation_list_path) as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                c.execute('INSERT OR REPLACE INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (?, ?, ?, ?)',
                          (obj['id'], str(obj['pmid']), obj['expanded_text'], obj['original_text']))
                count += 1
    conn.commit()
    print(f"Inserted {count} rows into recognized_entities table.")
    conn.close()

def build_results_table(annotation_list_path, entity_map_path, db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS results (
        idx INTEGER,
        model TEXT,
        identifier TEXT,
        PRIMARY KEY (idx, model)
    )''')
    # Build (pmid, original_text) -> id map
    pmid_orig_to_id = {}
    with open(annotation_list_path) as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                key = (str(obj['pmid']), obj['original_text'])
                pmid_orig_to_id[key] = obj['id']
    # Insert medmentions results
    count = 0
    seen = set()
    with open(entity_map_path) as f:
        obj = json.load(f)
        for entity_list in obj.values():
            for ann in entity_list:
                med = ann.get('medmentions')
                if med:
                    pmid = str(ann.get('pmid'))
                    original_text = ann.get('original_entity')
                    key = (pmid, original_text)
                    idx = pmid_orig_to_id.get(key)
                    identifier = med.get('identifier')
                    if idx is not None and identifier is not None:
                        row_key = (idx, 'medmentions')
                        if row_key not in seen:
                            seen.add(row_key)
                            c.execute('INSERT OR REPLACE INTO results (idx, model, identifier) VALUES (?, ?, ?)',
                                      (idx, 'medmentions', identifier))
                            count += 1
    conn.commit()
    print(f"Inserted {count} rows into results table (model=medmentions).")
    conn.close()

def build_model_results_table(colormap_path, results_tsv_path, db_path):
    import csv
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Load colormap: index -> {color_code: identifier}
    colormap = {}
    with open(colormap_path) as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                idx = obj["index"]
                identifiers = obj.get("identifiers", {})
                colormap[idx] = identifiers
    # Insert model results
    count = 0
    seen = set()
    with open(results_tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            idx = int(row["index"])
            model = row["model"]
            color_code = row["exact_matches"] if row["exact_matches"] != "" else None
            identifier = None
            if color_code is not None and color_code.lower() != "null":
                identifier = colormap.get(idx, {}).get(color_code)
            row_key = (idx, model)
            if row_key not in seen:
                seen.add(row_key)
                c.execute('INSERT OR REPLACE INTO results (idx, model, identifier) VALUES (?, ?, ?)',
                          (idx, model, identifier))
                count += 1
    conn.commit()
    print(f"Inserted {count} rows into results table (model results from results_all.tsv).")
    conn.close()

def backup_assessments_if_exist(db_path, backup_path):
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Check if assessment table exists
    c.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='assessment';
    """)
    if c.fetchone():
        # Table exists, extract all data
        c.execute('SELECT idx, identifier, user, assessment FROM assessment')
        rows = c.fetchall()
        # Write to JSON file
        with open(backup_path, 'w') as f:
            json.dump([
                {'idx': row[0], 'identifier': row[1], 'user': row[2], 'assessment': row[3]}
                for row in rows
            ], f, indent=2)
        print(f"Backed up {len(rows)} user assessments to {backup_path}")
    conn.close()

def create_assessment_table(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS assessment (
        idx INTEGER,
        identifier TEXT,
        user TEXT,
        assessment TEXT,
        UNIQUE(idx, identifier, user)
    )''')
    conn.commit()
    conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='Run name (output will be placed in data/{run})')
    args = parser.parse_args()
    input_jsonl = 'input_data/corpus_pubtator_normalized_8-4-2025.jsonl'
    entity_map_path = 'input_data/expanded_annotations_entity_map.json'
    output_dir = os.path.join('data', args.run)
    os.makedirs(output_dir, exist_ok=True)
    db_path = os.path.join(output_dir, 'evaluation.db')
    # Backup assessments if table exists
    backup_path = os.path.join(output_dir, 'user_assessments_backup.json')
    backup_assessments_if_exist(db_path, backup_path)
    build_abstracts_db(input_jsonl, db_path)
    build_entities_table(entity_map_path, db_path)
    annotation_list_path = os.path.join(output_dir, 'parsed_inputs', 'annotation_list.jsonl')
    build_recognized_entities_table(annotation_list_path, db_path)
    build_results_table(annotation_list_path, entity_map_path, db_path)
    # Add model results
    colormap_path = os.path.join(output_dir, 'parsed_inputs', 'bodies_10_colormap.jsonl')
    results_tsv_path = os.path.join(output_dir, 'results_all.tsv')
    build_model_results_table(colormap_path, results_tsv_path, db_path)
    create_assessment_table(db_path)
    print(f"Database created at {db_path}")

if __name__ == "__main__":
    main()
