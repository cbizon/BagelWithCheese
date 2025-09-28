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
    conn, _, paramstyle, q, db_path = get_db_connection()
    assessor = request.cookies.get('assessor') or request.args.get('assessor')
    if paramstyle == '?' and not os.path.exists(db_path):
        return f'<h2>Database not found at {db_path}</h2>'
    # Get abstract metadata (now multi-model)
    metadata = get_abstract_metadata(index, conn, paramstyle)
    if not metadata:
        conn.close()
        return f'<h2>No recognized entity with index {index} found.</h2>'
    pmid = metadata['pmid']
    original_text = metadata['original_text']
    model_results = metadata['model_results']
    highlighted_abstract = metadata['highlighted_abstract']
    valid_indices = get_valid_indices(conn, paramstyle)
    skip_mode = request.cookies.get('skip_mode') == '1'
    navigation = get_navigation(index, assessor, skip_mode, conn, pmid, paramstyle)
    
    # Get all unique identifiers across all models for assessment
    all_identifiers = []
    for model_name, identifiers in model_results.items():
        all_identifiers.extend(identifiers)
    unique_identifiers = list(set(all_identifiers))
    
    identifier_infos = get_identifier_infos(unique_identifiers, conn, paramstyle) if index in valid_indices and unique_identifiers else []
    assessor_assessments = get_assessor_assessments(index, assessor, conn, paramstyle) if index in valid_indices and unique_identifiers else {}
    # Build abstract navigation URLs from indices (no model-specific URLs needed)
    def url_for_index(route, idx):
        return url_for(route, index=idx) if idx is not None else None
    prev_abstract_url = url_for_index('show_abstract', navigation['prev_abstract_index'])
    next_abstract_url = url_for_index('show_abstract', navigation['next_abstract_index'])
    random_annotation_url = url_for_index('show_abstract', navigation['random_annotation_index'])
    random_abstract_url = url_for_index('show_abstract', navigation['random_abstract_index'])
    conn.close()
    return render_template(
        'abstract.html',
        pmid=pmid,
        abstract=highlighted_abstract,
        model_results=model_results,
        identifier_infos=identifier_infos,
        prev_index=navigation['prev_index'],
        next_index=navigation['next_index'],
        current_index=index,
        original_text=original_text,
        assessor_assessments=assessor_assessments,
        prev_abstract_url=prev_abstract_url,
        next_abstract_url=next_abstract_url,
        random_annotation_url=random_annotation_url,
        random_abstract_url=random_abstract_url
    )

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

def calculate_confusion_matrix(model):
    conn, cursor, paramstyle, q, db_path = get_db_connection()
    # Get all indices where medmentions has a result
    sql = q('''
        SELECT mm.idx, mm.identifier as medmentions_id, m.identifier as model_id, m.rowid as model_row_exists
        FROM results mm
        LEFT JOIN results m ON m.idx = mm.idx AND m.model = ?
        WHERE mm.model = 'medmentions' AND mm.identifier IS NOT NULL
    ''')
    cursor.execute(sql, (model,))
    rows = cursor.fetchall()
    summary = {'match': 0, 'disagree': 0, 'null': 0}
    for idx, medmentions_id, model_id, model_row_exists in rows:
        if model_row_exists is None:
            # No row for the model: skip
            continue
        if model_id is None:
            # Model row exists and identifier is NULL
            summary['null'] += 1
        elif model_id == medmentions_id:
            summary['match'] += 1
        else:
            summary['disagree'] += 1
    # Add total for agree/disagree/null percentage calculation
    summary['total'] = summary['match'] + summary['disagree'] + summary['null']
    conn.close()
    return summary

@app.route('/results')
def results_summary():
    assessor = request.cookies.get('assessor') or request.args.get('assessor')
    if not assessor:
        return render_template('results.html', model_summaries=None, assessor=None)
    conn, cursor, paramstyle, q, db_path = get_db_connection()
    # Get all models (excluding medmentions)
    sql_models = q("SELECT DISTINCT model FROM results WHERE model != 'medmentions' ORDER BY model")
    cursor.execute(sql_models)
    models = [row[0] for row in cursor.fetchall()]
    model_summaries = []
    for model in models:
        # Total results for this model
        sql_total = q("SELECT COUNT(*) FROM results WHERE model = ?")
        cursor.execute(sql_total, (model,))
        total = cursor.fetchone()[0]
        # NULLs for this model
        sql_nulls = q("SELECT COUNT(*) FROM results WHERE model = ? AND identifier IS NULL")
        cursor.execute(sql_nulls, (model,))
        null_count = cursor.fetchone()[0]
        null_fraction = (null_count / total) if total > 0 else 0.0
        # Assessed by this user
        sql_assessed = q("""
            SELECT COUNT(DISTINCT r.idx)
            FROM results r
            JOIN assessment a ON r.idx = a.idx AND r.identifier = a.identifier
            WHERE r.model = ? AND a.assessor = ?
        """)
        cursor.execute(sql_assessed, (model, assessor))
        assessed_count = cursor.fetchone()[0]
        # Add confusion matrix
        confusion = calculate_confusion_matrix(model)
        # Add assessment confusion matrix
        assessment_confusion = calculate_confusion_matrix_vs_assessment(model, assessor)
        # Calculate row, column, and grand totals for the assessment confusion matrix
        med_states = ['True', 'False', 'Unsure']
        model_states = ['True', 'False', 'Unsure', 'Null']
        row_totals = {med: sum(assessment_confusion[med][m] for m in model_states) for med in med_states}
        col_totals = {m: sum(assessment_confusion[med][m] for med in med_states) for m in model_states}
        grand_total = sum(row_totals.values())
        model_summaries.append({
            'model': model,
            'total': total,
            'null_count': null_count,
            'null_fraction': null_fraction,
            'assessed_count': assessed_count,
            'confusion_matrix': confusion,
            'assessment_confusion_matrix': assessment_confusion,
            'assessment_confusion_matrix_row_totals': row_totals,
            'assessment_confusion_matrix_col_totals': col_totals,
            'assessment_confusion_matrix_grand_total': grand_total
        })
    conn.close()
    return render_template('results.html', model_summaries=model_summaries, assessor=assessor)

@app.route('/confusion_matrix')
def confusion_matrix():
    # Get selected model from query param or cookie or default
    models = get_all_models()
    selected_model = request.args.get('model') or request.cookies.get('selected_model')
    if not selected_model or selected_model not in models:
        selected_model = app.config['MODEL']
    model = selected_model
    conn, cursor, paramstyle, q, db_path = get_db_connection()
    # Get all rows for this model, with medmentions
    sql = q('''
        SELECT r.idx,
               mm.identifier as medmentions_id,
               m.identifier as model_id
        FROM results r
        LEFT JOIN results mm ON mm.idx = r.idx AND mm.model = 'medmentions'
        LEFT JOIN results m ON m.idx = r.idx AND m.model = ?
        WHERE r.model = 'medmentions' OR r.model = ?
        GROUP BY r.idx
    ''')
    cursor.execute(sql, (model, model))
    rows = cursor.fetchall()
    # Build confusion matrix
    # Rows: medmentions (present, null)
    # Columns: model (agrees, disagrees, is null)
    matrix = {
        'medmentions_present': {'agrees': 0, 'disagrees': 0, 'is_null': 0},
        'medmentions_null': {'agrees': 0, 'disagrees': 0, 'is_null': 0}
    }
    for idx, medmentions_id, model_id in rows:
        medmentions_is_null = medmentions_id is None
        model_is_null = model_id is None
        if medmentions_is_null:
            row_key = 'medmentions_null'
        else:
            row_key = 'medmentions_present'
        if model_is_null:
            col_key = 'is_null'
        elif not medmentions_is_null and model_id == medmentions_id:
            col_key = 'agrees'
        else:
            col_key = 'disagrees'
        matrix[row_key][col_key] += 1
    conn.close()
    return render_template('confusion_matrix.html', matrix=matrix, model=model)

def calculate_confusion_matrix_vs_assessment(model, assessor):
    conn, cursor, paramstyle, q, db_path = get_db_connection()
    # Get all idx with medmentions and model results
    sql = q('''
        SELECT r.idx,
               mm.identifier as medmentions_id,
               m.identifier as model_id
        FROM results r
        LEFT JOIN results mm ON mm.idx = r.idx AND mm.model = 'medmentions'
        LEFT JOIN results m ON m.idx = r.idx AND m.model = ?
        WHERE r.model = 'medmentions' OR r.model = ?
        GROUP BY r.idx
    ''')
    cursor.execute(sql, (model, model))
    rows = cursor.fetchall()
    # Confusion matrix: rows=medmentions (True, False, Unsure), cols=model (True, False, Unsure, Null)
    matrix = {
        'True':    {'True': 0, 'False': 0, 'Unsure': 0, 'Null': 0},
        'False':   {'True': 0, 'False': 0, 'Unsure': 0, 'Null': 0},
        'Unsure':  {'True': 0, 'False': 0, 'Unsure': 0, 'Null': 0},
    }
    from evaluation_helpers import get_assessor_assessments
    for idx, medmentions_id, model_id in rows:
        # If medmentions and model agree (same non-null identifier), both are True
        if medmentions_id is not None and model_id is not None and medmentions_id == model_id:
            matrix['True']['True'] += 1
            continue
        # Otherwise, only consider idx if:
        # - For every non-null result (medmentions or model), there is an assessment for that identifier
        # - There is a result for the model (not missing)
        if model_id is None:
            model_state = 'Null'
        else:
            model_state = None
        # Get all assessments for this idx and assessor
        assessments = get_assessor_assessments(idx, assessor, conn, paramstyle)
        # Check if all non-null results have assessments
        needed = []
        if medmentions_id is not None:
            needed.append(medmentions_id)
        if model_id is not None:
            needed.append(model_id)
        if any(nid not in assessments for nid in needed):
            continue  # skip idx if any assessment missing
        # Map assessment values to states
        def map_assessment(val):
            if val is None:
                return 'Null'
            v = val.lower()
            if v == 'agree':
                return 'True'
            elif v == 'disagree':
                return 'False'
            elif v == 'unsure':
                return 'Unsure'
            return 'Null'
        med_state = map_assessment(assessments.get(medmentions_id)) if medmentions_id is not None else 'Null'
        model_state = map_assessment(assessments.get(model_id)) if model_id is not None else 'Null'
        matrix[med_state][model_state] += 1
    conn.close()
    return matrix

@app.route('/confusion_matrix_assessment')
def confusion_matrix_assessment():
    assessor = request.cookies.get('assessor') or request.args.get('assessor')
    if not assessor:
        return 'Assessor required', 400
    models = get_all_models()
    selected_model = request.args.get('model') or request.cookies.get('selected_model')
    if not selected_model or selected_model not in models:
        selected_model = app.config['MODEL']
    matrix = calculate_confusion_matrix_vs_assessment(selected_model, assessor)
    return render_template('confusion_matrix_assessment.html', matrix=matrix, model=selected_model, assessor=assessor)

if __name__ == '__main__':
    app.run(debug=True)
