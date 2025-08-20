import sqlite3
import csv
import os
import argparse

def load_abstracts(db_path, tsv_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS abstracts (
        pmid TEXT PRIMARY KEY,
        abstract TEXT
    )''')
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT OR REPLACE INTO abstracts (pmid, abstract) VALUES (?, ?)', (row['pmid'], row['abstract']))
    conn.commit()
    conn.close()

def load_entities(db_path, tsv_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS entities (
        identifier TEXT PRIMARY KEY,
        label TEXT,
        description TEXT,
        type TEXT,
        taxon TEXT
    )''')
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT OR REPLACE INTO entities (identifier, label, description, type, taxon) VALUES (?, ?, ?, ?, ?)',
                      (row['identifier'], row['label'], row['description'], row['type'], row['taxon']))
    conn.commit()
    conn.close()

def load_recognized_entities(db_path, tsv_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recognized_entities (
        id INTEGER PRIMARY KEY,
        pmid TEXT,
        expanded_text TEXT,
        original_text TEXT
    )''')
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT OR REPLACE INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (?, ?, ?, ?)',
                      (row['id'], row['pmid'], row['expanded_text'], row['original_text']))
    conn.commit()
    conn.close()

def load_results(db_path, tsv_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS results (
        idx INTEGER,
        model TEXT,
        identifier TEXT,
        PRIMARY KEY (idx, model)
    )''')
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            identifier = row['identifier'] if row['identifier'] != '' else None
            c.execute('INSERT OR REPLACE INTO results (idx, model, identifier) VALUES (?, ?, ?)',
                      (row['idx'], row['model'], identifier))
    conn.commit()
    conn.close()

def load_assessment(db_path, tsv_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS assessment (
        idx INTEGER,
        identifier TEXT,
        assessor TEXT,
        assessment TEXT,
        UNIQUE(idx, identifier, assessor)
    )''')
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT OR REPLACE INTO assessment (idx, identifier, assessor, assessment) VALUES (?, ?, ?, ?)',
                      (row['idx'], row['identifier'], row['assessor'], row['assessment']))
    conn.commit()
    conn.close()

def update_results(db_path, tsv_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS results (
        idx INTEGER,
        model TEXT,
        identifier TEXT,
        PRIMARY KEY (idx, model)
    )''')
    # Fetch all existing (idx, model) pairs
    c.execute('SELECT idx, model FROM results')
    existing = set(c.fetchall())
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        new_rows = 0
        for row in reader:
            key = (int(row['idx']), row['model'])
            if key not in existing:
                c.execute('INSERT INTO results (idx, model, identifier) VALUES (?, ?, ?)',
                          (row['idx'], row['model'], row['identifier']))
                new_rows += 1
    conn.commit()
    conn.close()
    print(f"Inserted {new_rows} new rows into results table.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='Run name (input will be read from data/{run})')
    parser.add_argument('--update_results', action='store_true', help='Only update results table with new rows from results.tsv')
    args = parser.parse_args()
    input_dir = os.path.join('data', args.run)
    db_path = os.path.join(input_dir, 'evaluation.db')
    if args.update_results:
        update_results(db_path, os.path.join(input_dir, 'results.tsv'))
        print(f"Results table updated in {db_path}")
    else:
        load_abstracts(db_path, os.path.join(input_dir, 'abstracts.tsv'))
        load_entities(db_path, os.path.join(input_dir, 'entities.tsv'))
        load_recognized_entities(db_path, os.path.join(input_dir, 'recognized_entities.tsv'))
        load_results(db_path, os.path.join(input_dir, 'results.tsv'))
        load_assessment(db_path, os.path.join(input_dir, 'assessment.tsv'))
        print(f"Database created at {db_path}")

if __name__ == '__main__':
    main()
