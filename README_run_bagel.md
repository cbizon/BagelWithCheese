# BAGEL City: Generating LLM Results

This document describes how to use the provided scripts to generate BAGEL results using LLMs. It covers the workflow for preparing input data, generating prompts, running LLMs (local and OpenAI), and collecting results for downstream evaluation and exploration.

If you are looking to evaluate or browse the results, see the main [README.md](README.md) for instructions on database creation and running the results browser app.

# BAGEL City

This project provides a workflow for generating prompts, running them through various AI models (local and OpenAI), evaluating the results, and interactively browsing the results via a web app. The workflow is organized into several scripts and directories for input data, output data, batch files, and results.


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

### 3. Run Local Models with Ollama

The `run_ollama.py` script runs prompts through local (Ollama) models and saves the results. You must specify which run directory to use (created by `make_prompts.py`).

**Arguments:**

- `--run RUN_NAME` (required): Name of the run directory under `data/` (e.g., `run_1`).
- `--models MODEL [MODEL ...]` (optional): List of model names to run (default: all models in the script). Example: `--models "alibayram/medgemma:27B" "gemma3:12B"`
- `--thresholds N [N ...]` (optional): List of thresholds to use (default: all thresholds in the script). Example: `--thresholds 5 10`
- `--walltime SECONDS` (optional): Walltime in seconds per model (default: run to completion).
- `--test-llm` (optional): Test LLM connection for selected models and exit (does not run prompts).

**Example usage:**

```bash
python scripts/run_ollama.py --run run_1 --models "alibayram/medgemma:27B" "gemma3:12B" --thresholds 5 10
```

This will run the specified models on the prompts for thresholds 5 and 10 in the `data/run_1/` directory. Results will be saved in `data/run_1/ollama_results/`.

**Outputs:**
- Model responses are saved as JSONL files in the corresponding `ollama_results/` directory for the run.
- Filenames encode the model and threshold used.

### 4. Convert Prompts to OpenAI Batch Format

The `convert_to_openai_batch.py` script converts generated prompts into OpenAI batch format for one or more models. It reads prompt files from a run directory and writes batch files for each model to a dedicated output directory.

**Arguments:**

- `--threshold N` (required): The threshold for the prompt files (e.g., 10, 20, etc.).
- `--run RUN_NAME` (optional): Name of the run directory under `data/` (default: `run_1`).
- `--limit N` (optional): Maximum number of prompts to include in each batch file (default: all prompts).
- `--models MODEL1,MODEL2,...` (optional): Comma-separated list of model names to use (default: all supported models).

**Example usage:**

```bash
python scripts/convert_to_openai_batch.py --threshold 10 --run run_1 --models "gpt-4o,gpt-4.1" --limit 50
```

This will convert up to 50 prompts from `data/run_1/parsed_inputs/bodies_10.jsonl` into OpenAI batch format for the `gpt-4o` and `gpt-4.1` models, writing output files to `data/run_1/open_ai_batches_10/`.

**Outputs:**
- Batch files are saved as `openai_batch_MODELNAME_bodies_THRESHOLD.jsonl` in the appropriate `open_ai_batches_{threshold}` directory for the run.
- Each file contains prompts formatted for OpenAI batch processing.

### 5. Run OpenAI Batch

The `run_openai.py` script submits and monitors all OpenAI batch files for a given run. It automatically finds all `open_ai_batches_*` directories in the specified run directory, submits each batch file, monitors job status, and downloads results when complete.

**Arguments:**

- `--run RUN_NAME` (optional): Name of the run directory under `data/` (default: `run_1`).

**Example usage:**

```bash
python scripts/run_openai.py --run run_1
```

This will process all batch files in all `open_ai_batches_*` directories under `data/run_1/`, submitting them to OpenAI and saving results in the corresponding `open_ai_results_*` directories.

**Outputs:**
- Results are saved as `openai_results_MODELNAME_bodies_THRESHOLD.jsonl` in the appropriate `open_ai_results_{threshold}` directory for the run.
- Each file contains the OpenAI model responses for the submitted batch.

### 6. Evaluate Outputs

The `evaluate_outputs.py` script aggregates and evaluates all results from Ollama and OpenAI for a given run. It automatically finds all thresholds and processes both Ollama and OpenAI outputs, producing combined summary files for downstream analysis and database building.

**Arguments:**

- `--run RUN_NAME` (required): Name of the run directory under `data/` (e.g., `run_1`).

**Example usage:**

```bash
python scripts/evaluate_outputs.py --run run_1
```

This will process all results for all thresholds in `data/run_1/`, aggregating and evaluating both Ollama and OpenAI outputs.

**Outputs:**
- Combined evaluation summary as `evaluation_summary_all.jsonl` in the run directory (e.g., `data/run_1/evaluation_summary_all.jsonl`).
- TSV file for database building as `results_all.tsv` in the run directory (e.g., `data/run_1/results_all.tsv`).

### 7. Build Database for Browser App

Use `build_db.py` to create the SQLite database (`results.db`) for a run. This is required for the browser app to function.

```
python scripts/build_db.py --run run_1
```

This will create `data/run_1/results.db`.

### 8. Analyze and Visualize Evaluation Results

The `analyze.py` script aggregates and summarizes the evaluation results by model and threshold. It reads the evaluation summary JSONL file and outputs a TSV file with aggregated statistics for further analysis and visualization.

**Arguments:**

- `--run RUN_NAME` (required): Name of the run directory under `data/`.

**Example usage:**

```bash
python scripts/analyze.py --run run_1
```

This will read `data/run_1/evaluation_summary_all.jsonl` and write the aggregated results to `data/run_1/evaluation_summary_all_aggregated.tsv`.

**Outputs:**
- Aggregated statistics as `evaluation_summary_all_aggregated.tsv` in the run directory (e.g., `data/run_1/evaluation_summary_all_aggregated.tsv`).

---

The `visualize_analysis.py` script generates plots and visualizations from the aggregated TSV file. It produces a series of plots (e.g., accuracy, cost, duration) for each model and threshold, saving them in the run's `visualizations/` directory.

**Arguments:**

- `--run RUN_NAME` (optional): Name of the run directory under `data/` (default: `run_1`).
- `--input FILE` (optional): Path to the aggregated TSV file (default: `data/RUN_NAME/evaluation_summary_all_aggregated.tsv`).
- `--out FILE` (optional): Output plot file for duration plot (default: `data/RUN_NAME/visualizations/avg_duration_vs_threshold.png`).

**Example usage:**

```bash
python scripts/visualize_analysis.py --run run_1
```

This will generate plots for all relevant metrics and save them in `data/run_1/visualizations/`.

**Outputs:**
- Plots for each metric (e.g., `avg_duration_vs_threshold.png`, `avgcost_vs_threshold.png`, etc.) saved in the `visualizations/` directory for the run.

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
python scripts/convert_to_openai_batch.py --threshold 10 --run run_1 --limit 50
python scripts/run_openai.py --run run_1
python scripts/evaluate_outputs.py --run run_1
python scripts/build_db.py --run run_1
python scripts/analyze.py --run run_1
python scripts/visualize_analysis.py --run run_1
python results_browser_app/browse_results.py --run run_1
```

---

For more details on each script's options, use the `--help` flag, e.g.:

```
python scripts/run_ollama.py --help
```
