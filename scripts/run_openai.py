import os
import sys
import time
import json
import argparse
import requests
import mimetypes
import concurrent.futures

OPENAI_API_URL = "https://api.openai.com/v1/batches"
OPENAI_FILES_URL = "https://api.openai.com/v1/files"
api_key = os.environ.get("OPENAI_LITCOIN_KEY")


def upload_file(batch_file):
    if not api_key:
        print("OPENAI_API_KEY environment variable not set.")
        sys.exit(1)
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    files = {
        'file': (os.path.basename(batch_file), open(batch_file, 'rb'), 'application/jsonl')
    }
    data = {'purpose': 'batch'}
    response = requests.post(
        OPENAI_FILES_URL,
        headers=headers,
        files=files,
        data=data
    )
    if response.status_code != 200:
        print(f"File upload failed: {response.status_code} {response.text}")
        sys.exit(1)
    file_info = response.json()
    file_id = file_info["id"]
    print(f"File uploaded. File ID: {file_id}")
    return file_id

def submit_batch(batch_file):
    file_id = upload_file(batch_file)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    batch_body = {
        "input_file_id": file_id,
        "endpoint": "/v1/chat/completions",
        "completion_window": "24h"
    }
    response = requests.post(
        OPENAI_API_URL,
        headers=headers,
        json=batch_body
    )
    if response.status_code != 200:
        print(f"Batch submission failed: {response.status_code} {response.text}")
        sys.exit(1)
    batch_info = response.json()
    batch_id = batch_info["id"]
    print(f"Batch submitted. Batch ID: {batch_id}")
    return batch_id

def monitor_batch(batch_id, poll_interval=10, batch_name=None):
    headers = {"Authorization": f"Bearer {api_key}"}
    status_url = f"{OPENAI_API_URL}/{batch_id}"
    while True:
        response = requests.get(status_url, headers=headers)
        if response.status_code != 200:
            print(f"Error checking batch status: {response.status_code} {response.text}")
            sys.exit(1)
        batch_info = response.json()
        status = batch_info.get("status")
        name_str = f" ({batch_name})" if batch_name else ""
        print(f"Batch status{name_str}: {status}")
        if status in ("completed", "failed", "cancelled"):
            return batch_info
        time.sleep(poll_interval)

def download_results(batch_info, output_file):
    headers = {"Authorization": f"Bearer {api_key}"}
    output_file_id = batch_info.get("output_file_id")
    if not output_file_id:
        print("No output_file_id found in batch info. Full batch_info:")
        print(json.dumps(batch_info, indent=2))
        sys.exit(1)
    result_url = f"{OPENAI_FILES_URL}/{output_file_id}/content"
    response = requests.get(result_url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to download results: {response.status_code} {response.text}")
        sys.exit(1)
    with open(output_file, "wb") as f:
        f.write(response.content)
    print(f"Results downloaded to {output_file}")

def process_batch_file(batch_file, output_dir):
    batch_id = submit_batch(batch_file)
    batch_name = os.path.basename(batch_file)
    batch_info = monitor_batch(batch_id, batch_name=batch_name)
    output_file = os.path.join(output_dir, batch_name.replace("openai_batch_", "openai_results_"))
    if batch_info.get("status") == "completed":
        download_results(batch_info, output_file)
    else:
        print(f"Batch {batch_file} did not complete successfully. Status: {batch_info.get('status')}")

def process_batch_file_concurrent(batch_file, output_dir):
    try:
        batch_id = submit_batch(batch_file)
        batch_name = os.path.basename(batch_file)
        batch_info = monitor_batch(batch_id, batch_name=batch_name)
        output_file = os.path.join(output_dir, batch_name.replace("openai_batch_", "openai_results_"))
        if batch_info.get("status") == "completed":
            download_results(batch_info, output_file)
        else:
            print(f"Batch {batch_file} did not complete successfully. Status: {batch_info.get('status')}")
    except Exception as e:
        print(f"Error processing {batch_file}: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='run_1', help='Run directory name (default: run_1)')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)
    # Find all open_ai_batches_* directories
    batch_dirs = [os.path.join(run_dir, d) for d in os.listdir(run_dir)
                  if d.startswith('open_ai_batches_') and os.path.isdir(os.path.join(run_dir, d))]
    all_batch_files = []
    for batch_dir in batch_dirs:
        batch_files = [os.path.join(batch_dir, f) for f in os.listdir(batch_dir) if f.endswith('.jsonl')]
        all_batch_files.extend(batch_files)
    if not all_batch_files:
        print(f"No batch files found in {run_dir}.")
        return
    # Output dir for each threshold
    output_dirs = {}
    for batch_dir in batch_dirs:
        threshold = batch_dir.split('_')[-1]
        output_dir = os.path.join(run_dir, f'open_ai_results_{threshold}')
        os.makedirs(output_dir, exist_ok=True)
        output_dirs[batch_dir] = output_dir
    def get_output_dir(batch_file):
        for batch_dir, output_dir in output_dirs.items():
            if batch_file.startswith(batch_dir):
                return output_dir
        return run_dir  # fallback
    num_workers = len(all_batch_files)
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(process_batch_file_concurrent, batch_file, get_output_dir(batch_file)) for batch_file in all_batch_files]
        for future in concurrent.futures.as_completed(futures):
            pass

if __name__ == "__main__":
    main()
