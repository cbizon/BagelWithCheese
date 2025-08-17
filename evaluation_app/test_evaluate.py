import sqlite3
import pytest
from evaluation_helpers import get_next_skip_index

def setup_in_memory_db():
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    # Create tables
    c.execute('''CREATE TABLE abstracts (pmid TEXT PRIMARY KEY, abstract TEXT)''')
    c.execute('''CREATE TABLE entities (identifier TEXT PRIMARY KEY, label TEXT, description TEXT, type TEXT, taxon TEXT)''')
    c.execute('''CREATE TABLE recognized_entities (id INTEGER PRIMARY KEY, pmid TEXT, expanded_text TEXT, original_text TEXT)''')
    c.execute('''CREATE TABLE results (idx INTEGER, model TEXT, identifier TEXT, PRIMARY KEY (idx, model, identifier))''')
    c.execute('''CREATE TABLE assessment (idx INTEGER, identifier TEXT, user TEXT, assessment TEXT, UNIQUE(idx, identifier, user))''')
    conn.commit()
    return conn

def test_get_next_skip_index_no_eligible():
    conn = setup_in_memory_db()
    # Insert a single recognized entity and result, but all identifiers are assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1', 'user1', 'yes')")
    conn.commit()
    # Should return None since all identifiers for id=1 are assessed
    assert get_next_skip_index(0, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_next_skip_index_eligible_exists():
    conn = setup_in_memory_db()
    # Two recognized entities, only first is assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1', 'user1', 'yes')")
    conn.commit()
    # Should return 2, since E2 is not assessed for user1
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 2
    conn.close()

def test_get_next_skip_index_partial_assessed():
    conn = setup_in_memory_db()
    # Entity 2 has two identifiers, only one is assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2b')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2a', 'user1', 'yes')")
    conn.commit()
    # Should return 2, since E2b is not assessed for user1
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 2
    conn.close()

def test_get_next_skip_index_all_assessed_multiple_identifiers():
    conn = setup_in_memory_db()
    # Entity 2 has two identifiers, both are assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2b')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2b', 'user1', 'yes')")
    conn.commit()
    # Should return None, since all identifiers for id=2 are assessed
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_next_skip_index_multiple_users():
    conn = setup_in_memory_db()
    # Entity 2 has one identifier, assessed by user2 but not user1
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2', 'user2', 'yes')")
    conn.commit()
    # Should return 2 for user1, since user1 has not assessed E2
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 2
    conn.close()

def test_get_next_skip_index_multiple_models():
    conn = setup_in_memory_db()
    # Entity 2 has identifiers for two models, only testmodel is relevant
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'othermodel', 'E2b')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2b', 'user1', 'yes')")
    conn.commit()
    # Should return None, since all identifiers for testmodel are assessed
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) is None
    # Now, if E2a is not assessed, should return 2
    conn.execute("DELETE FROM assessment WHERE idx=2 AND identifier='E2a' AND user='user1'")
    conn.commit()
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 2
    conn.close()

def test_get_next_skip_index_null_identifier():
    conn = setup_in_memory_db()
    # Entity 2: testmodel result is NULL, medmentions has a real identifier
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', NULL)")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'E2b')")
    conn.commit()
    # Should return 2, since E2b is not assessed for user1 and NULL identifier should be ignored
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 2
    # Now, if E2b is assessed, should return None
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2b', 'user1', 'yes')")
    conn.commit()
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_prev_skip_index_no_eligible():
    conn = setup_in_memory_db()
    # Only one recognized entity, all identifiers assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1', 'user1', 'yes')")
    conn.commit()
    # Should return None since there is no previous eligible index
    from evaluation_helpers import get_prev_skip_index
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_prev_skip_index_eligible_exists():
    conn = setup_in_memory_db()
    # Two recognized entities, only second is assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (2, 'E2', 'user1', 'yes')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return 1, since E1 is not assessed for user1
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) == 1
    conn.close()

def test_get_prev_skip_index_partial_assessed():
    conn = setup_in_memory_db()
    # Entity 1 has two identifiers, only one is assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1b')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1a', 'user1', 'yes')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return 1, since E1b is not assessed for user1
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) == 1
    conn.close()

def test_get_prev_skip_index_all_assessed_multiple_identifiers():
    conn = setup_in_memory_db()
    # Entity 1 has two identifiers, both are assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1b')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1b', 'user1', 'yes')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return None, since all identifiers for id=1 are assessed
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_prev_skip_index_multiple_users():
    conn = setup_in_memory_db()
    # Entity 1 has one identifier, assessed by user2 but not user1
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1', 'user2', 'yes')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return 1 for user1, since user1 has not assessed E1
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) == 1
    conn.close()

def test_get_prev_skip_index_multiple_models():
    conn = setup_in_memory_db()
    # Entity 1 has identifiers for two models, only testmodel is relevant
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'othermodel', 'E1b')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1b', 'user1', 'yes')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return None, since all identifiers for testmodel are assessed
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) is None
    # Now, if E1a is not assessed, should return 1
    conn.execute("DELETE FROM assessment WHERE idx=1 AND identifier='E1a' AND user='user1'")
    conn.commit()
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) == 1
    conn.close()

def test_get_prev_skip_index_null_identifier():
    conn = setup_in_memory_db()
    # Entity 1: testmodel result is NULL, medmentions has a real identifier
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', NULL)")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E1b')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return 1, since E1b is not assessed for user1 and NULL identifier should be ignored
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) == 1
    # Now, if E1b is assessed, should return None
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (1, 'E1b', 'user1', 'yes')")
    conn.commit()
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_prev_skip_index_complex_skip():
    conn = setup_in_memory_db()
    # Insert recognized entities for idx 46-49
    for idx in range(46, 50):
        conn.execute(f"INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES ({idx}, 'PMID{idx}', 'text', 'orig')")
    # Insert results as described
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (46, 'gpt-oss', 'UMLS:C0085262')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (46, 'medmentions', 'UMLS:C0085262')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (47, 'gpt-oss', 'CHEBI:79516')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (47, 'medmentions', 'UMLS:C1254354')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (48, 'gpt-oss', NULL)")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (48, 'medmentions', 'UMLS:C1254354')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (49, 'gpt-oss', NULL)")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (49, 'medmentions', 'UMLS:C1254354')")
    # Insert assessments as described
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (46, 'UMLS:C0085262', 'cb', 'agree')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (47, 'CHEBI:79516', 'cb', 'agree')")
    conn.execute("INSERT INTO assessment (idx, identifier, user, assessment) VALUES (49, 'UMLS:C1254354', 'cb', 'disagree')")
    conn.commit()
    # Debug: print identifiers for idx=48
    c = conn.cursor()
    c.execute("SELECT identifier FROM results WHERE idx=48 AND (model='gpt-oss' OR model='medmentions') AND identifier IS NOT NULL")
    print('Identifiers for idx=48:', [row[0] for row in c.fetchall()])
    c.execute("SELECT identifier FROM assessment WHERE idx=48 AND user='cb'")
    print('Assessments for idx=48:', [row[0] for row in c.fetchall()])
    from evaluation_helpers import get_prev_skip_index
    # Starting at 50, previous eligible should be 48
    result = get_prev_skip_index(50, 'gpt-oss', 'cb', conn)
    print('get_prev_skip_index(50, gpt-oss, cb) =', result)
    assert result == 48
    conn.close()
