from flask import Flask, render_template, jsonify
import json
import os
import sqlite3
import glob
from collections import defaultdict
import argparse

# Set template_folder to the absolute path to ./templates (now inside results_browser_app)
TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=TEMPLATE_DIR)

def init_app(app, run_dir):
    app.config['RUN_DIR'] = run_dir
    db_path = os.path.join(run_dir, 'results.db')
    app.config['DB_CONN'] = sqlite3.connect(db_path, check_same_thread=False)

# Helper to get current run_dir and db connection

def get_run_dir():
    return app.config['RUN_DIR']

def get_conn():
    return app.config['DB_CONN']

def load_results():
    path = os.path.join(get_run_dir(), 'evaluation_summary_all.jsonl')
    results = []
    with open(path) as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results

def load_index_to_pmid():
    path = os.path.join(get_run_dir(), 'annotations-7-30-25.jsonl')
    index_to_pmid = {}
    with open(path) as f:
        for idx, line in enumerate(f):
            if line.strip():
                try:
                    obj = json.loads(line)
                    pmid = obj.get('pmid')
                    if pmid:
                        index_to_pmid[idx] = pmid
                except Exception:
                    continue
    return index_to_pmid

def get_abstract_from_db(pmid):
    c = get_conn().cursor()
    c.execute('SELECT abstract FROM abstracts WHERE pmid=?', (pmid,))
    row = c.fetchone()
    if row:
        return row[0]
    return None

def get_available_thresholds():
    c = get_conn().cursor()
    c.execute('PRAGMA table_info(results)')
    columns = [row[1] for row in c.fetchall()]
    thresholds = set()
    import re
    for col in columns:
        m = re.match(r'exact_matches_(\d+)', col)
        if m:
            thresholds.add(int(m.group(1)))
    return sorted(thresholds)

def load_candidates_for_index(idx, thresholds=None):
    if thresholds is None:
        thresholds = get_available_thresholds()
    base_dir = os.path.join(get_run_dir(), 'parsed_inputs')
    candidates_by_threshold = {}
    entity = None
    for threshold in thresholds:
        filename = f"bodies_{threshold}_colormap.jsonl"
        path = os.path.join(base_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                obj = json.loads(line)
                if obj.get('index') == idx:
                    if entity is None:
                        entity = obj.get('entity')
                    labels = obj.get('labels', {})
                    taxons = obj.get('taxons', {})
                    candidates = []
                    for color, label in labels.items():
                        taxon = taxons.get(color, "")
                        display = f"{label} ({taxon})" if taxon else label
                        candidates.append({'color': color, 'display': display})
                    candidates_by_threshold[str(threshold)] = candidates
                    break
    return candidates_by_threshold, entity

def get_pmid_for_index(idx):
    c = get_conn().cursor()
    c.execute('SELECT pmid FROM index_to_pmid WHERE idx=?', (idx,))
    row = c.fetchone()
    if row:
        return row[0]
    return None

def get_next_prev_indices(idx):
    c = get_conn().cursor()
    c.execute('SELECT next_idx, prev_idx FROM index_sequence WHERE idx=?', (idx,))
    row = c.fetchone()
    if row:
        return row[0], row[1]
    return None, None

def get_exact_color_codes_for_model(idx, threshold, model):
    import glob
    import re
    import os
    pattern = os.path.join(get_run_dir(), 'ollama_results', f'{model}*bodies_{threshold}_response_output.jsonl')
    files = glob.glob(pattern)
    if not files:
        return set()
    color_codes = set()
    with open(files[0]) as f:
        for line in f:
            obj = json.loads(line)
            if obj.get('index') == idx:
                candidates = obj.get('candidates', [])
                for c in candidates:
                    if c.get('relation_type') == 'exact':
                        color_codes.add(c.get('color_code'))
    return color_codes

def get_exact_model_map(idx, threshold):
    """
    For a given index and threshold, return a dict:
      color_code -> set of models that flagged it as exact
    """
    c = get_conn().cursor()
    tstr = str(threshold)
    col = f'exact_matches_{tstr}'
    c.execute(f'SELECT model, {col} FROM results WHERE idx=?', (idx,))
    model_map = defaultdict(set)
    for model, exact_json in c.fetchall():
        if not exact_json:
            continue
        try:
            codes = [code.strip() for code in exact_json.split(',') if code.strip()]
        except Exception:
            codes = []
        for code in codes:
            model_map[code].add(model)
    return model_map

def get_all_models():
    c = get_conn().cursor()
    c.execute('SELECT DISTINCT model FROM results')
    return sorted([row[0] for row in c.fetchall()])

@app.route('/')
@app.route('/<int:idx>')
def index(idx=0):
    thresholds = get_available_thresholds()
    thresholds = [str(t) for t in thresholds]  # Convert to strings for template
    candidates_by_threshold, entity = load_candidates_for_index(idx, thresholds=[int(t) for t in thresholds])
    query = entity
    abstract = None

    pmid = get_pmid_for_index(idx)
    if pmid:
        abstract = get_abstract_from_db(pmid)

    next_idx, prev_idx = get_next_prev_indices(idx)

    # Get model->color_code exact match map for each threshold
    exact_model_maps = {}
    for threshold in thresholds:
        exact_model_maps[threshold] = get_exact_model_map(idx, int(threshold))

    # Get all models in the database for consistent coloring
    all_models = get_all_models()
    palette = [
        '#3cb44b', '#e6194b', '#4363d8', '#ffe119', '#f58231', '#911eb4',
        '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff',
        '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080'
    ]
    model_colors = {model: palette[i % len(palette)] for i, model in enumerate(all_models)}

    if not candidates_by_threshold:
        return '<h2>No candidate data found. Please check your data files.</h2>'
    return render_template('browse.html',
                           candidates_by_threshold=candidates_by_threshold,
                           query=query,
                           abstract=abstract,
                           idx=idx,
                           next_idx=next_idx,
                           prev_idx=prev_idx,
                           exact_model_maps=exact_model_maps,
                           model_colors=model_colors,
                           thresholds=thresholds)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='Run directory name (required)')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)
    init_app(app, run_dir)
    app.run(debug=True)
