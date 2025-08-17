from flask import Flask, request, render_template, redirect, url_for, jsonify
import sqlite3
import os
import argparse
import random
import sys
import re
from evaluation_helpers import (
    get_abstract_metadata,
    get_valid_indices,
    get_identifier_infos,
    get_user_assessments,
    get_next_skip_index,
    get_prev_skip_index,
    get_navigation
)

app = Flask(__name__)

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True, help='Model name')
    parser.add_argument('--run', required=True, help='Run name')
    return parser.parse_args()

args = get_args()
app.config['MODEL'] = args.model
app.config['RUN'] = args.run

# Check if model exists in results table before starting the app
run = args.run
model = args.model
db_path = os.path.join('data', run, 'evaluation.db')
if not os.path.exists(db_path):
    print(f"ERROR: Database not found at {db_path}")
    sys.exit(1)
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('SELECT 1 FROM results WHERE model = ? LIMIT 1', (model,))
if not c.fetchone():
    print(f"ERROR: Model '{model}' not found in results table of {db_path}.")
    conn.close()
    sys.exit(1)
conn.close()

@app.route('/<int:index>')
def show_abstract(index):
    run = app.config['RUN']
    model = app.config['MODEL']
    db_path = os.path.join('data', run, 'evaluation.db')
    user = request.cookies.get('user') or request.args.get('user')
    if not os.path.exists(db_path):
        return f'<h2>Database not found at {db_path}</h2>'
    conn = sqlite3.connect(db_path)
    # Get abstract metadata
    metadata = get_abstract_metadata(index, model, conn)
    if not metadata:
        conn.close()
        return f'<h2>No recognized entity with index {index} found.</h2>'
    pmid = metadata['pmid']
    original_text = metadata['original_text']
    identifiers = metadata['identifiers']
    highlighted_abstract = metadata['highlighted_abstract']
    valid_indices = get_valid_indices(model, conn)
    skip_mode = request.cookies.get('skip_mode') == '1'
    navigation = get_navigation(index, model, user, skip_mode, conn, pmid)
    identifier_infos = get_identifier_infos(identifiers, conn) if index in valid_indices and identifiers else []
    user_assessments = get_user_assessments(index, user, conn) if index in valid_indices and identifiers else {}
    conn.close()
    return render_template(
        'abstract.html',
        pmid=pmid,
        abstract=highlighted_abstract,
        identifier_infos=identifier_infos,
        prev_index=navigation['prev_index'],
        next_index=navigation['next_index'],
        current_index=index,
        original_text=original_text,
        user_assessments=user_assessments,
        prev_abstract_url=navigation['prev_abstract_url'],
        next_abstract_url=navigation['next_abstract_url'],
        random_annotation_url=navigation['random_annotation_url'],
        random_abstract_url=navigation['random_abstract_url']
    )

@app.route('/')
def root():
    user = request.cookies.get('user') or request.args.get('user')
    if user:
        return redirect(url_for('show_abstract', index=0, user=user))
    else:
        return redirect(url_for('show_abstract', index=0))

@app.route('/submit_assessment', methods=['POST'])
def submit_assessment():
    data = request.get_json()
    idx = data.get('idx')
    identifier = data.get('identifier')
    user = data.get('user')
    assessment = data.get('assessment')
    run = app.config['RUN']
    db_path = os.path.join('data', run, 'evaluation.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''INSERT INTO assessment (idx, identifier, user, assessment)
                 VALUES (?, ?, ?, ?)
                 ON CONFLICT(idx, identifier, user) DO UPDATE SET assessment=excluded.assessment''',
              (idx, identifier, user, assessment))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/delete_assessment', methods=['POST'])
def delete_assessment():
    data = request.get_json()
    idx = data.get('idx')
    identifier = data.get('identifier')
    user = data.get('user')
    run = app.config['RUN']
    db_path = os.path.join('data', run, 'evaluation.db')
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('DELETE FROM assessment WHERE idx = ? AND identifier = ? AND user = ?', (idx, identifier, user))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted'})

if __name__ == '__main__':
    app.run(debug=True)
