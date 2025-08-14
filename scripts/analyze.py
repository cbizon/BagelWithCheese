import json
import os
import argparse
import sys
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser(description="Aggregate evaluation results by model and threshold.")
    parser.add_argument('--run', help='Run directory name')
    parser.add_argument("--input", help="Input evaluation summary JSONL file")
    args = parser.parse_args()

    run_dir = os.path.join('data', args.run)
    input_path = os.path.join(run_dir, "evaluation_summary_all.jsonl")

    if not os.path.exists(input_path):
        print(f"Error: {input_path} does not exist.")
        sys.exit(1)

    # Aggregate stats: model -> threshold -> stats
    stats = defaultdict(lambda: defaultdict(lambda: {"completed": 0, "single_exact": 0, "json_error": 0, "total_exact": 0, "sum_frac_missing": 0.0, "sum_frac_mismatched": 0.0, "sum_duration": 0.0, "duration_count": 0, "sum_cost": 0.0, "cost_count": 0}))

    with open(input_path) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            model = row.get("model name", "unknown")
            threshold = row.get("threshold", "unknown")
            stats[model][threshold]["completed"] += 1
            num_exact = row.get("Number of exact matches", 0)
            if num_exact == 1:
                stats[model][threshold]["single_exact"] += 1
            stats[model][threshold]["total_exact"] += num_exact
            if not row.get("Valid JSON", True):
                stats[model][threshold]["json_error"] += 1
            # Calculate fraction of missing and mismatched codes for this row
            colormap_length = row.get("Colormap Length", 0)
            num_missing = row.get("Number of missing codes", 0)
            num_mismatched = row.get("Number of mismatched codes", 0)
            frac_missing = num_missing / colormap_length if colormap_length else 0.0
            frac_mismatched = num_mismatched / colormap_length if colormap_length else 0.0
            stats[model][threshold]["sum_frac_missing"] += frac_missing
            stats[model][threshold]["sum_frac_mismatched"] += frac_mismatched
            # Duration
            duration = row.get("Duration (s)")
            if duration is not None:
                stats[model][threshold]["sum_duration"] += duration
                stats[model][threshold]["duration_count"] += 1
            # Cost
            cost = row.get("Cost (USD)")
            if cost is not None:
                stats[model][threshold]["sum_cost"] += cost
                stats[model][threshold]["cost_count"] += 1

    # Print header and write to file
    output_path = os.path.splitext(input_path)[0] + "_aggregated.tsv"
    with open(output_path, "w") as out:
        out.write("Model\tThreshold\tCompleted\tFracSingleExact\tFracJsonError\tAvgNumExact\tAvgFracMissing\tAvgFracMismatched\tAvgDuration\tTotalDuration\tAvgCost\tTotalCost\n")
        print("Model\tThreshold\tCompleted\tFracSingleExact\tFracJsonError\tAvgNumExact\tAvgFracMissing\tAvgFracMismatched\tAvgDuration\tTotalDuration\tAvgCost\tTotalCost")
        for model in sorted(stats):
            for threshold in sorted(stats[model], key=lambda x: (int(x) if str(x).isdigit() else x)):
                s = stats[model][threshold]
                completed = s["completed"]
                frac_single_exact = s["single_exact"] / completed if completed else 0
                frac_json_error = s["json_error"] / completed if completed else 0
                avg_num_exact = s["total_exact"] / completed if completed else 0
                avg_frac_missing = s["sum_frac_missing"] / completed if completed else 0
                avg_frac_mismatched = s["sum_frac_mismatched"] / completed if completed else 0
                # Duration columns
                avg_duration = s["sum_duration"] / s["duration_count"] if s["duration_count"] else ""
                if avg_duration != "":
                    total_seconds = float(avg_duration) * 232429
                    days = int(total_seconds // 86400)
                    hours = int((total_seconds % 86400) // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    total_duration_str = f"{days}d {hours}h {minutes}m"
                else:
                    total_duration_str = ""
                # Cost columns
                avg_cost = s["sum_cost"] / s["cost_count"] if s["cost_count"] else ""
                total_cost = float(avg_cost) * 232429 if avg_cost != "" else ""
                out.write(f"{model}\t{threshold}\t{completed}\t{frac_single_exact:.3f}\t{frac_json_error:.3f}\t{avg_num_exact:.3f}\t{avg_frac_missing:.3f}\t{avg_frac_mismatched:.3f}\t{avg_duration if avg_duration == '' else f'{avg_duration:.3f}'}\t{total_duration_str}\t{avg_cost if avg_cost == '' else f'{avg_cost:.4f}'}\t{total_cost if total_cost == '' else f'{total_cost:.0f}'}\n")
                print(f"{model}\t{threshold}\t{completed}\t{frac_single_exact:.3f}\t{frac_json_error:.3f}\t{avg_num_exact:.3f}\t{avg_frac_missing:.3f}\t{avg_frac_mismatched:.3f}\t{avg_duration if avg_duration == '' else f'{avg_duration:.3f}'}\t{total_duration_str}\t{avg_cost if avg_cost == '' else f'{avg_cost:.4f}'}\t{total_cost if total_cost == '' else f'{total_cost:.0f}'}")
    print(f"Aggregated results written to {output_path}")

if __name__ == "__main__":
    main()
