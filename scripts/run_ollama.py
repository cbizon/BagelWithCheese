import ollama
import json
import time
import glob
import os
import re
import argparse
from typing import List, Tuple, Set, Optional, Dict, Any
from openai import OpenAI
from response_schema import Response, CandidateResponse
from ollama import Client

# --- Utility Functions ---
# ModelConfig type: (name, format, url)
ModelConfig = Tuple[str, bool, str]

def run_prompt(idx: int, prompt: str, model: str, format: bool = True, url: str = "local") -> Tuple[str, dict]:
    """
    Run a prompt using the Ollama API.
    Returns:
        tuple: (message_content, full_response)
    """
    host = "http://localhost:11434" if url == "local" else url
    client = Client(host=host)
    chat_kwargs: Dict[str, Any] = dict(model=model, messages=[{"role": "user", "content": prompt}])
    try:
        if format:
            chat_kwargs["format"] = Response.model_json_schema()
            response = client.chat(**chat_kwargs)
            message_content = response['message']['content']
        else:
            response = client.chat(**chat_kwargs)
            message_content = response['message']['content']
            match = re.search(r'```json\s*(.*?)```', message_content, re.DOTALL)
            if match:
                message_content = match.group(1).strip()
        # Only print the length of the message_content
        print(f"[run_prompt] message_content length for idx={idx}: {len(message_content) if message_content else 0}")
        return message_content, response
    except Exception as e:
        print(f"[run_prompt] ERROR: Exception for idx={idx}, model={model}, url={url}: {e}")
        return "", {}

def get_prompts(bfile: str) -> List[dict]:
    """
    Get the prompts from the bodies file (JSONL, one JSON object per line).
    Returns:
        list: The prompt dicts.
    """
    prompts = []
    with open(bfile) as f:
        for line in f:
            if line.strip():
                prompts.append(json.loads(line))
    return prompts

def get_processed_indices(message_file_path: str) -> Set[int]:
    processed_indices = set()
    if os.path.exists(message_file_path):
        with open(message_file_path) as mf:
            for line in mf:
                try:
                    obj = json.loads(line)
                    processed_indices.add(obj["index"])
                except Exception:
                    continue
    return processed_indices

def report_progress(completed: int, total: int, avg: float, elapsed: float, walltime_seconds: Optional[int] = None) -> None:
    remaining = total - completed
    if walltime_seconds is not None:
        expected_total = completed + int((walltime_seconds - elapsed) / avg) if avg > 0 else completed
        expected_total = min(expected_total, total)
        print(f"Progress: {completed}/{total} | Avg: {avg:.2f}s | ETA: {((total-completed)*avg)/60:.1f} min | Elapsed: {elapsed/60:.1f} min | Est. to finish in walltime: {expected_total}")
    else:
        eta = avg * remaining
        print(f"Progress: {completed}/{total} | Avg: {avg:.2f}s | ETA: {eta/60:.1f} min | Elapsed: {elapsed/60:.1f} min")

def process_prompt(idx: int, prompt: str, model: str, format: bool, url: str, mf, jf) -> float:
    t0 = time.time()
    message_content, response = run_prompt(idx, prompt, model, format=format, url=url)
    t1 = time.time()
    # Only print the length of the message_content
    if not message_content:
        print(f"[process_prompt] WARNING: No content returned for idx={idx}, model={model}. Skipping file write.")
    else:
        print(f"[process_prompt] Writing to files for idx={idx}")
        mf.write(json.dumps({"index": idx, "content": message_content}) + '\n')
        response_copy = dict(response)
        if 'message' in response_copy and 'content' in response_copy['message']:
            response_copy['message'] = dict(response_copy['message'])
            del response_copy['message']['content']
        response_copy['index'] = idx
        jf.write(json.dumps(response_copy) + '\n')
    return t1 - t0

def ensure_dir_exists(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)

def get_models_to_run(all_models: List[ModelConfig], selected_models: Optional[List[str]]) -> List[ModelConfig]:
    if selected_models:
        return [m for m in all_models if m[0] in selected_models]
    return all_models

def get_thresholds_to_run(all_thresholds: List[int], selected_thresholds: Optional[List[int]]) -> List[int]:
    if selected_thresholds:
        return selected_thresholds
    return all_thresholds

def get_prompt_files(run_dir: str, thresholds: List[int]) -> List[str]:
    return [os.path.join(run_dir, "parsed_inputs", f"bodies_{t}.jsonl") for t in thresholds]

def run_prompts(
    prompts_file: str,
    model: str,
    message_file_path: str,
    jsonl_file_path: str,
    walltime_seconds: Optional[int] = None,
    format: bool = True,
    url: str = "local"
) -> None:
    prompts = get_prompts(prompts_file)
    start_time = time.time()
    i = 0
    processed_indices = get_processed_indices(message_file_path)
    # Always open in append mode to avoid overwriting
    mode = 'a'
    total = len(prompts)
    completed = len(processed_indices)
    print(f"Starting model '{model}' on {prompts_file}: {completed}/{total} already completed.")
    times: List[float] = []
    last_report = time.time()
    with open(message_file_path, mode) as mf, open(jsonl_file_path, mode) as jf:
        while (walltime_seconds is None or time.time() - start_time < walltime_seconds) and i < len(prompts):
            prompt_entry = prompts[i]
            prompt = prompt_entry["prompt"]
            idx = prompt_entry["index"]
            if idx in processed_indices:
                i += 1
                continue
            elapsed = time.time() - start_time
            duration = process_prompt(idx, prompt, model, format, url, mf, jf)
            times.append(duration)
            completed += 1
            i += 1
            if len(times) > 0 and (time.time() - last_report > 10 or completed == total):
                avg = sum(times) / len(times)
                report_progress(completed, total, avg, elapsed, walltime_seconds)
                last_report = time.time()

def test_llm_connection(model: str, url: str = "local", format: bool = True) -> None:
    """
    Test LLM connection by sending a simple message and printing the response.
    """
    print(f"\nTesting LLM connection for model '{model}' at url '{url}'...")
    prompt = "Hi, this is a test, please respond with only the word Hello"
    try:
        message_content, response = run_prompt(0, prompt, model, format=format, url=url)
        print(f"Test response: {message_content}")
    except Exception as e:
        print(f"Test failed: {e}")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', help='Run directory name (required)')
    parser.add_argument('--models', nargs='+', default=None, help='List of model names to run (default: all)')
    parser.add_argument('--thresholds', nargs='+', type=int, default=None, help='List of thresholds to use (default: all)')
    parser.add_argument('--walltime', type=int, default=None, help='Walltime in seconds per model (default: run to completion)')
    parser.add_argument('--test-llm', action='store_true', help='Test LLM connection for selected models and exit')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)
    ollama_results_dir = os.path.join(run_dir, 'ollama_results')
    ensure_dir_exists(ollama_results_dir)
    # ModelConfig: (name, format, url)
    all_models: List[ModelConfig] = [
        ("alibayram/medgemma:27B", True, "local"),
        ("gemma3:12B", True, "local"),
        ("gpt-oss", False, "local"),
        ("deepseek-r1", True, "local"),
        ("medgemma-27b-Q4", True, "https://healpaca.apps.renci.org")
        # Add more model configs here if needed
    ]
    models = get_models_to_run(all_models, args.models)
    if args.test_llm:
        for model, format, url in models:
            test_llm_connection(model, url, format)
        return
    all_thresholds: List[int] = [5, 10, 20]
    thresholds = get_thresholds_to_run(all_thresholds, args.thresholds)
    prompts_files = get_prompt_files(run_dir, thresholds)
    for model, format, url in models:
        print(model)
        for prompts_file in prompts_files:
            print("", prompts_file)
            base_name = f"{model.replace('/', '_').replace(':', '_')}__{os.path.basename(prompts_file).replace('.jsonl', '')}"
            message_file_path = os.path.join(ollama_results_dir, f"{base_name}_message_output.jsonl")
            jsonl_file_path = os.path.join(ollama_results_dir, f"{base_name}_response_output.jsonl")
            run_prompts(prompts_file, model, message_file_path, jsonl_file_path, walltime_seconds=args.walltime, format=format, url=url)

if __name__ == "__main__":
    main()
