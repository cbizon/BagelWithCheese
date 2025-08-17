import re
import random

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

def get_next_skip_index(index, model, user, conn):
    c = conn.cursor()
    c.execute('''
        SELECT re.id FROM recognized_entities re
        JOIN results r ON re.id = r.idx
        WHERE re.id > ?
        GROUP BY re.id
        HAVING COUNT(DISTINCT CASE WHEN r.model = ? OR r.model = 'medmentions' THEN r.identifier END) > (
            SELECT COUNT(DISTINCT a.identifier)
            FROM assessment a
            WHERE a.idx = re.id AND a.user = ?
              AND a.identifier IN (
                SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions')
              )
        )
    ''', (index, model, user, model))
    row = c.fetchone()
    return row[0] if row else None

def get_prev_skip_index(index, model, user, conn):
    c = conn.cursor()
    c.execute('''
        SELECT re.id FROM recognized_entities re
        JOIN results r ON re.id = r.idx
        WHERE re.id < ?
        GROUP BY re.id
        HAVING COUNT(DISTINCT CASE WHEN (r.model = ? OR r.model = 'medmentions') AND r.identifier IS NOT NULL THEN r.identifier END) > (
            SELECT COUNT(DISTINCT a.identifier)
            FROM assessment a
            WHERE a.idx = re.id AND a.user = ?
              AND a.identifier IN (
                SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions') AND r2.identifier IS NOT NULL
              )
        )
        ORDER BY re.id DESC LIMIT 1
    ''', (index, model, user, model))
    row = c.fetchone()
    return row[0] if row else None

def get_navigation(index, model, user, skip_mode, conn, pmid=None):
    c = conn.cursor()
    prev_index = next_index = None
    prev_abstract_index = next_abstract_index = None
    prev_abstract_url = next_abstract_url = None
    random_annotation_url = random_abstract_url = None
    models = (model, 'medmentions')
    if skip_mode and user:
        next_index = get_next_skip_index(index, model, user, conn)
        prev_index = get_prev_skip_index(index, model, user, conn)
        # Abstract navigation (prev/next) in skip mode
        # Get all eligible pmids in order
        c.execute('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.model = ? OR r.model = 'medmentions' ORDER BY re.pmid''', (model,))
        pmid_rows = c.fetchall()
        pmid_list = [row[0] for row in pmid_rows]
        pmid_pos = pmid_list.index(pmid) if pmid and pmid in pmid_list else None
        # Previous abstract
        prev_abstract_index = None
        if pmid_pos is not None and pmid_pos > 0:
            for p in range(pmid_pos - 1, -1, -1):
                prev_pmid = pmid_list[p]
                # Find eligible recognized_entity for this pmid
                c.execute('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND (r.model = ? OR r.model = 'medmentions') WHERE re.pmid = ? AND (
                    SELECT COUNT(DISTINCT CASE WHEN r2.model = ? OR r2.model = 'medmentions' THEN r2.identifier END) FROM results r2 WHERE r2.idx = re.id AND r2.identifier IS NOT NULL
                ) > (
                    SELECT COUNT(DISTINCT a.identifier) FROM assessment a WHERE a.idx = re.id AND a.user = ? AND a.identifier IN (
                        SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions') AND r2.identifier IS NOT NULL
                    )
                ) ORDER BY re.id ASC''', (model, prev_pmid, model, user, model))
                rows = c.fetchall()
                if rows:
                    prev_abstract_index = rows[0][0]
                    break
        # Next abstract
        next_abstract_index = None
        if pmid_pos is not None and pmid_pos < len(pmid_list) - 1:
            for p in range(pmid_pos + 1, len(pmid_list)):
                next_pmid = pmid_list[p]
                c.execute('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND (r.model = ? OR r.model = 'medmentions') WHERE re.pmid = ? AND (
                    SELECT COUNT(DISTINCT CASE WHEN r2.model = ? OR r2.model = 'medmentions' THEN r2.identifier END) FROM results r2 WHERE r2.idx = re.id AND r2.identifier IS NOT NULL
                ) > (
                    SELECT COUNT(DISTINCT a.identifier) FROM assessment a WHERE a.idx = re.id AND a.user = ? AND a.identifier IN (
                        SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions') AND r2.identifier IS NOT NULL
                    )
                ) ORDER BY re.id ASC''', (model, next_pmid, model, user, model))
                rows = c.fetchall()
                if rows:
                    next_abstract_index = rows[0][0]
                    break
    else:
        valid_indices = get_valid_indices(model, conn)
        if index in valid_indices:
            idx_pos = valid_indices.index(index)
            prev_index = valid_indices[idx_pos - 1] if idx_pos > 0 else None
            next_index = valid_indices[idx_pos + 1] if idx_pos < len(valid_indices) - 1 else None
        # Abstract navigation (prev/next) in non-skip mode
        c.execute('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.model = ? ORDER BY re.pmid''', (model,))
        valid_pmids = [row[0] for row in c.fetchall()]
        pmid_pos = valid_pmids.index(pmid) if pmid and pmid in valid_pmids else None
        prev_abstract_index = next_abstract_index = None
        if pmid_pos is not None:
            if pmid_pos > 0:
                prev_pmid = valid_pmids[pmid_pos - 1]
                c.execute('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.model = ? ORDER BY re.id ASC LIMIT 1''', (prev_pmid, model))
                prev_row = c.fetchone()
                if prev_row:
                    prev_abstract_index = prev_row[0]
            if pmid_pos < len(valid_pmids) - 1:
                next_pmid = valid_pmids[pmid_pos + 1]
                c.execute('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.model = ? ORDER BY re.id ASC LIMIT 1''', (next_pmid, model))
                next_row = c.fetchone()
                if next_row:
                    next_abstract_index = next_row[0]
    return {
        'prev_index': prev_index,
        'next_index': next_index,
        'prev_abstract_index': prev_abstract_index,
        'next_abstract_index': next_abstract_index,
        'prev_abstract_url': None,
        'next_abstract_url': None,
        'random_annotation_url': None,
        'random_abstract_url': None
    }
