import csv
import json
import os
import re
import glob
from pydantic import ValidationError
from response_schema import Response

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

def load_jsonl_with_index(path):
    results = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            # For OpenAI results, use custom_id as index if present
            if "custom_id" in obj and "index" not in obj:
                # Try to extract integer index from custom_id (e.g., "0_gpt-4.1-mini")
                m = re.match(r"(\d+)_", str(obj["custom_id"]))
                if m:
                    obj["index"] = int(m.group(1))
            results.append(obj)
    return results

def build_index_map(entries):
    return {entry["index"]: entry for entry in entries if "index" in entry}

def evaluate_ollama_outputs(colormap_path, output_path, model_name, threshold):
    color_maps = load_jsonl(colormap_path)
    outputs = load_jsonl_with_index(output_path)
    # Infer and load response_output file
    response_output_path = os.path.join(os.path.dirname(output_path), 'response_output'.join(os.path.basename(output_path).split('message_output')))
    if not os.path.exists(response_output_path):
        raise FileNotFoundError(f"Ollama response output file not found: {response_output_path}")
    response_outputs = load_jsonl(response_output_path)
    response_by_index = build_index_map(response_outputs)
    color_map_by_index = build_index_map(color_maps)
    output_by_index = build_index_map(outputs)
    rows = []
    for idx, output in output_by_index.items():
        color_map = color_map_by_index.get(idx, {})
        response = response_by_index.get(idx, {})
        row, _ = parse_candidates_and_build_row(idx, color_map, output, response, model_name, threshold)
        rows.append(row)
    return rows

def parse_candidates_and_build_row(idx, color_map, output, response, model_name, threshold, extra_fields=None):
    """
    Shared logic for parsing candidates and building a result row.
    extra_fields: dict of additional fields to add to the row (e.g., duration, cost)
    """
    duration_s = None
    if response:
        duration_ns = response.get("total_duration", None)
        if duration_ns is not None:
            duration_s = float(duration_ns) / 1e9
    missing = 0
    mismatched = 0
    num_exact = 0
    exact_candidates = []
    valid_json = False
    content = get_llm_content(output)
    if not content:
        missing = len(color_map.get("labels", {}))
        candidates = []
    else:
        try:
            content_json = json.loads(content)
            try:
                Response(**content_json)
                valid_json = True
            except ValidationError as ve:
                valid_json = False
                print(f"Validation error for index {idx}: {ve}")
        except Exception:
            missing = len(color_map.get("labels", {}))
            candidates = []
        else:
            candidates = content_json.get("candidates", [])
            if valid_json:
                output_map = {c["color_code"]: c["candidate"] for c in candidates if "color_code" in c}
                malformed = [c for c in candidates if "color_code" not in c]
                if malformed:
                    print(f"Warning: Skipping malformed candidates at index {idx}: {malformed}")
                for color_code, label in color_map.get("labels", {}).items():
                    if color_code not in output_map:
                        missing += 1
                    elif output_map[color_code] != label:
                        mismatched += 1
                        print(f"MISMATCH index {idx}: color_code={color_code}, input_label={label}, output_label={output_map[color_code]}")
                for c in candidates:
                    if c.get("relation_type") == "exact":
                        num_exact += 1
                        exact_candidates.append(c.get("candidate", ""))
    colormap_length = len(color_map.get("labels", {}))
    candidate_list_length = len(candidates)
    row = {
        "index": idx,
        "entity": color_map.get("entity", ""),
        "model name": model_name,
        "threshold": threshold,
        "Number of missing codes": missing,
        "Number of mismatched codes": mismatched,
        "Number of exact matches": num_exact,
        "exact candidates": "|".join(exact_candidates),
        "Valid JSON": valid_json,
        "Colormap Length": colormap_length,
        "Candidate List Length": candidate_list_length
    }
    row['candidates'] = candidates
    if duration_s is not None:
        row["Duration (s)"] = duration_s
    if extra_fields:
        row.update(extra_fields)
    return row, candidates

def parse_pricing(pricing_path):
    pricing = {}
    with open(pricing_path) as f:
        header = f.readline().strip().split('\t') if '\t' in f.readline() else f.readline().strip().split()
        for line in f:
            if not line.strip() or line.startswith('Model'):
                continue
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            model = parts[0]
            input_price = float(parts[1].replace('$', '')) if len(parts) > 1 else 0.0
            cached_input_price = float(parts[2].replace('$', '')) if len(parts) > 2 and parts[2] != '-' else 0.0
            output_price = float(parts[3].replace('$', '')) if len(parts) > 3 and parts[3] != '-' else 0.0
            pricing[model] = {
                'input': input_price,
                'cached_input': cached_input_price,
                'output': output_price
            }
    return pricing

def evaluate_openai_outputs(colormap_path, openai_results_path, model_name, threshold, pricing):
    color_maps = load_jsonl(colormap_path)
    color_map_by_index = build_index_map(color_maps)
    rows = []
    with open(openai_results_path) as f:
        for line in f:
            if not line.strip():
                continue
            result = json.loads(line)
            # Extract integer index from custom_id (e.g., "170_gpt-4.1" -> 170)
            idx = result.get("custom_id")
            idx_int = None
            if idx is not None:
                m = re.match(r"(\d+)_", str(idx))
                if m:
                    idx_int = int(m.group(1))
                else:
                    try:
                        idx_int = int(idx)
                    except Exception:
                        idx_int = idx  # fallback to string if not parseable
            else:
                idx_int = None
            color_map = color_map_by_index.get(idx_int, {})
            response_obj = result.get("response", {})
            model_name_final = None
            body = response_obj.get("body") if response_obj else None
            usage = body.get("usage") if body else None
            prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
            cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) if usage and usage.get("prompt_tokens_details") else 0
            completion_tokens = usage.get("completion_tokens", 0) if usage else 0
            # Set model_name_final for pricing lookup
            if body and isinstance(body, dict):
                model_name_final = body.get("model", model_name)
            else:
                model_name_final = model_name
            # Pricing lookup: robust model name matching
            price_info = find_price_info(model_name_final, pricing)
            input_price = price_info.get('input', 0.0)
            cached_input_price = price_info.get('cached_input', 0.0)
            output_price = price_info.get('output', 0.0)
            # Calculate cost (per 1M tokens)
            total_cost = ((prompt_tokens-cached_tokens)*input_price + cached_tokens*cached_input_price + completion_tokens*output_price) / 1_000_000.0
            # Parse content JSON from OpenAI message
            content = None
            if body and isinstance(body, dict):
                choices = body.get("choices", [])
                if choices and "message" in choices[0]:
                    content = choices[0]["message"].get("content")
            # Strip markdown code block if present
            if content and content.strip().startswith('```'):
                match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            # Parse content as JSON for candidates
            candidates = []
            if content:
                try:
                    content_json = json.loads(content)
                    candidates = content_json.get("candidates", [])
                except Exception:
                    candidates = []
            output = result.copy()
            # Attach parsed candidates for downstream use
            output["_parsed_candidates"] = candidates
            response = None  # Not used for OpenAI
            extra_fields = {"Cost (USD)": total_cost}
            row, _ = parse_candidates_and_build_row(idx_int, color_map, output, response, model_name_final, threshold, extra_fields=extra_fields)
            rows.append(row)
    return rows

def find_ollama_results(data_dir):
    return glob.glob(os.path.join(data_dir, 'ollama_results', '*_message_output.jsonl'))

def find_openai_results(data_dir):
    # Find all openai_results_*.jsonl recursively in data/
    return glob.glob(os.path.join(data_dir, '**', 'openai_results_*.jsonl'), recursive=True)

def aggregate_all_results(data_dir="../data"):
    ollama_files = find_ollama_results(data_dir)
    openai_files = find_openai_results(data_dir)
    all_files = ollama_files + openai_files
    print(f"Found {len(ollama_files)} Ollama result files and {len(openai_files)} OpenAI result files.")
    return all_files

def infer_message_file(model_name):
    safe_model = model_name.replace('/', '_').replace(':', '_')
    base = f"{safe_model}__bodies_message_output.jsonl"
    if os.path.exists(base):
        return base
    base_json = f"{safe_model}__bodies_message_output.json"
    if os.path.exists(base_json):
        return base_json
    raise FileNotFoundError(f"Could not find message output file for model={model_name}")

def infer_colormap_file():
    base = "bodies_colormap.jsonl"
    if os.path.exists(base):
        return base
    base_json = "bodies_colormap.json"
    if os.path.exists(base_json):
        return base_json
    raise FileNotFoundError(f"Could not find colormap file")

def get_llm_content(output):
    """Extracts the LLM response content string from an output dict, handling OpenAI and Ollama formats."""
    content = None
    if "response" in output and "body" in output["response"]:
        body = output["response"]["body"]
        if isinstance(body, dict):
            choices = body.get("choices", [])
            if choices and "message" in choices[0]:
                content = choices[0]["message"].get("content")
                # Strip markdown code block if present
                if content and content.strip().startswith('```'):
                    match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
                    if match:
                        content = match.group(1).strip()
    if content is None:
        # Ollama or fallback
        content = output.get("content")
    return content

def find_price_info(model_name_final, pricing):
    if model_name_final in pricing:
        return pricing[model_name_final]
    # Try to match by prefix (e.g., gpt-4o-mini in gpt-4o-mini-2024-07-18)
    for k in pricing:
        if model_name_final.startswith(k):
            return pricing[k]
    # Try to match by removing date/version suffixes
    base = re.split(r'[-_][0-9]{4,}', model_name_final)[0]
    if base in pricing:
        return pricing[base]
    # Try substring match
    for k in pricing:
        if k in model_name_final:
            return pricing[k]
    print(f"Warning: No pricing found for model {model_name_final}")
    return {'input': 0.0, 'cached_input': 0.0, 'output': 0.0}

def aggregate_match_types_across_models(model_results, output_path):
    """
    model_results: list of dicts with keys: model name, threshold, index, candidates (list of dicts with color_code, relation_type)
    Writes a CSV with columns: model, threshold, index, exact_matches, subclass_matches, superclass_matches, related_matches, none_matches
    """
    import csv
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow([
            'model', 'threshold', 'index', 'exact_matches', 'subclass_matches', 'superclass_matches', 'related_matches', 'none_matches'
        ])
        for row in model_results:
            match_types = {'exact': [], 'subclass': [], 'superclass': [], 'related': [], 'none': []}
            # Try to get candidates from 'candidates', '_parsed_candidates', or skip if not present
            candidates = row.get('candidates')
            if candidates is None:
                candidates = row.get('_parsed_candidates', [])
            for c in candidates:
                rel = c.get('relation_type', 'none')
                code = c.get('color_code')
                if code is not None:
                    match_types.setdefault(rel, []).append(code)
            index_val = row.get('index')
            writer.writerow([
                row.get('model name'),
                row.get('threshold'),
                index_val,
                ','.join(match_types['exact']),
                ','.join(match_types['subclass']),
                ','.join(match_types['superclass']),
                ','.join(match_types['related']),
                ','.join(match_types['none'])
            ])

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Aggregate and evaluate all Ollama and OpenAI results.")
    parser.add_argument('--run', required=True, help='Run directory name (required)')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)

    # Find all thresholds by looking for colormap files
    parsed_inputs_dir = os.path.join(run_dir, 'parsed_inputs')
    colormap_files = [f for f in os.listdir(parsed_inputs_dir) if f.endswith('_colormap.jsonl')]
    thresholds = sorted(set(f.split('_')[1] for f in colormap_files if f.startswith('bodies_')))

    # Pricing info (optional, only for OpenAI)
    pricing_path = os.path.join(os.path.dirname(__file__), '../input_data/pricing.txt')
    pricing = parse_pricing(pricing_path) if os.path.exists(pricing_path) else {}

    all_rows = []
    for threshold in thresholds:
        colormap_path = os.path.join(parsed_inputs_dir, f'bodies_{threshold}_colormap.jsonl')
        # Evaluate Ollama results
        ollama_dir = os.path.join(run_dir, 'ollama_results')
        if os.path.isdir(ollama_dir):
            for fname in os.listdir(ollama_dir):
                if fname.endswith(f'bodies_{threshold}_message_output.jsonl'):
                    model = fname.split('__')[0]
                    output_path = os.path.join(ollama_dir, fname)
                    try:
                        rows = evaluate_ollama_outputs(colormap_path, output_path, model, threshold)
                        all_rows.extend(rows)
                        print(f"Evaluated Ollama: {fname} ({len(rows)} rows)")
                    except Exception as e:
                        print(f"Error evaluating Ollama {fname}: {e}")
        # Evaluate OpenAI results
        openai_dir = os.path.join(run_dir, f'open_ai_results_{threshold}')
        if os.path.isdir(openai_dir):
            for fname in os.listdir(openai_dir):
                if fname.endswith('.jsonl'):
                    # Model name is between 'openai_results_' and '_bodies'
                    m = re.match(r'openai_results_(.+?)_bodies_.*\\.jsonl', fname)
                    model = m.group(1) if m else 'unknown'
                    openai_results_path = os.path.join(openai_dir, fname)
                    try:
                        rows = evaluate_openai_outputs(colormap_path, openai_results_path, model, threshold, pricing)
                        all_rows.extend(rows)
                        print(f"Evaluated OpenAI: {fname} ({len(rows)} rows)")
                    except Exception as e:
                        print(f"Error evaluating OpenAI {fname}: {e}")
    print(f"Evaluated {len(all_rows)} outputs in total.")
    # Write all_rows to JSONL
    if all_rows:
        jsonl_path = os.path.join(run_dir, "evaluation_summary_all.jsonl")
        with open(jsonl_path, "w") as f:
            for row in all_rows:
                f.write(json.dumps(row) + "\n")
        print(f"Wrote JSONL results to {jsonl_path}")
        # Write results_all.tsv for build_db.py compatibility
        results_all_tsv_path = os.path.join(run_dir, "results_all.tsv")
        aggregate_match_types_across_models(all_rows, results_all_tsv_path)
        print(f"Wrote TSV results to {results_all_tsv_path}")

if __name__ == "__main__":
    main()
