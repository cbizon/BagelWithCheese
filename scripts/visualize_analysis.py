import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os

def parse_duration_to_days(s):
    if pd.isnull(s) or not isinstance(s, str):
        return None
    s = s.strip()
    if s == '':
        return None
    # Try pandas to_timedelta
    try:
        td = pd.to_timedelta(s)
        return td.total_seconds() / 86400
    except Exception:
        pass
    # Try manual parsing (e.g., '1 days 02:03:04')
    import re
    match = re.match(r"(?:(\d+) days? )?(\d+):(\d+):(\d+)", s)
    if match:
        days = int(match.group(1)) if match.group(1) else 0
        hours = int(match.group(2))
        minutes = int(match.group(3))
        seconds = int(match.group(4))
        return days + (hours * 3600 + minutes * 60 + seconds) / 86400
    return None

def main():
    parser = argparse.ArgumentParser(description="Visualize analysis output for BAGEL.")
    parser.add_argument('--run', default='run_1', help='Run directory name (default: run_1)')
    parser.add_argument('--input', help='Aggregated analysis TSV file')
    parser.add_argument('--out', help='Output plot file (for duration plot)')
    args = parser.parse_args()

    run_dir = os.path.join('data', args.run)
    input_path = args.input if args.input else os.path.join(run_dir, 'evaluation_summary_all_aggregated.tsv')
    viz_dir = os.path.join(run_dir, 'visualizations')
    os.makedirs(viz_dir, exist_ok=True)
    out_path = args.out if args.out else os.path.join(viz_dir, 'avg_duration_vs_threshold.png')

    # Generalized: Plot all relevant columns vs Threshold by Model
    df_agg = pd.read_csv(input_path, sep='\t')
    df_agg.columns = [col.strip() for col in df_agg.columns]
    df_agg['Threshold'] = pd.to_numeric(df_agg['Threshold'], errors='coerce')
    df_agg = df_agg.dropna(subset=['Threshold', 'Model'])
    columns_to_plot = [
        'Completed', 'FracSingleExact', 'FracJsonError', 'AvgNumExact',
        'AvgFracMissing', 'AvgFracMismatched', 'AvgDuration', 'TotalDuration',
        'AvgCost', 'TotalCost'
    ]
    for col in columns_to_plot:
        if col not in df_agg.columns:
            continue
        if col == 'TotalDuration':
            df_plot = df_agg[df_agg[col] != '']
            df_plot['TotalDurationDays'] = df_plot[col].apply(parse_duration_to_days)
            df_plot = df_plot.dropna(subset=['TotalDurationDays', 'Threshold', 'Model'])
            if df_plot.empty:
                continue
            sorted_models = sorted(df_plot['Model'].unique())
            plt.figure(figsize=(10, 6))
            for model in sorted_models:
                group = df_plot[df_plot['Model'] == model]
                plt.plot(group['Threshold'], group['TotalDurationDays'], marker='o', label=model)
            plt.xlabel('Threshold')
            plt.ylabel('Total Duration (days)')
            plt.title('Total Duration vs Threshold by Model')
            plt.legend()
            plt.tight_layout()
            plt.savefig(out_path)
            print(f"Saved plot to {out_path}")
        else:
            df_plot = df_agg[df_agg[col] != '']
            df_plot[col] = pd.to_numeric(df_plot[col], errors='coerce')
            df_plot = df_plot.dropna(subset=[col, 'Threshold', 'Model'])
            if df_plot.empty:
                continue
            # For cost columns, only plot models that actually have cost data
            if col in ['AvgCost', 'TotalCost']:
                # Find models with at least one non-null, non-zero cost value
                models_with_cost = df_plot.groupby('Model')[col].apply(lambda x: (x.notnull() & (x != 0)).any())
                valid_models = models_with_cost[models_with_cost].index
                df_plot = df_plot[df_plot['Model'].isin(valid_models)]
                if df_plot.empty:
                    continue
                # Sort models by value at threshold=20 (descending)
                cost_at_20 = df_plot[df_plot['Threshold'] == 20].set_index('Model')[col]
                sorted_models = cost_at_20.sort_values(ascending=False).index.tolist()
            else:
                sorted_models = sorted(df_plot['Model'].unique())
            plt.figure(figsize=(10, 6))
            for model in sorted_models:
                group = df_plot[df_plot['Model'] == model]
                plt.plot(group['Threshold'], group[col], marker='o', label=model)
            plt.xlabel('Threshold')
            plt.ylabel(col)
            plt.title(f'{col} vs Threshold by Model')
            plt.legend(title='Model', bbox_to_anchor=(1.05, 1), loc='upper left')
            plt.tight_layout()
            out_path = os.path.join(viz_dir, f'{col.lower()}_vs_threshold.png')
            plt.savefig(out_path)
            print(f"Saved plot to {out_path}")

if __name__ == "__main__":
    main()
