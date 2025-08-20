from flask import Flask, request, render_template, redirect, url_for, jsonify
import sqlite3
import os
import argparse
import sys
import psycopg2
from evaluation_helpers import (
    get_abstract_metadata,
    get_valid_indices,
    get_identifier_infos,
    get_assessor_assessments,
    get_navigation
)

app = Flask(__name__)

def get_args():
    parser = argparse.ArgumentParser()
    # Removed --model argument
    return parser.parse_args()

args = get_args()

def get_db_connection():
    backend = os.environ.get('DB_BACKEND', 'sqlite').lower()
    if backend == 'postgres':
        host = os.environ.get('DB_HOST', 'localhost')
        port = int(os.environ.get('DB_PORT', 5432))
        dbname = os.environ.get('DB_NAME', 'postgres')
        user = os.environ.get('DB_USER', 'postgres')
        password = os.environ.get('DB_PASSWORD', '')
        conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
        paramstyle = '%s'
        db_path = None
    else:
        db_path = os.environ.get('SQLITE_DB_PATH')
        if not db_path:
            print("ERROR: SQLITE_DB_PATH environment variable must be set when using SQLite backend.")
            sys.exit(1)
        if not os.path.exists(db_path):
            print(f"ERROR: Database not found at {db_path}")
            sys.exit(1)
        conn = sqlite3.connect(db_path)
        paramstyle = '?'
    q = (lambda sql: sql.replace('?', '%s')) if paramstyle == '%s' else (lambda sql: sql)
    return conn, conn.cursor(), paramstyle, q, db_path

# Determine the model with the most results and set it in app.config['MODEL']
def get_most_common_model():
    conn, cursor, paramstyle, q, db_path = get_db_connection()
    sql = q("SELECT model, COUNT(*) as cnt FROM results WHERE model != 'medmentions' GROUP BY model ORDER BY cnt DESC LIMIT 1")
    cursor.execute(sql)
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    else:
        print("ERROR: No models (other than medmentions) found in results table.")
        sys.exit(1)

app.config['MODEL'] = get_most_common_model()
print("[INFO] Using model:", app.config['MODEL'])

def get_all_models():
    conn, cursor, paramstyle, q, db_path = get_db_connection()
    sql = q("SELECT DISTINCT model FROM results WHERE model != 'medmentions' ORDER BY model ASC")
    cursor.execute(sql)
    models = [row[0] for row in cursor.fetchall()]
    conn.close()
    return models

@app.route('/<int:index>')
def show_abstract(index):
    models = get_all_models()
    # Determine selected model: query param, cookie, or default
    selected_model = request.args.get('model') or request.cookies.get('selected_model')
    if not selected_model or selected_model not in models:
        selected_model = app.config['MODEL']
    model = selected_model
    conn, _, paramstyle, q, db_path = get_db_connection()
    assessor = request.cookies.get('assessor') or request.args.get('assessor')
    if paramstyle == '?' and not os.path.exists(db_path):
        return f'<h2>Database not found at {db_path}</h2>'
    # Get abstract metadata (assume helpers are compatible)
    metadata = get_abstract_metadata(index, model, conn, paramstyle)
    if not metadata:
        conn.close()
        return f'<h2>No recognized entity with index {index} found.</h2>'
    pmid = metadata['pmid']
    original_text = metadata['original_text']
    identifiers = metadata['identifiers']
    highlighted_abstract = metadata['highlighted_abstract']
    valid_indices = get_valid_indices(model, conn, paramstyle)
    skip_mode = request.cookies.get('skip_mode') == '1'
    navigation = get_navigation(index, model, assessor, skip_mode, conn, pmid, paramstyle)
    identifier_infos = get_identifier_infos(identifiers, conn, paramstyle) if index in valid_indices and identifiers else []
    assessor_assessments = get_assessor_assessments(index, assessor, conn, paramstyle) if index in valid_indices and identifiers else {}
    # Build abstract navigation URLs from indices, preserve model param
    def url_with_model(url, idx):
        return url_for(url, index=idx, model=model) if idx is not None else None
    prev_abstract_url = url_with_model('show_abstract', navigation['prev_abstract_index'])
    next_abstract_url = url_with_model('show_abstract', navigation['next_abstract_index'])
    random_annotation_url = url_with_model('show_abstract', navigation['random_annotation_index'])
    random_abstract_url = url_with_model('show_abstract', navigation['random_abstract_index'])
    conn.close()
    resp = render_template(
        'abstract.html',
        pmid=pmid,
        abstract=highlighted_abstract,
        identifier_infos=identifier_infos,
        prev_index=navigation['prev_index'],
        next_index=navigation['next_index'],
        current_index=index,
        original_text=original_text,
        assessor_assessments=assessor_assessments,
        prev_abstract_url=prev_abstract_url,
        next_abstract_url=next_abstract_url,
        random_annotation_url=random_annotation_url,
        random_abstract_url=random_abstract_url,
        model_name=model,
        models=models,
        selected_model=model
    )
    # Set cookie for selected model
    response = app.make_response(resp)
    response.set_cookie('selected_model', model)
    return response

@app.route('/')
def root():
    assessor = request.cookies.get('assessor') or request.args.get('assessor')
    if assessor:
        return redirect(url_for('show_abstract', index=0, assessor=assessor))
    else:
        return redirect(url_for('show_abstract', index=0))

@app.route('/submit_assessment', methods=['POST'])
def submit_assessment():
    data = request.get_json()
    idx = data.get('idx')
    identifier = data.get('identifier')
    assessor = data.get('assessor')
    assessment = data.get('assessment')
    conn, c, paramstyle, q, _ = get_db_connection()
    try:
        c.execute(q('''INSERT INTO assessment (idx, identifier, assessor, assessment)
                         VALUES (?, ?, ?, ?)
                         ON CONFLICT(idx, identifier, assessor) DO UPDATE SET assessment=excluded.assessment'''),
                  (idx, identifier, assessor, assessment))
        conn.commit()
        # Verification: check if row exists
        c.execute(q('SELECT assessment FROM assessment WHERE idx = ? AND identifier = ? AND assessor = ?'), (idx, identifier, assessor))
        result = c.fetchone()
        if not result:
            print(f"[ERROR] Assessment not saved: idx={idx}, identifier={identifier}, assessor={assessor}")
            return jsonify({'status': 'error', 'message': 'Assessment not saved'}), 500
    except Exception as e:
        print(f"[ERROR] Exception during assessment insert: {e}")
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/delete_assessment', methods=['POST'])
def delete_assessment():
    data = request.get_json()
    idx = data.get('idx')
    identifier = data.get('identifier')
    assessor = data.get('assessor')
    conn, c, paramstyle, q, _ = get_db_connection()
    c.execute(q('DELETE FROM assessment WHERE idx = ? AND identifier = ? AND assessor = ?'), (idx, identifier, assessor))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)
