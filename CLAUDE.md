BAGEL: Babel Assissted Generative Entity Linker

Given an abstract and a set of text spans, we send the text to our initial entity linkers, name resolver and sapbert.  This generates a list of candidates, and those go to an LLM reranker that considers the abstract text as well as the possiblities. We can run this against several different models, including OpenAI batch mode queries and local ollama models.

We also have an evaluation webapp that shows a user the results from bagel as well as the results from the medmentions benchmark.  The user is able to mark whether they think that each is good or not.

We are using conda for dependencies, the environment is called Babel

## Skip Mode Logic

The evaluation webapp has a "skip mode" for efficient assessment. The skip logic is designed around the fact that **medmentions is a benchmark** we're comparing our new models against.

### Key Skip Principles:
1. **Skip if only medmentions has results** - These aren't worth assessing since we only care about medmentions in comparison to other models
2. **Skip if all models agree** - When medmentions and other models produce the same identifier, there's no disagreement to assess
3. **Show for assessment if models disagree** - The interesting cases where our new models differ from the medmentions benchmark
4. **Show if assessments incomplete** - Any case where there are unassessed identifiers from models that disagree

### Multi-Model Skip Behavior:
- **Medmentions-only results**: Skip (not interesting)  
- **Single model + medmentions with same result**: Skip (models agree)
- **Multiple models with different results**: Show for assessment
- **Partial assessments**: Show until all identifiers are assessed

The goal is to efficiently focus assessment effort on cases where new models disagree with the medmentions benchmark, allowing unbiased evaluation of when we prefer the new models over medmentions.

### NULL Identifier Handling:
- **NULLs indicate disagreement**: If one model returns NULL and another returns a non-NULL identifier, this is considered disagreement requiring assessment
- **NULLs are not assessed**: Only non-NULL identifiers get assessment buttons and require evaluation
- **Assessment completion**: An index is only "complete" when all non-NULL identifiers have been assessed

### Skip Mode Technical Details:
The skip logic is implemented in `get_next_skip_index()` and `get_prev_skip_index()` functions with these conditions:
1. Has any results: `EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id)`
2. Not medmentions-only: `EXISTS (SELECT 1 FROM results r WHERE r.idx = re.id AND r.model != 'medmentions')`  
3. Models disagree: Check for multiple distinct identifiers OR presence of NULLs
4. Assessment incomplete: Count distinct non-NULL identifiers vs assessed identifiers

## Multi-Model Display Architecture

**IMPORTANT**: The evaluation webapp was converted from single-model display (dropdown selection) to multi-model display (show all models simultaneously).

### Key Implementation Details:
- **Blind Evaluation**: Model names are NOT shown to evaluators to maintain unbiased assessment
- **Unique Identifiers**: Each identifier appears only once, regardless of how many models produced it
- **Function Signatures**: Helper functions no longer take model parameters:
  - `get_abstract_metadata(index, conn, paramstyle)` - returns `model_results` dict
  - `get_valid_indices(conn, paramstyle)` - works with any model results
  - `get_navigation(index, assessor, skip_mode, conn, pmid, paramstyle)` - model-agnostic
- **Assessment Flow**: Users assess unique identifiers without knowing which models produced them

### Frontend Changes:
- **Removed**: Model selection dropdown
- **Kept**: Login/logout, skip mode toggle, all assessment functionality  
- **Template**: Shows `identifier_infos` list (unique identifiers from all models)

### Skip Mode Usage:
- Enable via "Enter skip mode" link in top-right (appears after login)
- Skip mode focuses on disagreement cases, regular mode shows all results
- Navigation automatically updates based on mode
