import json
import argparse
import os
import csv

def build_abstracts_tsv(jsonl_path, output_dir):
    out_path = os.path.join(output_dir, 'abstracts.tsv')
    with open(jsonl_path) as f, open(out_path, 'w', newline='') as out_f:
        writer = csv.writer(out_f, delimiter='\t')
        writer.writerow(['pmid', 'abstract'])
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    pmid = str(obj.get('pmid'))
                    abstract = obj.get('text')
                    if pmid and abstract:
                        writer.writerow([pmid, abstract])
                except Exception:
                    print(f"Error processing line: {line.strip()}")
    print(f"Wrote abstracts.tsv")

def build_entities_tsv(entity_map_path, expanded_ann_path, output_dir):
    out_path = os.path.join(output_dir, 'entities.tsv')
    seen = set()
    with open(out_path, 'w', newline='') as out_f:
        writer = csv.writer(out_f, delimiter='\t')
        writer.writerow(['identifier', 'label', 'description', 'type', 'taxon'])
        # First source: entity_map_path (JSON)
        with open(entity_map_path) as f:
            obj = json.load(f)
            for entity_list in obj.values():
                for ann in entity_list:
                    med = ann.get('medmentions')
                    if med:
                        identifier = med.get('identifier')
                        if identifier and identifier not in seen:
                            seen.add(identifier)
                            label = med.get('label')
                            description = med.get('description')
                            biolink_types = med.get('biolink_types')
                            type_val = biolink_types[0] if biolink_types and len(biolink_types) > 0 else None
                            taxon = med.get('taxon') if 'taxon' in med else None
                            writer.writerow([identifier, label, description, type_val, taxon])
        # Second source: expanded_annotations.jsonl (JSONL)
        with open(expanded_ann_path) as f:
            for line in f:
                if line.strip():
                    try:
                        obj = json.loads(line)
                        for identifier, val in obj.items():
                            if identifier not in seen:
                                seen.add(identifier)
                                label = val.get('name')
                                description = val.get('description')
                                type_val = val.get('category')
                                taxon = val.get('taxa') if 'taxa' in val else None
                                writer.writerow([identifier, label, description, type_val, taxon])
                    except Exception as e:
                        print(f"Error processing line in expanded_annotations.jsonl: {e}")
    print(f"Wrote entities.tsv")

def build_recognized_entities_tsv(annotation_list_path, output_dir):
    out_path = os.path.join(output_dir, 'recognized_entities.tsv')
    with open(annotation_list_path) as f, open(out_path, 'w', newline='') as out_f:
        writer = csv.writer(out_f, delimiter='\t')
        writer.writerow(['id', 'pmid', 'expanded_text', 'original_text'])
        for line in f:
            if line.strip():
                obj = json.loads(line)
                writer.writerow([obj['id'], str(obj['pmid']), obj['expanded_text'], obj['original_text']])
    print(f"Wrote recognized_entities.tsv")

def build_results_tsv(annotation_list_path, entity_map_path, colormap_path, results_tsv_path, output_dir):
    out_path = os.path.join(output_dir, 'results.tsv')
    import collections
    import csv
    # Build (pmid, original_text) -> id map
    pmid_orig_to_id = {}
    with open(annotation_list_path) as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                key = (str(obj['pmid']), obj['original_text'])
                pmid_orig_to_id[key] = obj['id']
    # Prepare to write results
    seen = set()
    rows = []
    # Insert medmentions results
    with open(entity_map_path) as f:
        obj = json.load(f)
        for entity_list in obj.values():
            for ann in entity_list:
                med = ann.get('medmentions')
                if med:
                    pmid = str(ann.get('pmid'))
                    original_text = ann.get('original_entity')
                    key = (pmid, original_text)
                    idx = pmid_orig_to_id.get(key)
                    identifier = med.get('identifier')
                    if idx is not None and identifier is not None:
                        row_key = (idx, 'medmentions')
                        if row_key not in seen:
                            seen.add(row_key)
                            rows.append([idx, 'medmentions', identifier])
    # Insert model results
    # Load colormap: index -> {color_code: identifier}
    colormap = {}
    with open(colormap_path) as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                idx = obj["index"]
                identifiers = obj.get("identifiers", {})
                colormap[idx] = identifiers
    with open(results_tsv_path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            idx = int(row["index"])
            model = row["model"]
            color_code = row["exact_matches"] if row["exact_matches"] != "" else None
            identifier = None
            if color_code is not None and color_code.lower() != "null":
                identifier = colormap.get(idx, {}).get(color_code)
            row_key = (idx, model)
            if row_key not in seen:
                seen.add(row_key)
                rows.append([idx, model, identifier])
    # Write to TSV
    with open(out_path, 'w', newline='') as out_f:
        writer = csv.writer(out_f, delimiter='\t')
        writer.writerow(['idx', 'model', 'identifier'])
        for row in rows:
            writer.writerow(row)
    print(f"Wrote results.tsv")

def build_assessment_tsv(output_dir):
    out_path = os.path.join(output_dir, 'assessment.tsv')
    with open(out_path, 'w', newline='') as out_f:
        writer = csv.writer(out_f, delimiter='\t')
        writer.writerow(['idx', 'identifier', 'user', 'assessment'])
    print(f"Wrote assessment.tsv (empty)")

# More functions for model_results will be added next.

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='Run name (output will be placed in data/{run})')
    args = parser.parse_args()
    input_jsonl = 'input_data/corpus_pubtator_normalized_8-4-2025.jsonl'
    entity_map_path = 'input_data/expanded_annotations_entity_map.json'
    expanded_ann_path = 'input_data/expanded_annotations.jsonl'
    output_dir = os.path.join('data', args.run)
    os.makedirs(output_dir, exist_ok=True)
    annotation_list_path = os.path.join(output_dir, 'parsed_inputs', 'annotation_list.jsonl')
    build_abstracts_tsv(input_jsonl, output_dir)
    build_entities_tsv(entity_map_path, expanded_ann_path, output_dir)
    build_recognized_entities_tsv(annotation_list_path, output_dir)
    colormap_path = os.path.join(output_dir, 'parsed_inputs', 'bodies_10_colormap.jsonl')
    results_tsv_path = os.path.join(output_dir, 'results_all.tsv')
    build_results_tsv(annotation_list_path, entity_map_path, colormap_path, results_tsv_path, output_dir)
    build_assessment_tsv(output_dir)
    # More calls for model_results and assessment will be added next.

if __name__ == '__main__':
    main()
