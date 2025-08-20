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
    c.execute('''CREATE TABLE assessment (idx INTEGER, identifier TEXT, assessor TEXT, assessment TEXT, UNIQUE(idx, identifier, assessor))''')
    conn.commit()
    return conn

def test_get_next_skip_index_no_eligible():
    conn = setup_in_memory_db()
    # Insert a single recognized entity and result, but all identifiers are assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1', 'user1', 'yes')")
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
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'E3')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1', 'user1', 'yes')")
    conn.commit()
    # Should return 2, since E2 is not assessed for user1
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 2
    conn.close()

def test_get_next_skip_index_partial_assessed():
    conn = setup_in_memory_db()
    # Entity 2 has two identifiers, only one is assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'E2a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2b')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2a', 'user1', 'yes')")
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
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2b', 'user1', 'yes')")
    conn.commit()
    # Should return None, since all identifiers for id=2 are assessed
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_next_skip_index_multiple_users():
    conn = setup_in_memory_db()
    # Entity 2 has one identifier, assessed by user2 but not user1
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E1', 'user2', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2', 'user2', 'yes')")
    conn.commit()
    # Should return 2 for user1, since user1 has not assessed E2
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 2
    conn.close()

def test_get_next_skip_index_multiple_models():
    conn = setup_in_memory_db()
    # Entity 2 has identifiers for two models, only testmodel is relevant
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'E2c')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'othermodel', 'E2b')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2b', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2c', 'user1', 'yes')")
    conn.commit()
    # Should return None, since all identifiers for testmodel are assessed
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) is None
    # Now, if E2a is not assessed, should return 2
    conn.execute("DELETE FROM assessment WHERE idx=2 AND identifier='E2a' AND assessor='user1'")
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
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2b', 'user1', 'yes')")
    conn.commit()
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_prev_skip_index_no_eligible():
    conn = setup_in_memory_db()
    # Only one recognized entity, all identifiers assessed
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1', 'user1', 'yes')")
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
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E0')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E2')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (2, 'E2', 'user1', 'yes')")
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
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E1a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1b')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1a', 'user1', 'yes')")
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
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1b', 'user1', 'yes')")
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
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E0')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1', 'user2', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E0', 'user2', 'yes')")
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
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E0a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1a')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'othermodel', 'E1b')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E0a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1a', 'user1', 'yes')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1b', 'user1', 'yes')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return None, since all identifiers for testmodel are assessed
    assert get_prev_skip_index(2, 'testmodel', 'user1', conn) is None
    # Now, if E1a is not assessed, should return 1
    conn.execute("DELETE FROM assessment WHERE idx=1 AND identifier='E1a' AND assessor='user1'")
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
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1b', 'user1', 'yes')")
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
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (46, 'UMLS:C0085262', 'cb', 'agree')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (47, 'CHEBI:79516', 'cb', 'agree')")
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (49, 'UMLS:C1254354', 'cb', 'disagree')")
    conn.commit()
    # Debug: print identifiers for idx=48
    c = conn.cursor()
    c.execute("SELECT identifier FROM results WHERE idx=48 AND (model='gpt-oss' OR model='medmentions') AND identifier IS NOT NULL")
    print('Identifiers for idx=48:', [row[0] for row in c.fetchall()])
    c.execute("SELECT identifier FROM assessment WHERE idx=48 AND assessor='cb'")
    print('Assessments for idx=48:', [row[0] for row in c.fetchall()])
    from evaluation_helpers import get_prev_skip_index
    # Starting at 50, previous eligible should be 48
    result = get_prev_skip_index(50, 'gpt-oss', 'cb', conn)
    print('get_prev_skip_index(50, gpt-oss, cb) =', result)
    assert result == 48
    conn.close()

def test_get_next_skip_index_skips_missing_model_result():
    conn = setup_in_memory_db()
    # Three recognized entities: 1, 2, 3
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (3, 'PMID3', 'text', 'orig')")
    # Results for model only at 1 and 3, not 2
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'A')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'B')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (3, 'medmentions', 'C')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (3, 'testmodel', 'E3')")
    # Assess 1 so it is not eligible
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (1, 'E1', 'user1', 'yes')")
    conn.commit()
    # Should skip 2 (no result for model) and return 3
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) == 3
    conn.close()

def test_navigation_skips_missing_model_result():
    from evaluation_helpers import get_navigation
    conn = setup_in_memory_db()
    # Three recognized entities: 1, 2, 3
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (3, 'PMID3', 'text', 'orig')")
    # Results for model only at 1 and 3, not 2
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (3, 'testmodel', 'E3')")
    conn.commit()
    # At index 1, next_index should be 3 (skipping 2)
    nav = get_navigation(1, 'testmodel', 'user1', False, conn)
    assert nav['next_index'] == 3
    # At index 3, next_index should be None
    nav = get_navigation(3, 'testmodel', 'user1', False, conn)
    assert nav['next_index'] is None
    conn.close()

def test_get_next_skip_index_last_index_missing_model_result():
    conn = setup_in_memory_db()
    # Only two recognized entities: 1, 2
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    # Result for model only at 1, not 2
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    # Add medmentions results for both indices
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'M1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'M2')")
    conn.commit()
    # At index 1, should return None (since 2 has no result for model)
    assert get_next_skip_index(1, 'testmodel', 'user1', conn) is None
    conn.close()

def test_navigation_last_index_missing_model_result():
    from evaluation_helpers import get_navigation
    conn = setup_in_memory_db()
    # Only two recognized entities: 1, 2
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    # Result for model only at 1, not 2
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    # Add medmentions results for both indices
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'M1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'M2')")
    conn.commit()
    # At index 1, next_index should be None (since 2 has no result for model)
    nav = get_navigation(1, 'testmodel', 'user1', True, conn)
    assert nav['next_index'] is None
    conn.close()

def test_get_next_skip_index_skips_if_same_as_medmentions():
    conn = setup_in_memory_db()
    # Entity 1: testmodel and medmentions have the same identifier
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E1')")
    conn.commit()
    # Should return None, since the only entity should be skipped
    assert get_next_skip_index(0, 'testmodel', 'user1', conn) is None
    conn.close()

def test_get_next_skip_index_does_not_skip_if_different_from_medmentions():
    conn = setup_in_memory_db()
    # Entity 1: testmodel and medmentions have different identifiers
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E2')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E1')")
    conn.commit()
    # Should return 1, since the entity should not be skipped
    assert get_next_skip_index(0, 'testmodel', 'user1', conn) == 1
    conn.close()

def test_get_prev_skip_index_skips_if_same_as_medmentions():
    from evaluation_helpers import get_prev_skip_index
    conn = setup_in_memory_db()
    # Entity 1: testmodel and medmentions have different identifiers
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (1, 'PMID1', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'testmodel', 'E1')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (1, 'medmentions', 'E2')")
    # Entity 2: testmodel and medmentions have the same identifier
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (2, 'PMID2', 'text', 'orig')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'testmodel', 'E3')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (2, 'medmentions', 'E3')")
    conn.commit()
    # Should return 1, skipping 2 (since 2's identifiers match)
    assert get_prev_skip_index(3, 'testmodel', 'user1', conn) == 1
    conn.close()

def test_get_next_skip_index_null_model_result():
    conn = setup_in_memory_db()
    # Insert recognized entities
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (8, 'PMID8', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (9, 'PMID9', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (10, 'PMID10', 'text', 'orig')")
    # Insert results
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (8, 'medmentions', 'UMLS:C0443252')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (9, 'medmentions', 'MONDO:0005275')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (10, 'medmentions', 'UMLS:C0220921')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (10, 'gpt-oss', 'UMLS:C0220922')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (9, 'gpt-oss', NULL)")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (9, 'o3-mini-2025-01-31', 'UMLS:C2359474')")
    # Insert assessment
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (9, 'MONDO:0005275', 'cb', 'agree')")
    conn.commit()
    from evaluation_helpers import get_next_skip_index
    # Should return 9 if NULL is not considered agreement, else None
    result = get_next_skip_index(8, 'gpt-oss', 'cb', conn)
    assert result == 10
    conn.close()

def test_get_prev_skip_index_null_model_result():
    conn = setup_in_memory_db()
    # Insert recognized entities
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (8, 'PMID8', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (9, 'PMID9', 'text', 'orig')")
    conn.execute("INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES (10, 'PMID10', 'text', 'orig')")
    # Insert results
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (8, 'gpt-oss', NULL)")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (8, 'medmentions', 'UMLS:C0443252')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (9, 'medmentions', 'MONDO:0005275')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (10, 'medmentions', 'UMLS:C0220921')")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (9, 'gpt-oss', NULL)")
    conn.execute("INSERT INTO results (idx, model, identifier) VALUES (9, 'o3-mini-2025-01-31', 'UMLS:C2359474')")
    # Insert assessment
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (9, 'MONDO:0005275', 'cb', 'agree')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    # Should return 9 if NULL is not considered agreement, else None
    result = get_prev_skip_index(10, 'gpt-oss', 'cb', conn)
    assert result == 8
    conn.close()

def test_get_prev_skip_index_complex_realistic():
    conn = setup_in_memory_db()
    # Insert recognized entities
    for i in range(11):
        conn.execute(f"INSERT INTO recognized_entities (id, pmid, expanded_text, original_text) VALUES ({i}, 'PMID{i}', 'text', 'orig')")
    # Insert results
    results = [
        (0, 'gpt-oss', 'NCBIGene:51164'), (0, 'medmentions', 'NCBIGene:51164'), (0, 'o3-mini-2025-01-31', 'NCBIGene:51164'),
        (1, 'gpt-oss', 'NCBIGene:51164'), (1, 'medmentions', 'NCBIGene:51164'), (1, 'o3-mini-2025-01-31', 'NCBIGene:51164'),
        (2, 'gpt-oss', 'UMLS:C5208136'), (2, 'medmentions', 'UMLS:C0854135'), (2, 'o3-mini-2025-01-31', 'UMLS:C5208136'),
        (3, 'gpt-oss', 'UMLS:C5208136'), (3, 'medmentions', 'UMLS:C0854135'), (3, 'o3-mini-2025-01-31', 'UMLS:C5208136'),
        (4, 'gpt-oss', 'MONDO:0009061'), (4, 'medmentions', 'MONDO:0009061'), (4, 'o3-mini-2025-01-31', 'MONDO:0009061'),
        (5, 'gpt-oss', 'MONDO:0009061'), (5, 'medmentions', 'MONDO:0009061'), (5, 'o3-mini-2025-01-31', 'MONDO:0009061'),
        (6, 'gpt-oss', 'UMLS:C0854135'), (6, 'medmentions', 'UMLS:C0854135'), (6, 'o3-mini-2025-01-31', 'UMLS:C0854135'),
        (7, 'gpt-oss', 'UMLS:C0030705'), (7, 'medmentions', 'UMLS:C0030705'), (7, 'o3-mini-2025-01-31', 'UMLS:C0030705'),
        (8, 'medmentions', 'UMLS:C0443252'),
        (9, 'gpt-oss', None), (9, 'medmentions', 'MONDO:0005275'), (9, 'o3-mini-2025-01-31', 'UMLS:C2359474'),
        (10, 'medmentions', 'UMLS:C0220921'),
    ]
    for idx, model, identifier in results:
        conn.execute("INSERT INTO results (idx, model, identifier) VALUES (?, ?, ?)", (idx, model, identifier))
    # Insert assessment
    conn.execute("INSERT INTO assessment (idx, identifier, assessor, assessment) VALUES (9, 'MONDO:0005275', 'cb', 'agree')")
    conn.commit()
    from evaluation_helpers import get_prev_skip_index
    result = get_prev_skip_index(10, 'gpt-oss', 'cb', conn)
    assert result == 3
    conn.close()
