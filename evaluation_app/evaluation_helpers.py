import re
import random

def get_abstract_metadata(index, model, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    c.execute(q('SELECT pmid FROM recognized_entities WHERE id = ?'), (index,))
    row = c.fetchone()
    if not row:
        return None
    pmid = row[0]
    c.execute(q('SELECT abstract FROM abstracts WHERE pmid = ?'), (pmid,))
    row = c.fetchone()
    abstract = row[0] if row else ''
    c.execute(q('SELECT identifier FROM results WHERE idx = ? AND model = ?'), (index, 'medmentions'))
    medmentions_row = c.fetchone()
    medmentions_id = medmentions_row[0] if medmentions_row and medmentions_row[0] else None
    c.execute(q('SELECT identifier FROM results WHERE idx = ? AND model = ?'), (index, model))
    model_row = c.fetchone()
    model_id = model_row[0] if model_row and model_row[0] else None
    c.execute(q('SELECT original_text FROM recognized_entities WHERE id = ?'), (index,))
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

def get_valid_indices(model, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    c.execute(q('SELECT DISTINCT idx FROM results WHERE model = ? ORDER BY idx'), (model,))
    return [row[0] for row in c.fetchall()]

def get_identifier_infos(identifiers, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    infos = []
    for ident in identifiers:
        c.execute(q('SELECT label, description, type FROM entities WHERE identifier = ?'), (ident,))
        ent_row = c.fetchone()
        label, description, type_ = ent_row if ent_row else ('', '', '')
        infos.append({
            'identifier': ident,
            'label': label,
            'description': description,
            'type': type_
        })
    return infos

def get_assessor_assessments(index, assessor, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    assessments = {}
    if assessor:
        c.execute(q('SELECT identifier, assessment FROM assessment WHERE idx = ? AND assessor = ?'), (index, assessor))
        for row in c.fetchall():
            assessments[row[0]] = row[1]
    return assessments

def get_next_skip_index(index, model, assessor, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    sql = q('''
        SELECT re.id FROM recognized_entities re
        JOIN results r ON re.id = r.idx
        WHERE re.id > ?
        GROUP BY re.id
        HAVING SUM(CASE WHEN r.model = ? THEN 1 ELSE 0 END) > 0
           AND SUM(CASE WHEN r.model = 'medmentions' THEN 1 ELSE 0 END) > 0
           AND (
                SELECT r1.identifier FROM results r1 WHERE r1.idx = re.id AND r1.model = ?
            ) <> (
                SELECT r2.identifier FROM results r2 WHERE r2.idx = re.id AND r2.model = 'medmentions'
            )
           AND COUNT(DISTINCT CASE WHEN r.model = ? OR r.model = 'medmentions' THEN r.identifier END) > (
                SELECT COUNT(DISTINCT a.identifier)
                FROM assessment a
                WHERE a.idx = re.id AND a.assessor = ?
                  AND a.identifier IN (
                    SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions')
                  )
            )
        ORDER BY re.id ASC LIMIT 1
    ''')
    c.execute(sql, (index, model, model, model, assessor, model))
    row = c.fetchone()
    return row[0] if row else None

def get_prev_skip_index(index, model, assessor, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    sql = q('''
        SELECT re.id FROM recognized_entities re
        JOIN results r ON re.id = r.idx
        WHERE re.id < ?
        GROUP BY re.id
        HAVING SUM(CASE WHEN r.model = ? THEN 1 ELSE 0 END) > 0
           AND SUM(CASE WHEN r.model = 'medmentions' THEN 1 ELSE 0 END) > 0
           AND (
                SELECT r1.identifier FROM results r1 WHERE r1.idx = re.id AND r1.model = ?
            ) <> (
                SELECT r2.identifier FROM results r2 WHERE r2.idx = re.id AND r2.model = 'medmentions'
            )
           AND COUNT(DISTINCT CASE WHEN r.model = ? OR r.model = 'medmentions' THEN r.identifier END) > (
                SELECT COUNT(DISTINCT a.identifier)
                FROM assessment a
                WHERE a.idx = re.id AND a.assessor = ?
                  AND a.identifier IN (
                    SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions')
                  )
            )
        ORDER BY re.id DESC LIMIT 1
    ''')
    c.execute(sql, (index, model, model, model, assessor, model))
    row = c.fetchone()
    return row[0] if row else None

def get_navigation(index, model, assessor, skip_mode, conn, pmid=None, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    prev_index = next_index = None
    prev_abstract_index = next_abstract_index = None
    prev_abstract_url = next_abstract_url = None
    random_annotation_index = random_abstract_index = None
    if skip_mode and assessor:
        next_index = get_next_skip_index(index, model, assessor, conn, paramstyle)
        print(f"Next index in skip mode: {next_index}")
        prev_index = get_prev_skip_index(index, model, assessor, conn, paramstyle)
        # Abstract navigation (prev/next) in skip mode
        # Get all eligible pmids in order
        sql = q('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.model = ? OR r.model = 'medmentions' ORDER BY re.pmid''')
        c.execute(sql, (model,))
        pmid_rows = c.fetchall()
        pmid_list = [row[0] for row in pmid_rows]
        pmid_pos = pmid_list.index(pmid) if pmid and pmid in pmid_list else None
        # Previous abstract
        prev_abstract_index = None
        if pmid_pos is not None and pmid_pos > 0:
            for p in range(pmid_pos - 1, -1, -1):
                prev_pmid = pmid_list[p]
                sql = q('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND (r.model = ? OR r.model = 'medmentions') WHERE re.pmid = ? AND (
                    SELECT COUNT(DISTINCT CASE WHEN r2.model = ? OR r2.model = 'medmentions' THEN r2.identifier END) FROM results r2 WHERE r2.idx = re.id AND r2.identifier IS NOT NULL
                ) > (
                    SELECT COUNT(DISTINCT a.identifier) FROM assessment a WHERE a.idx = re.id AND a.assessor = ? AND a.identifier IN (
                        SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions') AND r2.identifier IS NOT NULL
                    )
                ) ORDER BY re.id ASC''')
                c.execute(sql, (model, prev_pmid, model, assessor, model))
                rows = c.fetchall()
                if rows:
                    prev_abstract_index = rows[0][0]
                    break
        # Next abstract
        next_abstract_index = None
        if pmid_pos is not None and pmid_pos < len(pmid_list) - 1:
            for p in range(pmid_pos + 1, len(pmid_list)):
                next_pmid = pmid_list[p]
                sql = q('''SELECT re.id FROM recognized_entities re LEFT JOIN results r ON re.id = r.idx AND (r.model = ? OR r.model = 'medmentions') WHERE re.pmid = ? AND (
                    SELECT COUNT(DISTINCT CASE WHEN r2.model = ? OR r2.model = 'medmentions' THEN r2.identifier END) FROM results r2 WHERE r2.idx = re.id AND r2.identifier IS NOT NULL
                ) > (
                    SELECT COUNT(DISTINCT a.identifier) FROM assessment a WHERE a.idx = re.id AND a.assessor = ? AND a.identifier IN (
                        SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions') AND r2.identifier IS NOT NULL
                    )
                ) ORDER BY re.id ASC''')
                c.execute(sql, (model, next_pmid, model, assessor, model))
                rows = c.fetchall()
                if rows:
                    next_abstract_index = rows[0][0]
                    break
        # Fast random eligible annotation for current model
        sql = q('''
            SELECT re.id FROM recognized_entities re
            JOIN results r ON re.id = r.idx
            GROUP BY re.id
            HAVING COUNT(DISTINCT CASE WHEN (r.model = ? OR r.model = 'medmentions') AND r.identifier IS NOT NULL THEN r.identifier END) > (
                SELECT COUNT(DISTINCT a.identifier)
                FROM assessment a
                WHERE a.idx = re.id AND a.assessor = ?
                  AND a.identifier IN (
                    SELECT identifier FROM results r2 WHERE r2.idx = re.id AND (r2.model = ? OR r2.model = 'medmentions') AND r2.identifier IS NOT NULL
                  )
            )
            AND SUM(CASE WHEN r.model = ? AND r.identifier IS NOT NULL THEN 1 ELSE 0 END) > 0
            ORDER BY RANDOM() LIMIT 1
        ''')
        c.execute(sql, (model, assessor, model, model))
        row = c.fetchone()
        random_annotation_index = row[0] if row else None
        # Fast random eligible abstract: pick a random eligible annotation for current model, then use its pmid
        if random_annotation_index is not None:
            sql = q('SELECT pmid FROM recognized_entities WHERE id = ?')
            c.execute(sql, (random_annotation_index,))
            pmid_row = c.fetchone()
            if pmid_row:
                random_pmid = pmid_row[0]
                sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.model = ? AND r.identifier IS NOT NULL ORDER BY RANDOM() LIMIT 1''')
                c.execute(sql, (random_pmid, model))
                row = c.fetchone()
                if row:
                    random_abstract_index = row[0]
    else:
        valid_indices = get_valid_indices(model, conn, paramstyle)
        if index in valid_indices:
            idx_pos = valid_indices.index(index)
            prev_index = valid_indices[idx_pos - 1] if idx_pos > 0 else None
            next_index = valid_indices[idx_pos + 1] if idx_pos < len(valid_indices) - 1 else None
        # Abstract navigation (prev/next) in non-skip mode
        sql = q('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.model = ? ORDER BY re.pmid''')
        c.execute(sql, (model,))
        valid_pmids = [row[0] for row in c.fetchall()]
        pmid_pos = valid_pmids.index(pmid) if pmid and pmid in valid_pmids else None
        prev_abstract_index = next_abstract_index = None
        if pmid_pos is not None:
            if pmid_pos > 0:
                prev_pmid = valid_pmids[pmid_pos - 1]
                sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.model = ? ORDER BY re.id ASC LIMIT 1''')
                c.execute(sql, (prev_pmid, model))
                prev_row = c.fetchone()
                if prev_row:
                    prev_abstract_index = prev_row[0]
            if pmid_pos < len(valid_pmids) - 1:
                next_pmid = valid_pmids[pmid_pos + 1]
                sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.model = ? ORDER BY re.id ASC LIMIT 1''')
                c.execute(sql, (next_pmid, model))
                next_row = c.fetchone()
                if next_row:
                    next_abstract_index = next_row[0]
        # Fast random annotation for current model
        sql = q('''SELECT idx FROM results WHERE model = ? AND identifier IS NOT NULL ORDER BY RANDOM() LIMIT 1''')
        c.execute(sql, (model,))
        row = c.fetchone()
        random_annotation_index = row[0] if row else None
        # Fast random abstract for current model
        sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.model = ? AND r.identifier IS NOT NULL ORDER BY RANDOM() LIMIT 1''')
        c.execute(sql, (model,))
        row = c.fetchone()
        random_abstract_index = row[0] if row else None
    return {
        'prev_index': prev_index,
        'next_index': next_index,
        'prev_abstract_index': prev_abstract_index,
        'next_abstract_index': next_abstract_index,
        'random_annotation_index': random_annotation_index,
        'random_abstract_index': random_abstract_index,
        'prev_abstract_url': None,
        'next_abstract_url': None,
        'random_annotation_url': None,
        'random_abstract_url': None
    }
