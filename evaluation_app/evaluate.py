from flask import Flask, request, render_template, redirect, url_for, jsonify
import sqlite3
import os
import argparse
import sys
import psycopg2
import requests
from evaluation_helpers import (
    get_abstract_metadata,
    get_valid_indices,
    get_identifier_infos,
    get_assessor_assessments,
    get_navigation,
    check_has_assignments,
    get_assignment_stats,
    get_next_uncompleted_assignment,
    get_prev_uncompleted_assignment
)

app = Flask(__name__)

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000, help='Port to run the Flask app on')
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

    # Check assignment mode
    has_assignments = check_has_assignments(assessor, conn, paramstyle)
    assignment_stats = get_assignment_stats(assessor, conn, paramstyle) if has_assignments else None

    # Get uncompleted navigation for assignment mode
    next_uncompleted = get_next_uncompleted_assignment(index, assessor, conn, paramstyle) if has_assignments else None
    prev_uncompleted = get_prev_uncompleted_assignment(index, assessor, conn, paramstyle) if has_assignments else None

    # Build abstract navigation URLs from indices (no model-specific URLs needed)
    def url_for_index(route, idx):
        return url_for(route, index=idx) if idx is not None else None
    prev_abstract_url = url_for_index('show_abstract', navigation['prev_abstract_index'])
    next_abstract_url = url_for_index('show_abstract', navigation['next_abstract_index'])
    random_annotation_url = url_for_index('show_abstract', navigation['random_annotation_index'])
    random_abstract_url = url_for_index('show_abstract', navigation['random_abstract_index'])
    next_uncompleted_url = url_for_index('show_abstract', next_uncompleted)
    prev_uncompleted_url = url_for_index('show_abstract', prev_uncompleted)

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
        random_abstract_url=random_abstract_url,
        has_assignments=has_assignments,
        assignment_stats=assignment_stats,
        next_uncompleted_url=next_uncompleted_url,
        prev_uncompleted_url=prev_uncompleted_url
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

        # Check if assignment should be marked complete
        update_assignment_completion(idx, assessor, conn, c, paramstyle, q)

    except Exception as e:
        print(f"[ERROR] Exception during assessment insert: {e}")
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    conn.close()
    return jsonify({'status': 'success'})

def update_assignment_completion(idx, assessor, conn, c, paramstyle, q):
    """Check if all non-NULL identifiers for this annotation are assessed, and mark assignment complete if so."""
    # Check if this idx is in assignments for this assessor
    c.execute(q('SELECT COUNT(*) FROM assignments WHERE idx = ? AND assessor = ?'), (idx, assessor))
    if c.fetchone()[0] == 0:
        return  # Not an assigned annotation

    # Get all non-NULL identifiers for this idx
    c.execute(q('SELECT DISTINCT identifier FROM results WHERE idx = ? AND identifier IS NOT NULL'), (idx,))
    all_identifiers = [row[0] for row in c.fetchall()]

    # Get all assessed identifiers for this idx and assessor
    c.execute(q('SELECT DISTINCT identifier FROM assessment WHERE idx = ? AND assessor = ?'), (idx, assessor))
    assessed_identifiers = set(row[0] for row in c.fetchall())

    # Check if all identifiers are assessed
    all_assessed = all(ident in assessed_identifiers for ident in all_identifiers)

    if all_assessed:
        # Mark assignment as complete
        if paramstyle == '%s':
            c.execute('UPDATE assignments SET completed = true WHERE idx = %s AND assessor = %s', (idx, assessor))
        else:
            c.execute('UPDATE assignments SET completed = 1 WHERE idx = ? AND assessor = ?', (idx, assessor))
        conn.commit()
        print(f"[INFO] Marked assignment idx={idx} as complete for assessor={assessor}")

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
        SELECT mm.idx, mm.identifier as medmentions_id, m.identifier as model_id,
               CASE WHEN m.idx IS NOT NULL THEN 1 ELSE 0 END as model_row_exists
        FROM results mm
        LEFT JOIN results m ON m.idx = mm.idx AND m.model = ?
        WHERE mm.model = 'medmentions' AND mm.identifier IS NOT NULL
    ''')
    cursor.execute(sql, (model,))
    rows = cursor.fetchall()
    summary = {'match': 0, 'disagree': 0, 'null': 0}
    for idx, medmentions_id, model_id, model_row_exists in rows:
        if model_row_exists == 0:
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
        # Add confusion matrix (global, no assessor)
        confusion = calculate_confusion_matrix(model)

        # Get all assessors who have assessed this model
        sql_assessors = q("""
            SELECT DISTINCT a.assessor
            FROM assessment a
            JOIN results r ON a.idx = r.idx AND a.identifier = r.identifier
            WHERE r.model = ?
            ORDER BY a.assessor
        """)
        cursor.execute(sql_assessors, (model,))
        assessors = [row[0] for row in cursor.fetchall()]

        # Build assessment confusion matrices for each assessor
        assessor_matrices = []
        for assess in assessors:
            assessment_confusion = calculate_confusion_matrix_vs_assessment(model, assess)
            # Calculate row, column, and grand totals for the assessment confusion matrix
            med_states = ['True', 'False', 'Unsure']
            model_states = ['True', 'False', 'Unsure', 'Null']
            row_totals = {med: sum(assessment_confusion[med][m] for m in model_states) for med in med_states}
            col_totals = {m: sum(assessment_confusion[med][m] for med in med_states) for m in model_states}
            grand_total = sum(row_totals.values())
            assessor_matrices.append({
                'assessor': assess,
                'matrix': assessment_confusion,
                'row_totals': row_totals,
                'col_totals': col_totals,
                'grand_total': grand_total
            })

        model_summaries.append({
            'model': model,
            'total': total,
            'confusion_matrix': confusion,
            'assessor_matrices': assessor_matrices
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

    # Use a single aggregating query instead of looping
    sql = q('''
        WITH combined AS (
            SELECT
                COALESCE(mm.idx, m.idx) as idx,
                mm.identifier as medmentions_id,
                m.identifier as model_id
            FROM
                (SELECT idx, identifier FROM results WHERE model = 'medmentions') mm
            FULL OUTER JOIN
                (SELECT idx, identifier FROM results WHERE model = ?) m
            ON mm.idx = m.idx
        )
        SELECT
            SUM(CASE WHEN medmentions_id IS NOT NULL AND model_id IS NOT NULL AND medmentions_id = model_id THEN 1 ELSE 0 END) as medmentions_present_agrees,
            SUM(CASE WHEN medmentions_id IS NOT NULL AND model_id IS NOT NULL AND medmentions_id != model_id THEN 1 ELSE 0 END) as medmentions_present_disagrees,
            SUM(CASE WHEN medmentions_id IS NOT NULL AND model_id IS NULL THEN 1 ELSE 0 END) as medmentions_present_is_null,
            SUM(CASE WHEN medmentions_id IS NULL AND model_id IS NOT NULL AND model_id = medmentions_id THEN 1 ELSE 0 END) as medmentions_null_agrees,
            SUM(CASE WHEN medmentions_id IS NULL AND model_id IS NOT NULL AND model_id != medmentions_id THEN 1 ELSE 0 END) as medmentions_null_disagrees,
            SUM(CASE WHEN medmentions_id IS NULL AND model_id IS NULL THEN 1 ELSE 0 END) as medmentions_null_is_null
        FROM combined
    ''')
    cursor.execute(sql, (model,))
    row = cursor.fetchone()

    matrix = {
        'medmentions_present': {
            'agrees': row[0] or 0,
            'disagrees': row[1] or 0,
            'is_null': row[2] or 0
        },
        'medmentions_null': {
            'agrees': row[3] or 0,
            'disagrees': row[4] or 0,
            'is_null': row[5] or 0
        }
    }
    conn.close()
    return render_template('confusion_matrix.html', matrix=matrix, model=model)

def calculate_confusion_matrix_vs_assessment(model, assessor):
    conn, cursor, paramstyle, q, db_path = get_db_connection()

    # Initialize matrix
    matrix = {
        'True':    {'True': 0, 'False': 0, 'Unsure': 0, 'Null': 0},
        'False':   {'True': 0, 'False': 0, 'Unsure': 0, 'Null': 0},
        'Unsure':  {'True': 0, 'False': 0, 'Unsure': 0, 'Null': 0},
    }

    # First, count cases where identifiers match (both True)
    sql_match = q('''
        SELECT COUNT(*)
        FROM results mm
        JOIN results m ON mm.idx = m.idx AND mm.identifier = m.identifier
        WHERE mm.model = 'medmentions' AND m.model = ?
          AND mm.identifier IS NOT NULL AND m.identifier IS NOT NULL
    ''')
    cursor.execute(sql_match, (model,))
    matrix['True']['True'] = cursor.fetchone()[0]

    # For disagreements, we need assessment data
    # Get all cases where identifiers differ or one is NULL, with assessment info
    sql_assessed = q('''
        WITH paired_results AS (
            SELECT
                COALESCE(mm.idx, m.idx) as idx,
                mm.identifier as medmentions_id,
                m.identifier as model_id
            FROM
                (SELECT idx, identifier FROM results WHERE model = 'medmentions') mm
            FULL OUTER JOIN
                (SELECT idx, identifier FROM results WHERE model = ?) m
            ON mm.idx = m.idx
            WHERE NOT (mm.identifier IS NOT NULL AND m.identifier IS NOT NULL AND mm.identifier = m.identifier)
        ),
        assessments_agg AS (
            SELECT
                idx,
                identifier,
                MAX(CASE WHEN assessor = ? THEN assessment END) as assessment
            FROM assessment
            GROUP BY idx, identifier
        )
        SELECT
            pr.idx,
            pr.medmentions_id,
            pr.model_id,
            a_mm.assessment as mm_assessment,
            a_m.assessment as m_assessment
        FROM paired_results pr
        LEFT JOIN assessments_agg a_mm ON pr.idx = a_mm.idx AND pr.medmentions_id = a_mm.identifier
        LEFT JOIN assessments_agg a_m ON pr.idx = a_m.idx AND pr.model_id = a_m.identifier
        WHERE (
            (pr.medmentions_id IS NULL OR a_mm.assessment IS NOT NULL) AND
            (pr.model_id IS NULL OR a_m.assessment IS NOT NULL)
        )
    ''')
    cursor.execute(sql_assessed, (model, assessor))

    # Process results and categorize
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

    for row in cursor.fetchall():
        idx, medmentions_id, model_id, mm_assessment, m_assessment = row

        med_state = map_assessment(mm_assessment) if medmentions_id is not None else 'Null'
        model_state = map_assessment(m_assessment) if model_id is not None else 'Null'

        # Only count if we have valid row state (not Null for medmentions)
        if med_state in matrix:
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

@app.route('/manage_assignments')
def manage_assignments():
    """Page for uploading and managing assignments."""
    return render_template('manage_assignments.html')

@app.route('/get_assignments')
def get_assignments():
    """Get current assignments from database."""
    conn, c, paramstyle, q, _ = get_db_connection()

    # Get summary by assessor and pmid
    sql = q('''
        SELECT
            assessor,
            pmid,
            COUNT(*) as total,
            SUM(CASE WHEN completed = ? THEN 1 ELSE 0 END) as completed,
            COUNT(*) - SUM(CASE WHEN completed = ? THEN 1 ELSE 0 END) as remaining
        FROM assignments
        GROUP BY assessor, pmid
        ORDER BY assessor, pmid
    ''')

    if paramstyle == '%s':
        c.execute(sql.replace('?', '%s'), (True, True))
    else:
        c.execute(sql, (1, 1))

    summary = []
    for row in c.fetchall():
        summary.append({
            'assessor': row[0],
            'pmid': row[1],
            'total': row[2],
            'completed': row[3],
            'remaining': row[4]
        })

    # Get total counts
    c.execute(q('SELECT COUNT(*) FROM assignments'))
    total_assignments = c.fetchone()[0]

    c.execute(q('SELECT COUNT(DISTINCT assessor) FROM assignments'))
    total_assessors = c.fetchone()[0]

    c.execute(q('SELECT COUNT(DISTINCT assessor || \':\' || pmid) FROM assignments'))
    total_abstract_assignments = c.fetchone()[0]

    conn.close()

    return jsonify({
        'summary': summary,
        'total_assignments': total_assignments,
        'total_assessors': total_assessors,
        'total_abstract_assignments': total_abstract_assignments
    })

@app.route('/upload_assignments', methods=['POST'])
def upload_assignments():
    """Handle TSV upload for assignments."""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected'}), 400

    if not file.filename.endswith('.tsv'):
        return jsonify({'status': 'error', 'message': 'File must be a .tsv file'}), 400

    try:
        # Read TSV content
        content = file.read().decode('utf-8')
        lines = content.strip().split('\n')

        if len(lines) < 2:
            return jsonify({'status': 'error', 'message': 'TSV file must have header and at least one row'}), 400

        # Parse header
        header = lines[0].split('\t')
        if header != ['assessor', 'pmid']:
            return jsonify({'status': 'error', 'message': 'TSV must have columns: assessor, pmid'}), 400

        conn, c, paramstyle, q, _ = get_db_connection()

        total_abstracts = 0
        total_annotations_accepted = 0
        abstracts_with_no_eligible = []

        # Process each row
        for line in lines[1:]:
            if not line.strip():
                continue

            parts = line.split('\t')
            if len(parts) != 2:
                continue

            assessor, pmid = parts[0].strip(), parts[1].strip()
            total_abstracts += 1

            # Get all eligible annotations for this PMID
            eligible_annotations = get_eligible_annotations_for_pmid(pmid, conn, c, paramstyle, q)

            if not eligible_annotations:
                abstracts_with_no_eligible.append(f"{assessor}:{pmid}")
                continue

            # Insert all eligible annotations as assignments
            for idx, span_text in eligible_annotations:
                try:
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
                    total_annotations_accepted += 1
                except Exception as e:
                    print(f"[ERROR] Failed to insert assignment for {assessor}:{pmid}:{idx}: {e}")

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'total_abstracts': total_abstracts,
            'total_annotations': total_annotations_accepted,
            'abstracts_with_no_eligible': len(abstracts_with_no_eligible),
            'abstracts_with_no_eligible_list': abstracts_with_no_eligible[:20]
        })

    except Exception as e:
        print(f"[ERROR] Exception during assignment upload: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

def get_eligible_annotations_for_pmid(pmid, conn, c, paramstyle, q):
    """Get all annotation indices for a PMID that meet skip-mode criteria."""
    # Get all annotation indices for this PMID
    sql = q('SELECT id, original_text FROM recognized_entities WHERE pmid = ?')
    c.execute(sql, (pmid,))
    annotations = c.fetchall()

    eligible = []
    for idx, span_text in annotations:
        if check_skip_criteria_for_idx(idx, conn, c, paramstyle, q):
            eligible.append((idx, span_text))

    return eligible

def check_skip_criteria_for_idx(idx, conn, c, paramstyle, q):
    """Check if annotation meets skip-mode criteria."""
    # Check if there are any non-medmentions results
    sql = q('SELECT COUNT(*) FROM results WHERE idx = ? AND model != \'medmentions\'')
    c.execute(sql, (idx,))
    non_med_count = c.fetchone()[0]

    if non_med_count == 0:
        return False

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
        return False

    return True

@app.route('/assessor_agreement')
def assessor_agreement():
    """Show inter-rater agreement matrix for all assessors."""
    conn, cursor, paramstyle, q, db_path = get_db_connection()

    # Get all assessors who have made assessments
    sql_assessors = q("SELECT DISTINCT assessor FROM assessment ORDER BY assessor")
    cursor.execute(sql_assessors)
    assessors = [row[0] for row in cursor.fetchall()]

    # Build agreement matrix
    agreement_matrix = {}
    for assessor_a in assessors:
        agreement_matrix[assessor_a] = {}
        for assessor_b in assessors:
            if assessor_a == assessor_b:
                # Same assessor - 100% agreement with themselves
                agreement_matrix[assessor_a][assessor_b] = {'shared': 0, 'agreed': 0, 'fraction': 1.0}
            else:
                # Find shared assessments (same idx and identifier)
                sql_shared = q('''
                    SELECT a1.idx, a1.identifier, a1.assessment, a2.assessment
                    FROM assessment a1
                    JOIN assessment a2 ON a1.idx = a2.idx AND a1.identifier = a2.identifier
                    WHERE a1.assessor = ? AND a2.assessor = ?
                ''')
                cursor.execute(sql_shared, (assessor_a, assessor_b))
                shared = cursor.fetchall()

                shared_count = len(shared)
                agreed_count = sum(1 for row in shared if row[2] == row[3])
                fraction = (agreed_count / shared_count) if shared_count > 0 else 0.0

                agreement_matrix[assessor_a][assessor_b] = {
                    'shared': shared_count,
                    'agreed': agreed_count,
                    'fraction': fraction
                }

    conn.close()
    return render_template('assessor_agreement.html', assessors=assessors, agreement_matrix=agreement_matrix)

@app.route('/babel_info/<path:curie>')
def babel_info(curie):
    """Fetch combined nodenorm and nameres data for a CURIE."""
    try:
        # Call nodenormalizer
        nodenorm_url = 'https://nodenormalization-sri.renci.org/get_normalized_nodes'
        nodenorm_payload = {
            "curies": [curie],
            "conflate": True,
            "description": False,
            "drug_chemical_conflate": True
        }
        nodenorm_response = requests.post(nodenorm_url, json=nodenorm_payload, timeout=10)
        nodenorm_data = nodenorm_response.json() if nodenorm_response.status_code == 200 else {}

        # Extract preferred CURIE for nameres (nameres requires preferred ID)
        preferred_curie = curie
        if curie in nodenorm_data and nodenorm_data[curie] and 'id' in nodenorm_data[curie]:
            preferred_curie = nodenorm_data[curie]['id']['identifier']

        # Call name resolver for synonyms - using the correct payload format
        nameres_url = 'https://name-resolution-sri.renci.org/synonyms'
        nameres_payload = {
            "preferred_curies": [preferred_curie]
        }
        nameres_response = requests.post(nameres_url, json=nameres_payload, timeout=10)
        nameres_data = nameres_response.json() if nameres_response.status_code == 200 else {}

        print(f"[DEBUG] CURIE: {curie}, Preferred: {preferred_curie}")
        print(f"[DEBUG] Nameres response status: {nameres_response.status_code}")
        print(f"[DEBUG] Nameres data keys: {list(nameres_data.keys())}")

        return jsonify({
            'status': 'success',
            'curie': curie,
            'preferred_curie': preferred_curie,
            'nodenorm': nodenorm_data.get(curie, {}),
            'nameres': nameres_data.get(preferred_curie, {})
        })
    except Exception as e:
        print(f"[ERROR] Babel info error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=args.port)
