# BAGEL City

This project provides a workflow for generating prompts, running them through various AI models (local and OpenAI), evaluating the results, and interactively browsing the results via a web app. The workflow is organized into several scripts and directories for input data, output data, batch files, and results.

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

Other files and folders may exist for logs, temporary files, or legacy purposes. See each script's documentation for details on input/output locations.

## Required Input Files

The `input_data/` directory must contain the following files:

- `corpus_pubtator_normalized_*.jsonl` — The main corpus file in JSONL format. The filename may include a date or version suffix.
- `annotations-*.jsonl` — The annotations file in JSONL format. The filename may include a date or version suffix.

These files are required for prompt generation and downstream processing. Ensure they are present and up to date before running the workflow.

## Workflow Overview

### 1. Extract Abbreviations

Before generating prompts, run `get_abbreviations.py` to extract abbreviations from the corpus. This script processes the corpus and outputs abbreviation results to `input_data/abbreviation_llm_results.jsonl`.

To run:

```
python scripts/get_abbreviations.py
```

This will create or update the abbreviation results file in `input_data/`. This file is required for prompt generation and downstream scripts that depend on abbreviation data.

### 2. Generate Prompts

Run `make_prompts.py` to create prompt files in the `data/` directory. This script expects the required files to be present in `input_data/`.

To generate prompts, run:

```
python scripts/make_prompts.py --run RUN_NAME --threshold THRESHOLD
```

- `--run` specifies the run directory name (e.g., `run_1`).
- `--threshold` specifies the prompt threshold (e.g., `10`, `20`, etc.).

This will generate files like `data/RUN_NAME/bodies_THRESHOLD.jsonl` in the appropriate run directory.

### 3. Run Local Model (Ollama)

Use `run_ollama.py` to process prompts with a local model (e.g., via Ollama). You can specify which models and thresholds to use with command-line arguments.

Example usage:

```
python scripts/run_ollama.py --run run_1 --models "alibayram/medgemma:27B" "gemma3:12B" --thresholds 10 20
```

- `--run` specifies the run directory name (default: `run_1`).
- `--models` specifies one or more model names to run (default: all models).
- `--thresholds` specifies one or more thresholds to use (default: all thresholds).

If you omit `--models` or `--thresholds`, the script will use all available models and thresholds by default.

**Input prompt files should be in the `data/RUN_NAME/parsed_inputs/` directory, and output files will be written to `data/RUN_NAME/ollama_results/`.**

Results are saved as files named like `MODELNAME__bodies_THRESHOLD_message_output.jsonl` and `MODELNAME__bodies_THRESHOLD_response_output.jsonl`.

To run the script, simply execute:

```
python scripts/run_ollama.py
```

This will process all configured models and prompt files as specified in the script, reading from and writing to the `data/` directory.

### 4. Prepare OpenAI Batch Files

Use `convert_to_openai_batch.py` to convert prompts into OpenAI batch format. This script takes a threshold (e.g., 10 or 20), infers the bodies and color file locations, and writes batch files to `data/run_*/open_ai_batches_{threshold}/`. You can also use the `--limit` option to control how many prompts are included in each batch file.

```
python scripts/convert_to_openai_batch.py 10 --limit 50
```

This will create files like `data/run_*/open_ai_batches_10/openai_batch_gpt-4o_bodies_10.jsonl` for each model, each containing up to 50 prompts.

### 5. Run OpenAI Batch

Use `run_openai.py` to submit and monitor all batch files in a directory (e.g., `data/run_*/open_ai_batches_10`). All batches will be submitted and monitored concurrently (one thread per batch file). Results for each batch will be downloaded into a new directory (e.g., `data/run_*/open_ai_results_10`).

```
python scripts/run_openai.py data/run_*/open_ai_batches_10
```

Each result will be saved as `data/run_*/open_ai_results_10/openai_results_MODELNAME_bodies_10.jsonl`.

You can also specify a custom output directory with `--output_dir`.

### 6. Evaluate Outputs

Use `evaluate_outputs.py` to aggregate and evaluate all results from Ollama and OpenAI. The script will automatically find all relevant result files in the `data/` directory and its subdirectories, and produce a combined summary.

```
python scripts/evaluate_outputs.py
```

The combined evaluation summary will be written to `data/run_*/evaluation_summary_all.jsonl`.

### 7. Build Database for Browser App

Use `build_db.py` to create the SQLite database (`results.db`) for a run. This is required for the browser app to function.

```
python scripts/build_db.py --run run_1
```

This will create `data/run_1/results.db`.

### 8. Analyze and Visualize Evaluation Results

After running evaluations, use `analyze.py` to aggregate and summarize the results by model and threshold. This script reads the evaluation summary JSONL file and outputs a TSV file with aggregated statistics.

```
python scripts/analyze.py --input data/run_1/evaluation_summary_all.jsonl
```

This will create a file like `data/run_1/evaluation_summary_all_aggregated.tsv` containing the summary statistics.

You can also use `visualize_analysis.py` to generate plots and visualizations from the aggregated TSV file:

```
python scripts/visualize_analysis.py --input data/run_1/evaluation_summary_all_aggregated.tsv
```

## Browse Results with the Web App

The `results_browser_app` directory contains a Flask app for interactively browsing results. It displays abstracts, candidate entities, and model agreement for each threshold present in your data.

To run the browser app:

```
python results_browser_app/browse_results.py --run run_1
```

- The app will be available at `http://localhost:5000/`.
- Use the navigation links to browse through examples.
- The columns shown will automatically match the available thresholds in your database.

## Interactive Data Exploration

- `scripts/examine.ipynb` — Jupyter notebook for ad hoc exploration of annotation and entity data. Open in JupyterLab or VSCode for interactive use.

## Notes

- All scripts should be run from the top-level directory unless otherwise noted.
- Input files are in `input_data/`, outputs in `data/`, batch files in `data/run_*/open_ai_batches_{threshold}/`, and results in `data/run_*/open_ai_results_{threshold}/`.
- Adjust script arguments as needed for your specific use case.

## Example Full Workflow

```
python scripts/get_abbreviations.py
python scripts/make_prompts.py --run run_1 --threshold 10
python scripts/run_ollama.py --run run_1 --thresholds 10
python scripts/convert_to_openai_batch.py 10 --limit 50
python scripts/run_openai.py data/run_1/open_ai_batches_10
python scripts/evaluate_outputs.py
python scripts/build_db.py --run run_1
python scripts/analyze.py --input data/run_1/evaluation_summary_all.jsonl
python scripts/visualize_analysis.py --input data/run_1/evaluation_summary_all_aggregated.tsv
python results_browser_app/browse_results.py --run run_1
```

---

For more details on each script's options, use the `--help` flag, e.g.:

```
python scripts/run_ollama.py --help
```
