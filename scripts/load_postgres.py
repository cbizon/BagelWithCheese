import psycopg2
import csv
import os
import argparse

def get_connection(args):
    return psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password
    )

def load_abstracts(conn, tsv_path):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS abstracts (
            pmid TEXT PRIMARY KEY,
            abstract TEXT
        )''')
        count = 0
        with open(tsv_path) as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                c.execute('INSERT INTO abstracts (pmid, abstract) VALUES (%s, %s) ON CONFLICT (pmid) DO UPDATE SET abstract=EXCLUDED.abstract',
                          (row['pmid'], row['abstract']))
                count += 1
    conn.commit()
    print(f"Loaded {count} rows into abstracts table.")

def load_entities(conn, tsv_path):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS entities (
            identifier TEXT PRIMARY KEY,
            label TEXT,
            description TEXT,
            type TEXT,
            taxon TEXT
        )''')
        count = 0
        with open(tsv_path) as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                c.execute('INSERT INTO entities (identifier, label, description, type, taxon) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (identifier) DO UPDATE SET label=EXCLUDED.label, description=EXCLUDED.description, type=EXCLUDED.type, taxon=EXCLUDED.taxon',
                          (row['identifier'], row['label'], row['description'], row['type'], row['taxon']))
                count += 1
    conn.commit()
    print(f"Loaded {count} rows into entities table.")

def load_recognized_entities(conn, tsv_path):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS recognized_entities (
            id INTEGER PRIMARY KEY,
            pmid TEXT,
            expanded_text TEXT,
            original_text TEXT
        )''')
        count = 0
        with open(tsv_path) as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                c.execute('INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET pmid=EXCLUDED.pmid, expanded_text=EXCLUDED.expanded_text, original_text=EXCLUDED.original_text',
                          (row['id'], row['pmid'], row['expanded_text'], row['original_text']))
                count += 1
    conn.commit()
    print(f"Loaded {count} rows into recognized_entities table.")

def load_results(conn, tsv_path):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS results (
            idx INTEGER,
            model TEXT,
            identifier TEXT,
            PRIMARY KEY (idx, model)
        )''')
        count = 0
        with open(tsv_path) as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                identifier = row['identifier'] if row['identifier'] != '' else None
                c.execute('INSERT INTO results (idx, model, identifier) VALUES (%s, %s, %s) ON CONFLICT (idx, model) DO UPDATE SET identifier=EXCLUDED.identifier',
                          (row['idx'], row['model'], identifier))
                count += 1
    conn.commit()
    print(f"Loaded {count} rows into results table.")

def load_assessment(conn, tsv_path):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS assessment (
            idx INTEGER,
            identifier TEXT,
            assessor TEXT,
            assessment TEXT,
            UNIQUE(idx, identifier, assessor)
        )''')
        count = 0
        with open(tsv_path) as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                c.execute('INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (%s, %s, %s, %s) ON CONFLICT (idx, identifier, assessor) DO UPDATE SET assessment=EXCLUDED.assessment',
                          (row['idx'], row['identifier'], row['assessor'], row['assessment']))
                count += 1
    conn.commit()
    print(f"Loaded {count} rows into assessment table.")

def update_results(conn, tsv_path):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS results (
            idx INTEGER,
            model TEXT,
            identifier TEXT,
            PRIMARY KEY (idx, model)
        )''')
        c.execute('SELECT idx, model FROM results')
        existing = set(c.fetchall())
        with open(tsv_path) as f:
            reader = csv.DictReader(f, delimiter='\t')
            new_rows = 0
            for row in reader:
                key = (int(row['idx']), row['model'])
                if key not in existing:
                    identifier = row['identifier'] if row['identifier'] != '' else None
                    c.execute('INSERT INTO results (idx, model, identifier) VALUES (%s, %s, %s)',
                              (row['idx'], row['model'], identifier))
                    new_rows += 1
    conn.commit()
    print(f"Inserted {new_rows} new rows into results table.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='Run name (input will be read from data/{run})')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=5432)
    parser.add_argument('--dbname', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--update_results', action='store_true', help='Only update results table with new rows from results.tsv')
    args = parser.parse_args()
    input_dir = os.path.join('data', args.run)
    conn = get_connection(args)
    if args.update_results:
        update_results(conn, os.path.join(input_dir, 'results.tsv'))
        print(f"Results table updated in {args.dbname}")
    else:
        load_abstracts(conn, os.path.join(input_dir, 'abstracts.tsv'))
        load_entities(conn, os.path.join(input_dir, 'entities.tsv'))
        load_recognized_entities(conn, os.path.join(input_dir, 'recognized_entities.tsv'))
        load_results(conn, os.path.join(input_dir, 'results.tsv'))
        load_assessment(conn, os.path.join(input_dir, 'assessment.tsv'))
        print(f"Database loaded at {args.dbname}")
    conn.close()

if __name__ == '__main__':
    main()
