import re
import random

def get_abstract_metadata(index, conn, paramstyle='?'):
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
    c.execute(q('SELECT original_text FROM recognized_entities WHERE id = ?'), (index,))
    orig_row = c.fetchone()
    original_text = orig_row[0] if orig_row else ''
    
    # Get all model results for this index
    c.execute(q('SELECT model, identifier FROM results WHERE idx = ? AND identifier IS NOT NULL'), (index,))
    model_results = {}
    for model, identifier in c.fetchall():
        if model not in model_results:
            model_results[model] = []
        model_results[model].append(identifier)
    
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
        'model_results': model_results,
        'highlighted_abstract': highlighted_abstract
    }

def get_valid_indices(conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    c.execute(q('SELECT DISTINCT idx FROM results ORDER BY idx'))
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

def get_next_skip_index(index, assessor, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    sql = q('''
        SELECT re.id
        FROM recognized_entities re
        WHERE re.id > ?
        AND EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id)
        AND EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id AND r.model != 'medmentions')
        AND NOT (
            -- Skip if all models agree (same non-NULL identifier and no NULLs)
            (SELECT COUNT(DISTINCT r.identifier) FROM results r WHERE r.idx = re.id AND r.identifier IS NOT NULL) = 1
            AND NOT EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id AND r.identifier IS NULL)
            AND (SELECT COUNT(*) FROM results r WHERE r.idx = re.id) > 1
        )
        AND (
            SELECT COUNT(DISTINCT res.identifier)
            FROM results res
            WHERE res.idx = re.id AND res.identifier IS NOT NULL
        ) > (
            SELECT COUNT(DISTINCT a.identifier)
            FROM assessment a
            WHERE a.idx = re.id AND a.assessor = ?
              AND a.identifier IN (
                SELECT identifier FROM results res2 
                WHERE res2.idx = re.id AND res2.identifier IS NOT NULL
              )
        )
        ORDER BY re.id ASC
        LIMIT 1
    ''')
    c.execute(sql, (index, assessor))
    row = c.fetchone()
    result = row[0] if row else None
    return result

def get_prev_skip_index(index, assessor, conn, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    sql = q('''
        SELECT re.id
        FROM recognized_entities re
        WHERE re.id < ?
        AND EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id)
        AND EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id AND r.model != 'medmentions')
        AND NOT (
            -- Skip if all models agree (same non-NULL identifier and no NULLs)
            (SELECT COUNT(DISTINCT r.identifier) FROM results r WHERE r.idx = re.id AND r.identifier IS NOT NULL) = 1
            AND NOT EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id AND r.identifier IS NULL)
            AND (SELECT COUNT(*) FROM results r WHERE r.idx = re.id) > 1
        )
        AND (
            SELECT COUNT(DISTINCT res.identifier)
            FROM results res
            WHERE res.idx = re.id AND res.identifier IS NOT NULL
        ) > (
            SELECT COUNT(DISTINCT a.identifier)
            FROM assessment a
            WHERE a.idx = re.id AND a.assessor = ?
              AND a.identifier IN (
                SELECT identifier FROM results res2 
                WHERE res2.idx = re.id AND res2.identifier IS NOT NULL
              )
        )
        ORDER BY re.id DESC
        LIMIT 1
    ''')
    c.execute(sql, (index, assessor))
    row = c.fetchone()
    result = row[0] if row else None
    return result

def get_navigation(index, assessor, skip_mode, conn, pmid=None, paramstyle='?'):
    c = conn.cursor()
    q = lambda sql: sql.replace('?', '%s') if paramstyle == '%s' else sql
    prev_index = next_index = None
    prev_abstract_index = next_abstract_index = None
    prev_abstract_url = next_abstract_url = None
    random_annotation_index = random_abstract_index = None
    if skip_mode and assessor:
        next_index = get_next_skip_index(index, assessor, conn, paramstyle)
        prev_index = get_prev_skip_index(index, assessor, conn, paramstyle)
        # Abstract navigation (prev/next) in skip mode
        # Get all pmids that have any model results
        sql = q('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx ORDER BY re.pmid''')
        c.execute(sql)
        pmid_rows = c.fetchall()
        pmid_list = [row[0] for row in pmid_rows]
        pmid_pos = pmid_list.index(pmid) if pmid and pmid in pmid_list else None
        # Previous abstract
        prev_abstract_index = None
        if pmid_pos is not None and pmid_pos > 0:
            for p in range(pmid_pos - 1, -1, -1):
                prev_pmid = pmid_list[p]
                # Find first eligible annotation in this abstract
                prev_idx = get_prev_skip_index(999999, assessor, conn, paramstyle)  # Get any eligible before a high number
                if prev_idx is not None:
                    sql = q('SELECT pmid FROM recognized_entities WHERE id = ?')
                    c.execute(sql, (prev_idx,))
                    pmid_row = c.fetchone()
                    if pmid_row and pmid_row[0] == prev_pmid:
                        prev_abstract_index = prev_idx
                        break
        # Next abstract  
        next_abstract_index = None
        if pmid_pos is not None and pmid_pos < len(pmid_list) - 1:
            for p in range(pmid_pos + 1, len(pmid_list)):
                next_pmid = pmid_list[p]
                # Find first eligible annotation in this abstract
                next_idx = get_next_skip_index(0, assessor, conn, paramstyle)  # Get any eligible after 0
                if next_idx is not None:
                    sql = q('SELECT pmid FROM recognized_entities WHERE id = ?')
                    c.execute(sql, (next_idx,))
                    pmid_row = c.fetchone()
                    if pmid_row and pmid_row[0] == next_pmid:
                        next_abstract_index = next_idx
                        break
        # Fast random eligible annotation
        random_annotation_index = get_next_skip_index(0, assessor, conn, paramstyle)
        # Fast random eligible abstract: pick a random eligible annotation, then use its pmid
        if random_annotation_index is not None:
            sql = q('SELECT pmid FROM recognized_entities WHERE id = ?')
            c.execute(sql, (random_annotation_index,))
            pmid_row = c.fetchone()
            if pmid_row:
                random_pmid = pmid_row[0]
                sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? AND r.identifier IS NOT NULL ORDER BY RANDOM() LIMIT 1''')
                c.execute(sql, (random_pmid,))
                row = c.fetchone()
                if row:
                    random_abstract_index = row[0]
    else:
        valid_indices = get_valid_indices(conn, paramstyle)
        if index in valid_indices:
            idx_pos = valid_indices.index(index)
            prev_index = valid_indices[idx_pos - 1] if idx_pos > 0 else None
            next_index = valid_indices[idx_pos + 1] if idx_pos < len(valid_indices) - 1 else None
        # Abstract navigation (prev/next) in non-skip mode
        sql = q('''SELECT DISTINCT re.pmid FROM recognized_entities re JOIN results r ON re.id = r.idx ORDER BY re.pmid''')
        c.execute(sql)
        valid_pmids = [row[0] for row in c.fetchall()]
        pmid_pos = valid_pmids.index(pmid) if pmid and pmid in valid_pmids else None
        prev_abstract_index = next_abstract_index = None
        if pmid_pos is not None:
            if pmid_pos > 0:
                prev_pmid = valid_pmids[pmid_pos - 1]
                sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? ORDER BY re.id ASC LIMIT 1''')
                c.execute(sql, (prev_pmid,))
                prev_row = c.fetchone()
                if prev_row:
                    prev_abstract_index = prev_row[0]
            if pmid_pos < len(valid_pmids) - 1:
                next_pmid = valid_pmids[pmid_pos + 1]
                sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE re.pmid = ? ORDER BY re.id ASC LIMIT 1''')
                c.execute(sql, (next_pmid,))
                next_row = c.fetchone()
                if next_row:
                    next_abstract_index = next_row[0]
        # Fast random annotation
        sql = q('''SELECT idx FROM results WHERE identifier IS NOT NULL ORDER BY RANDOM() LIMIT 1''')
        c.execute(sql)
        row = c.fetchone()
        random_annotation_index = row[0] if row else None
        # Fast random abstract
        sql = q('''SELECT re.id FROM recognized_entities re JOIN results r ON re.id = r.idx WHERE r.identifier IS NOT NULL ORDER BY RANDOM() LIMIT 1''')
        c.execute(sql)
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
