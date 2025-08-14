import sys
import json
import argparse
import os

MODELS = [
    "o1-mini", "o3-mini", "o4-mini", "o3", "o1",
    "gpt-4o-mini", "gpt-4o", "gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1"
]

def main():
    parser = argparse.ArgumentParser(description="Convert prompts file to OpenAI batch format for multiple models.")
    parser.add_argument("--threshold", type=int, default=None, help="Threshold for bodies and color files (e.g., 10 or 20)")
    parser.add_argument("--run", default="run_1", help="Run directory name (default: run_1)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of prompts to include in each batch file")
    parser.add_argument("--models", type=str, default=None, help="Comma-separated list of models to use (default: all)")
    args = parser.parse_args()

    if args.threshold is None:
        parser.error("--threshold is required.")
    threshold = args.threshold
    run_dir = os.path.join("data", args.run)
    bodies_file = os.path.join(run_dir, "parsed_inputs", f"bodies_{threshold}.jsonl")
    color_file = os.path.join(run_dir, "parsed_inputs", f"bodies_{threshold}_colormap.jsonl")
    batch_dir = os.path.join(run_dir, f"open_ai_batches_{threshold}")
    os.makedirs(batch_dir, exist_ok=True)
    base = f"bodies_{threshold}.jsonl"

    # Determine models to use
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        models = MODELS

    # Prepare output file handles for each model
    outfiles = {}
    for model in models:
        out_path = os.path.join(batch_dir, f"openai_batch_{model}_{base}")
        outfiles[model] = open(out_path, "w")

    count = 0
    with open(bodies_file) as infile:
        for line in infile:
            if args.limit is not None and count >= args.limit:
                break
            if not line.strip():
                continue
            prompt_obj = json.loads(line)
            idx = prompt_obj.get("index")
            prompt = prompt_obj.get("prompt")
            if prompt is None:
                continue
            for model in models:
                batch_obj = {
                    "custom_id": f"{idx}_{model}" if idx is not None else model,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ]
                    }
                }
                outfiles[model].write(json.dumps(batch_obj) + "\n")
            count += 1

    for f in outfiles.values():
        f.close()

if __name__ == "__main__":
    main()
