from flask import Flask, request, render_template, redirect, url_for, jsonify
import sqlite3
import os
import argparse
import random
import sys
import re

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

def get_abstract_metadata(index, model, conn):
    c = conn.cursor()
    c.execute('SELECT pmid FROM recognized_entities WHERE id = ?', (index,))
    row = c.fetchone()
    if not row:
        return None
    pmid = row[0]
    c.execute('SELECT abstract FROM abstracts WHERE pmid = ?', (pmid,))
    row = c.fetchone()
    abstract = row[0] if row else ''
    c.execute('SELECT identifier FROM results WHERE idx = ? AND model = ?', (index, 'medmentions'))
    medmentions_row = c.fetchone()
    medmentions_id = medmentions_row[0] if medmentions_row and medmentions_row[0] else None
    c.execute('SELECT identifier FROM results WHERE idx = ? AND model = ?', (index, model))
    model_row = c.fetchone()
    model_id = model_row[0] if model_row and model_row[0] else None
    c.execute('SELECT original_text FROM recognized_entities WHERE id = ?', (index,))
    orig_row = c.fetchone()
    original_text = orig_row[0] if orig_row else ''
    identifiers = []
    if medmentions_id and model_id:
        if medmentions_id == model_id:
            identifiers = [medmentions_id]
        else:
            identifiers = [medmentions_id, model_id]
            random.shuffle(identifiers)
    elif medmentions_id:
        identifiers = [medmentions_id]
    elif model_id:
        identifiers = [model_id]
    highlighted_abstract = abstract
    if original_text:
        pattern = re.compile(re.escape(original_text), re.IGNORECASE)
        highlighted_abstract = pattern.sub(
            lambda m: f'<span class="highlighted-entity">{m.group(0)}</span>',
            abstract
        )
    return {
        'pmid': pmid,
        'abstract': abstract,
        'original_text': original_text,
        'identifiers': identifiers,
        'highlighted_abstract': highlighted_abstract
    }

def get_valid_indices(model, conn):
    c = conn.cursor()
    c.execute('SELECT DISTINCT idx FROM results WHERE model = ? ORDER BY idx', (model,))
    return [row[0] for row in c.fetchall()]

def get_identifier_infos(identifiers, conn):
    c = conn.cursor()
    infos = []
    for ident in identifiers:
        c.execute('SELECT label, description, type FROM entities WHERE identifier = ?', (ident,))
        ent_row = c.fetchone()
        label, description, type_ = ent_row if ent_row else ('', '', '')
        infos.append({
            'identifier': ident,
            'label': label,
            'description': description,
            'type': type_
        })
    return infos

def get_user_assessments(index, user, conn):
    c = conn.cursor()
    assessments = {}
    if user:
        c.execute('SELECT identifier, assessment FROM assessment WHERE idx = ? AND user = ?', (index, user))
        for row in c.fetchall():
            assessments[row[0]] = row[1]
    return assessments

def get_navigation(index, model, user, skip_mode, conn, pmid=None):
    c = conn.cursor()
    prev_index = next_index = None
    prev_abstract_url = next_abstract_url = None
    random_annotation_url = random_abstract_url = None
    if skip_mode and user:
        # Next/prev eligible annotation
        c.execute('''
            SELECT re.id FROM recognized_entities re
            JOIN results r ON re.id = r.idx
            WHERE re.id > ? AND r.model = ?
            GROUP BY re.id
            HAVING COUNT(r.identifier) > (
                SELECT COUNT(a.identifier) FROM assessment a WHERE a.idx = re.id AND a.user = ?
            )
            ORDER BY re.id ASC LIMIT 1''', (index, model, user))
        row = c.fetchone()
        next_index = row[0] if row else None
        c.execute('''
            SELECT re.id FROM recognized_entities re
            JOIN results r ON re.id = r.idx
            WHERE re.id < ? AND r.model = ?
            GROUP BY re.id
            HAVING COUNT(r.identifier) > (
                SELECT COUNT(a.identifier) FROM assessment a WHERE a.idx = re.id AND a.user = ?
            )
            ORDER BY re.id DESC LIMIT 1''', (index, model, user))
        row = c.fetchone()
        prev_index = row[0] if row else None
        # Random eligible annotation
        c.execute('''
            SELECT re.id FROM recognized_entities re
            JOIN results r ON re.id = r.idx
            WHERE r.model = ?
            GROUP BY re.id
            HAVING COUNT(r.identifier) > (
                SELECT COUNT(a.identifier) FROM assessment a WHERE a.idx = re.id AND a.user = ?
            )''', (model, user))
        eligible_ids = [row[0] for row in c.fetchall()]
        if eligible_ids:
            random_annotation_url = url_for('show_abstract', index=random.choice(eligible_ids))
        # Abstract navigation (prev/next/random) with skip mode
        c.execute('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.model = ? ORDER BY re.pmid''', (model,))
        pmid_rows = c.fetchall()
        pmid_list = [row[0] for row in pmid_rows]
        pmid_pos = pmid_list.index(pmid) if pmid and pmid in pmid_list else None
        # Previous abstract
        if pmid_pos is not None and pmid_pos > 0:
            for p in range(pmid_pos - 1, -1, -1):
                prev_pmid = pmid_list[p]
                c.execute('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND r.model = ? WHERE re.pmid = ? AND (SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?) > (SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?) ORDER BY re.id ASC''', (model, prev_pmid, model, user))
                rows = c.fetchall()
                if rows:
                    prev_abstract_url = url_for('show_abstract', index=rows[0][0])
                    break
        # Next abstract
        if pmid_pos is not None and pmid_pos < len(pmid_list) - 1:
            for p in range(pmid_pos + 1, len(pmid_list)):
                next_pmid = pmid_list[p]
                c.execute('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND r.model = ? WHERE re.pmid = ? AND (SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?) > (SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?) ORDER BY re.id ASC''', (model, next_pmid, model, user))
                rows = c.fetchall()
                if rows:
                    next_abstract_url = url_for('show_abstract', index=rows[0][0])
                    break
        # Random abstract
        eligible_pmids = []
        for p in pmid_list:
            c.execute('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND r.model = ? WHERE re.pmid = ? AND (SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?) > (SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?) ORDER BY re.id ASC''', (model, p, model, user))
            rows = c.fetchall()
            if rows:
                eligible_pmids.append(p)
        if eligible_pmids:
            random_pmid = random.choice(eligible_pmids)
            c.execute('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND r.model = ? WHERE re.pmid = ? AND (SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?) > (SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?) ORDER BY re.id ASC''', (model, random_pmid, model, user))
            rows = c.fetchall()
            if rows:
                random_abstract_url = url_for('show_abstract', index=random.choice([row[0] for row in rows]))
    else:
        valid_indices = get_valid_indices(model, conn)
        if index in valid_indices:
            idx_pos = valid_indices.index(index)
            prev_index = valid_indices[idx_pos - 1] if idx_pos > 0 else None
            next_index = valid_indices[idx_pos + 1] if idx_pos < len(valid_indices) - 1 else None
        c.execute('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.model = ? ORDER BY re.pmid''', (model,))
        valid_pmids = [row[0] for row in c.fetchall()]
        pmid_pos = valid_pmids.index(pmid) if pmid and pmid in valid_pmids else None
        if pmid_pos is not None:
            if pmid_pos > 0:
                prev_pmid = valid_pmids[pmid_pos - 1]
                c.execute('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.model = ? ORDER BY re.id ASC LIMIT 1''', (prev_pmid, model))
                prev_row = c.fetchone()
                if prev_row:
                    prev_abstract_url = url_for('show_abstract', index=prev_row[0])
            if pmid_pos < len(valid_pmids) - 1:
                next_pmid = valid_pmids[pmid_pos + 1]
                c.execute('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.model = ? ORDER BY re.id ASC LIMIT 1''', (next_pmid, model))
                next_row = c.fetchone()
                if next_row:
                    next_abstract_url = url_for('show_abstract', index=next_row[0])
    return {
        'prev_index': prev_index,
        'next_index': next_index,
        'prev_abstract_url': prev_abstract_url,
        'next_abstract_url': next_abstract_url,
        'random_annotation_url': random_annotation_url,
        'random_abstract_url': random_abstract_url
    }

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
