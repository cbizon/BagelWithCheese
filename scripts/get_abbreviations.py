import json
import os
import requests
import ollama
import re
import datetime
import argparse

def load_prompt_template(template_path):
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_corpus_jsonl(corpus_path):
    with open(corpus_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                yield obj['pmid'], obj['text']

def call_ollama(prompt, model="gpt-oss", format=None):
    # This matches the approach in run_ollama.py
    if format:
        response = ollama.chat(format=format, model=model, messages=[{"role": "user", "content": prompt}])
        message_content = response['message']['content']
    else:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        message_content = response['message']['content']
        match = re.search(r'```json\s*(.*?)```', message_content, re.DOTALL)
        if match:
            message_content = match.group(1).strip()
    duration = response.get("total_duration", 0)/1e9
    return message_content, duration

def get_processed_pmids(output_path):
    processed_pmids = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as out_f:
            for line in out_f:
                if line.strip():
                    try:
                        row = json.loads(line)
                        processed_pmids.add(row["pmid"])
                    except Exception:
                        continue
    return processed_pmids

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='run_1', help='Run directory name (default: run_1)')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)
    template_path = os.path.join('input_data', "abbreviation_prompt_template")
    corpus_path = os.path.join('input_data', "corpus_pubtator_normalized_8-4-2025.jsonl")
    output_path = os.path.join('input_data', "abbreviation_llm_results.jsonl")
    prompt_template = load_prompt_template(template_path)
    processed_pmids = get_processed_pmids(output_path)
    already_done = len(processed_pmids)
    # Always use append mode
    with open(output_path, "a", encoding="utf-8") as out_f:
        total = 4392
        sum_duration = 0.0
        num_this_run = 0
        for idx, (pmid, text) in enumerate(load_corpus_jsonl(corpus_path), 1):
            if pmid in processed_pmids:
                continue
            prompt = f"{prompt_template}\n{text}"
            response_json, duration = call_ollama(prompt)
            sum_duration += duration
            num_this_run += 1
            already_done += 1
            avg_duration = sum_duration / num_this_run
            remaining = total - already_done
            est_remaining = avg_duration * remaining
            est_td = datetime.timedelta(seconds=est_remaining)
            est_str = str(est_td).split('.')[0]
            try:
                abbreviation_map = json.loads(response_json)
            except Exception as e:
                print(f"Error parsing abbreviation JSON for PMID {pmid}: {e}\nRaw response: {response_json}")
                abbreviation_map = []
            row = {
                "pmid": pmid,
                "abbreviation_map": abbreviation_map
            }
            out_f.write(json.dumps(row) + "\n")
            out_f.flush()
            print(f"Processed {already_done} of {total}. Took {duration:.2f} seconds. Avg: {avg_duration:.2f} s. Est. remaining: {est_str}")

if __name__ == "__main__":
    main()
