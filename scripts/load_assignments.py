"""
Script to load annotation assignments from a TSV file.
The TSV should have columns: assessor, pmid
The script will automatically find all annotations in each abstract that meet skip-mode criteria:
- Has at least one non-medmentions model result
- Models disagree (multiple distinct identifiers OR presence of NULLs)
"""
import sqlite3
import psycopg2
import csv
import os
import argparse
import sys

def get_db_connection(backend, db_path=None, host=None, port=None, dbname=None, user=None, password=None):
    """Get database connection based on backend type."""
    if backend == 'postgres':
        conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
        paramstyle = '%s'
    else:  # sqlite
        if not db_path or not os.path.exists(db_path):
            print(f"ERROR: Database not found at {db_path}")
            sys.exit(1)
        conn = sqlite3.connect(db_path)
        paramstyle = '?'
    q = (lambda sql: sql.replace('?', '%s')) if paramstyle == '%s' else (lambda sql: sql)
    return conn, paramstyle, q

def check_skip_criteria(idx, conn, paramstyle, q):
    """
    Check if annotation meets skip-mode criteria:
    1. Has results from at least one non-medmentions model
    2. Models disagree (multiple distinct identifiers OR presence of NULLs)
    """
    c = conn.cursor()

    # Check if there are any non-medmentions results
    sql = q('SELECT COUNT(*) FROM results WHERE idx = ? AND model != \'medmentions\'')
    c.execute(sql, (idx,))
    non_med_count = c.fetchone()[0]

    if non_med_count == 0:
        return False, "No non-medmentions results"

    # Get stats for disagreement check
    sql_stats = q('''
        SELECT
            COUNT(DISTINCT CASE WHEN r.identifier IS NOT NULL THEN r.identifier END) as distinct_identifiers,
            COUNT(CASE WHEN r.identifier IS NULL THEN 1 END) as null_count,
            COUNT(*) as total_models
        FROM results r
        WHERE r.idx = ?
    ''')
    c.execute(sql_stats, (idx,))
    stats = c.fetchone()
    distinct_identifiers, null_count, total_models = stats

    # Skip if all models agree (single identifier, no nulls, multiple models)
    if distinct_identifiers == 1 and null_count == 0 and total_models > 1:
        return False, "All models agree"

    return True, "Meets criteria"

def get_eligible_annotations_for_pmid(pmid, conn, paramstyle, q):
    """Get all annotation indices for a PMID that meet skip-mode criteria."""
    c = conn.cursor()

    # Get all annotation indices for this PMID
    sql = q('SELECT id, original_text FROM recognized_entities WHERE pmid = ?')
    c.execute(sql, (pmid,))
    annotations = c.fetchall()

    eligible = []
    for idx, span_text in annotations:
        meets_criteria, _ = check_skip_criteria(idx, conn, paramstyle, q)
        if meets_criteria:
            eligible.append((idx, span_text))

    return eligible

def load_assignments_from_tsv(tsv_path, conn, paramstyle, q):
    """Load assignments from TSV file (assessor, pmid pairs)."""
    c = conn.cursor()

    total_abstracts = 0
    total_annotations_accepted = 0
    abstracts_with_no_eligible = []

    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')

        for row in reader:
            assessor = row['assessor']
            pmid = row['pmid']
            total_abstracts += 1

            # Get all eligible annotations for this PMID
            eligible_annotations = get_eligible_annotations_for_pmid(pmid, conn, paramstyle, q)

            if not eligible_annotations:
                abstracts_with_no_eligible.append(f"{assessor}:{pmid}")
                continue

            # Insert all eligible annotations as assignments
            for idx, span_text in eligible_annotations:
                try:
                    # For postgres, need to handle ON CONFLICT differently
                    if paramstyle == '%s':
                        sql = '''
                            INSERT INTO assignments (assessor, pmid, idx, span_text, completed)
                            VALUES (%s, %s, %s, %s, false)
                            ON CONFLICT (assessor, idx) DO NOTHING
                        '''
                    else:
                        sql = '''
                            INSERT OR IGNORE INTO assignments (assessor, pmid, idx, span_text, completed)
                            VALUES (?, ?, ?, ?, 0)
                        '''

                    c.execute(sql, (assessor, pmid, idx, span_text))
                    if c.rowcount > 0 or paramstyle == '?':  # SQLite doesn't reliably report rowcount for INSERT OR IGNORE
                        total_annotations_accepted += 1
                except Exception as e:
                    print(f"[ERROR] Failed to insert assignment for {assessor}:{pmid}:{idx}: {e}")

    conn.commit()

    print(f"\n=== Assignment Load Summary ===")
    print(f"Total abstracts processed: {total_abstracts}")
    print(f"Total annotations assigned: {total_annotations_accepted}")
    print(f"Abstracts with no eligible annotations: {len(abstracts_with_no_eligible)}")

    if abstracts_with_no_eligible:
        print(f"\n=== Abstracts with No Eligible Annotations (first 20) ===")
        for i, key in enumerate(abstracts_with_no_eligible[:20]):
            print(f"  {key}")
        if len(abstracts_with_no_eligible) > 20:
            print(f"  ... and {len(abstracts_with_no_eligible) - 20} more")

    return total_annotations_accepted, len(abstracts_with_no_eligible)

def main():
    parser = argparse.ArgumentParser(description='Load annotation assignments from TSV file')
    parser.add_argument('--tsv', required=True, help='Path to TSV file with columns: assessor, pmid')
    parser.add_argument('--backend', choices=['sqlite', 'postgres'], default='sqlite', help='Database backend')

    # SQLite args
    parser.add_argument('--db_path', help='Path to SQLite database (required for sqlite backend)')

    # PostgreSQL args
    parser.add_argument('--host', help='PostgreSQL host')
    parser.add_argument('--port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--dbname', help='PostgreSQL database name')
    parser.add_argument('--user', help='PostgreSQL user')
    parser.add_argument('--password', help='PostgreSQL password')

    args = parser.parse_args()

    # Validate args
    if args.backend == 'sqlite':
        if not args.db_path:
            print("ERROR: --db_path is required for sqlite backend")
            sys.exit(1)
        conn, paramstyle, q = get_db_connection('sqlite', db_path=args.db_path)
    else:  # postgres
        if not all([args.host, args.dbname, args.user, args.password]):
            print("ERROR: --host, --dbname, --user, and --password are required for postgres backend")
            sys.exit(1)
        conn, paramstyle, q = get_db_connection('postgres',
                                                 host=args.host,
                                                 port=args.port,
                                                 dbname=args.dbname,
                                                 user=args.user,
                                                 password=args.password)

    # Load assignments
    load_assignments_from_tsv(args.tsv, conn, paramstyle, q)

    conn.close()
    print("\nDone!")

if __name__ == '__main__':
    main()
