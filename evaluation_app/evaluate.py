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

@app.route('/<int:index>')
def show_abstract(index):
    run = app.config['RUN']
    model = app.config['MODEL']
    db_path = os.path.join('data', run, 'evaluation.db')
    user = request.cookies.get('user') or request.args.get('user')
    if not os.path.exists(db_path):
        return f'<h2>Database not found at {db_path}</h2>'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Get max index for navigation
    c.execute('SELECT MAX(id) FROM recognized_entities')
    max_row = c.fetchone()
    max_index = max_row[0] if max_row and max_row[0] is not None else 0
    # Get pmid for the given index from recognized_entities
    c.execute('SELECT pmid FROM recognized_entities WHERE id = ?', (index,))
    row = c.fetchone()
    if not row:
        conn.close()
        return f'<h2>No recognized entity with index {index} found.</h2>'
    pmid = row[0]
    # Get abstract text
    c.execute('SELECT abstract FROM abstracts WHERE pmid = ?', (pmid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return f'<h2>No abstract found for pmid {pmid}.</h2>'
    abstract = row[0]
    # Get identifiers from results table
    c.execute('SELECT identifier FROM results WHERE idx = ? AND model = ?', (index, 'medmentions'))
    medmentions_row = c.fetchone()
    medmentions_id = medmentions_row[0] if medmentions_row and medmentions_row[0] else None
    c.execute('SELECT identifier FROM results WHERE idx = ? AND model = ?', (index, model))
    model_row = c.fetchone()
    model_id = model_row[0] if model_row and model_row[0] else None
    # Get original_text for the given index from recognized_entities
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
    # Highlight all instances of original_text in the abstract
    highlighted_abstract = abstract
    if original_text:
        # Use re.escape to safely match special characters
        pattern = re.compile(re.escape(original_text), re.IGNORECASE)
        highlighted_abstract = pattern.sub(
            lambda m: f'<span class="highlighted-entity">{m.group(0)}</span>',
            abstract
        )
    # Get all valid indices for the current model
    c.execute('SELECT DISTINCT idx FROM results WHERE model = ? ORDER BY idx', (model,))
    valid_indices = [row[0] for row in c.fetchall()]
    # --- Begin skip mode navigation logic ---
    skip_mode = request.cookies.get('skip_mode') == '1'
    if skip_mode and user:
        # Efficient SQL for next unassessed annotation (not fully annotated)
        c.execute('''
            SELECT re.id
            FROM recognized_entities re
            JOIN results r ON re.id = r.idx
            WHERE re.id > ? AND r.model = ?
            GROUP BY re.id
            HAVING COUNT(r.identifier) > (
                SELECT COUNT(a.identifier)
                FROM assessment a
                WHERE a.idx = re.id AND a.user = ?
            )
            ORDER BY re.id ASC
            LIMIT 1
        ''', (index, model, user))
        row = c.fetchone()
        next_index = row[0] if row else None

        # Efficient SQL for previous unassessed annotation (not fully annotated)
        c.execute('''
            SELECT re.id
            FROM recognized_entities re
            JOIN results r ON re.id = r.idx
            WHERE re.id < ? AND r.model = ?
            GROUP BY re.id
            HAVING COUNT(r.identifier) > (
                SELECT COUNT(a.identifier)
                FROM assessment a
                WHERE a.idx = re.id AND a.user = ?
            )
            ORDER BY re.id DESC
            LIMIT 1
        ''', (index, model, user))
        row = c.fetchone()
        prev_index = row[0] if row else None

        # Efficient SQL for all unassessed annotation ids for random
        c.execute('''
            SELECT re.id
            FROM recognized_entities re
            JOIN results r ON re.id = r.idx
            WHERE r.model = ?
            GROUP BY re.id
            HAVING COUNT(r.identifier) > (
                SELECT COUNT(a.identifier)
                FROM assessment a
                WHERE a.idx = re.id AND a.user = ?
            )
        ''', (model, user))
        eligible_ids = [row[0] for row in c.fetchall()]
        random_annotation_url = None
        if eligible_ids:
            random_annotation_index = random.choice(eligible_ids)
            random_annotation_url = url_for('show_abstract', index=random_annotation_index)
        else:
            random_annotation_url = None

        # Abstract navigation (prev/next/random) with skip mode
        prev_abstract_url = None
        next_abstract_url = None
        random_abstract_url = None
        # Get all pmids with at least one result for this model
        c.execute('''SELECT DISTINCT re.pmid FROM recognized_entities re
                     JOIN results r ON re.id = r.idx
                     WHERE r.model = ?
                     ORDER BY re.pmid''', (model,))
        pmid_rows = c.fetchall()
        pmid_list = [row[0] for row in pmid_rows]
        try:
            pmid_pos = pmid_list.index(pmid)
        except ValueError:
            pmid_pos = None
        # Previous abstract
        if pmid_pos is not None and pmid_pos > 0:
            for p in range(pmid_pos - 1, -1, -1):
                prev_pmid = pmid_list[p]
                c.execute('''SELECT re.id FROM recognized_entities re
                             LEFT JOIN results r ON re.id = r.idx AND r.model = ?
                             WHERE re.pmid = ? AND (
                                 SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?
                             ) > (
                                 SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?
                             )
                             ORDER BY re.id ASC''', (model, prev_pmid, model, user))
                rows = c.fetchall()
                for row in rows:
                    prev_abstract_url = url_for('show_abstract', index=row[0])
                    break
                if prev_abstract_url:
                    break

        # Next abstract
        if pmid_pos is not None and pmid_pos < len(pmid_list) - 1:
            for p in range(pmid_pos + 1, len(pmid_list)):
                next_pmid = pmid_list[p]
                c.execute('''SELECT re.id FROM recognized_entities re
                             LEFT JOIN results r ON re.id = r.idx AND r.model = ?
                             WHERE re.pmid = ? AND (
                                 SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?
                             ) > (
                                 SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?
                             )
                             ORDER BY re.id ASC''', (model, next_pmid, model, user))
                rows = c.fetchall()
                for row in rows:
                    next_abstract_url = url_for('show_abstract', index=row[0])
                    break
                if next_abstract_url:
                    break
        # Random abstract: pick a random pmid with at least one eligible annotation
        eligible_pmids = []
        for p in pmid_list:
            c.execute('''SELECT re.id FROM recognized_entities re
                         LEFT JOIN results r ON re.id = r.idx AND r.model = ?
                         WHERE re.pmid = ? AND (
                             SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?
                         ) > (
                             SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?
                         )
                         ORDER BY re.id ASC''', (model, p, model, user))
            rows = c.fetchall()
            if rows:
                eligible_pmids.append(p)
        if eligible_pmids:
            random_pmid = random.choice(eligible_pmids)
            c.execute('''SELECT re.id FROM recognized_entities re
                         LEFT JOIN results r ON re.id = r.idx AND r.model = ?
                         WHERE re.pmid = ? AND (
                             SELECT COUNT(*) FROM results r2 WHERE r2.idx = re.id AND r2.model = ?
                         ) > (
                             SELECT COUNT(*) FROM assessment a WHERE a.idx = re.id AND a.user = ?
                         )
                         ORDER BY re.id ASC''', (model, random_pmid, model, user))
            rows = c.fetchall()
            if rows:
                random_abstract_url = url_for('show_abstract', index=random.choice([row[0] for row in rows]))
    else:
        # Non-skip mode navigation logic
        if index in valid_indices:
            idx_pos = valid_indices.index(index)
            prev_index = valid_indices[idx_pos - 1] if idx_pos > 0 else None
            next_index = valid_indices[idx_pos + 1] if idx_pos < len(valid_indices) - 1 else None
        else:
            prev_index = None
            next_index = None
    # Identifier and user assessment logic (moved outside of skip/non-skip mode branches)
    identifier_infos = []
    user_assessments = {}
    if index in valid_indices and identifiers:
        for ident in identifiers:
            c.execute('SELECT label, description, type FROM entities WHERE identifier = ?', (ident,))
            ent_row = c.fetchone()
            label, description, type_ = ent_row if ent_row else ('', '', '')
            identifier_infos.append({
                'identifier': ident,
                'label': label,
                'description': description,
                'type': type_
            })
        if user:
            c.execute('SELECT identifier, assessment FROM assessment WHERE idx = ? AND user = ?', (index, user))
            for row in c.fetchall():
                user_assessments[row[0]] = row[1]
    conn.close()
    # --- Navigation logic ---
    skip_mode = request.cookies.get('skip_mode') == '1'
    # Ensure all navigation variables are defined
    prev_index = locals().get('prev_index', None)
    next_index = locals().get('next_index', None)
    prev_abstract_url = locals().get('prev_abstract_url', None)
    next_abstract_url = locals().get('next_abstract_url', None)
    random_annotation_url = locals().get('random_annotation_url', None)
    random_abstract_url = locals().get('random_abstract_url', None)
    return render_template('abstract.html', pmid=pmid, abstract=highlighted_abstract, identifier_infos=identifier_infos, prev_index=prev_index, next_index=next_index, current_index=index, original_text=original_text, user_assessments=user_assessments, prev_abstract_url=prev_abstract_url, next_abstract_url=next_abstract_url, random_annotation_url=random_annotation_url, random_abstract_url=random_abstract_url)

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
