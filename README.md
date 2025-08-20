# BAGEL City

This repository provides two main capabilities:

1. **Generate BAGEL Results with LLMs:**
   - Use a set of scripts to generate prompts, run them through local or OpenAI LLMs, and collect the results. For full details and step-by-step instructions, see [README_run_bagel.md](README_run_bagel.md).
2. **Evaluate and Explore Results:**
   - Build a database from the results and use a browser-based app to assess and explore the outputs. See [README_evaluate_bagel.md](README_evaluate_bagel.md) for full instructions on evaluation, database creation, and loading results.

---

## Directory Structure

- `scripts/` — All Python scripts for prompt generation, batch creation, model execution, evaluation, database building, and analysis:
  - `make_prompts.py` — Generate prompt files for each run/threshold.
  - `run_ollama.py` — Run local models (Ollama) on prompts.
  - `convert_to_openai_batch.py` — Convert prompts to OpenAI batch format.
  - `run_openai.py` — Submit and monitor OpenAI batch jobs.
  - `evaluate_outputs.py` — Aggregate and evaluate results from all models.
  - `analyze.py` — Summarize evaluation results by model/threshold.
  - `build_db.py` — Build the SQLite database for the browser app.
  - `visualize_analysis.py` — Create visualizations from evaluation results.
  - `get_abbreviations.py` — Extract abbreviations from the corpus.
  - `examine.ipynb` — Jupyter notebook for interactive data exploration.
- `input_data/` — Input data files (annotations, corpora, prompt templates, etc.).
- `data/` — All output data, including prompts, results, evaluations, and visualizations. Contains subdirectories for different experiment runs:
  - `run_*/` — Each run directory contains outputs and subdirectories for that experiment:
    - `evaluation_summary_all.jsonl`, `evaluation_summary_all_aggregated.tsv`, `results_all.tsv`, `results.db` — Summary and aggregated results for the run.
    - `ollama_results/` — Results from local (Ollama) model runs for this run.
    - `open_ai_batches_{threshold}/` — OpenAI batch files for each threshold for this run.
    - `open_ai_results_{threshold}/` — OpenAI batch results for each threshold for this run.
    - `parsed_inputs/` — Intermediate parsed input files for this run.
    - `visualizations/` — Visualization outputs for this run.
- `results_browser_app/` — Flask app for browsing results:
  - `browse_results.py` — Main Flask app code.
  - `templates/` — HTML templates for result browsing (e.g., `browse.html`).
- `batches/` — (Legacy) Old OpenAI batch files (not used in current workflow).
- `README.md` — Project documentation.
