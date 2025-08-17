import json
import argparse
import os

from pydantic import BaseModel, Field
from typing import List

colors = ['alizarin', 'amaranth', 'amber', 'amethyst', 'apricot', 'aqua', 'aquamarine', 'asparagus', 'auburn', 'azure', 'beige', 'bistre', 'black', 'blue', 'blue-green', 'blue-violet', 'bondi-blue', 'brass', 'bronze', 'brown', 'buff', 'burgundy', 'camouflage-green', 'caput-mortuum', 'cardinal', 'carmine', 'carrot-orange', 'celadon', 'cerise', 'cerulean', 'champagne', 'charcoal', 'chartreuse', 'cherry-blossom-pink', 'chestnut', 'chocolate', 'cinnabar', 'cinnamon', 'cobalt', 'copper', 'coral', 'corn', 'cornflower', 'cream', 'crimson', 'cyan', 'dandelion', 'denim', 'ecru', 'emerald', 'eggplant', 'falu-red', 'fern-green', 'firebrick', 'flax', 'forest-green', 'french-rose', 'fuchsia', 'gamboge', 'gold', 'goldenrod', 'green', 'grey', 'han-purple', 'harlequin', 'heliotrope', 'hollywood-cerise', 'indigo', 'ivory', 'jade', 'kelly-green', 'khaki', 'lavender', 'lawn-green', 'lemon', 'lemon-chiffon', 'lilac', 'lime', 'lime-green', 'linen', 'magenta', 'magnolia', 'malachite', 'maroon', 'mauve', 'midnight-blue', 'mint-green', 'misty-rose', 'moss-green', 'mustard', 'myrtle', 'navajo-white', 'navy-blue', 'ochre', 'office-green', 'olive', 'olivine', 'orange', 'orchid', 'papaya-whip', 'peach', 'pear', 'periwinkle', 'persimmon', 'pine-green', 'pink', 'platinum', 'plum', 'powder-blue', 'puce', 'prussian-blue', 'psychedelic-purple', 'pumpkin', 'purple', 'quartz-grey', 'raw-umber', 'razzmatazz', 'red', 'robin-egg-blue', 'rose', 'royal-blue', 'royal-purple', 'ruby', 'russet', 'rust', 'safety-orange', 'saffron', 'salmon', 'sandy-brown', 'sangria', 'sapphire', 'scarlet', 'school-bus-yellow', 'sea-green', 'seashell', 'sepia', 'shamrock-green', 'shocking-pink', 'silver', 'sky-blue', 'slate-grey', 'smalt', 'spring-bud', 'spring-green', 'steel-blue', 'tan', 'tangerine', 'taupe', 'teal', 'tenné-(tawny)', 'terra-cotta', 'thistle', 'titanium-white', 'tomato', 'turquoise', 'tyrian-purple', 'ultramarine', 'van-dyke-brown', 'vermilion', 'violet', 'viridian', 'wheat', 'white', 'wisteria', 'yellow', 'zucchini']

class Entity(BaseModel):
    """ Entity class: Represents a normalized entity (Synonym)."""
    label: str = Field(..., description="Label of the Entity.")
    identifier: str = Field("", description="Curie identifier of the Entity.")
    description: str = Field("", description="Formal description(definition) of the Entity.")
    entity_type: str = Field("", description="Type of the Entity.")
    color_code: str = Field("", description="Color coding for mapping back items.")
    taxa: str = Field("", description="Taxonomic label of the Entity.")
    taxa_ids: list = Field([], description="Taxonomic identifiers of the Entity.")

class SynonymListContext(BaseModel):
    text: str = Field(..., description="Body of text containing entity.")
    entity: str = Field(..., description="Entity identified in text.")
    synonyms: List[Entity] = Field(..., description="Entities linked to the target entity, to be re-ranked.")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for index, synonym in enumerate(self.synonyms):
            synonym.color_code = colors[index]

    def pretty_print_synonyms(self):
        string = "\n[\n"
        for synonym in self.synonyms:
            string += f'"label": "{synonym.label}",'
            string += f'"taxon": "{synonym.taxa}", ' if synonym.taxa else ""
            string += f'"color_code": "{synonym.color_code}", '
            string += f'"entity_type": "{synonym.entity_type}", '
            string += f'"description": "{synonym.description}"' if synonym.description else ""
            string += "\n]\n"
        return string

def preprocess_annotation_map(annotation_map):
    unique = {}
    for expanded_text, entries in annotation_map.items():
        for entry in entries:
            pmid = entry["pmid"]
            original_entity = entry["original_entity"]
            key = (str(pmid), original_entity)
            if key not in unique:
                unique[key] = {
                    "pmid": pmid,
                    "expanded_text": expanded_text,
                    "original_text": original_entity
                }
    # Order by pmid (as int if possible)
    def pmid_sort_key(x):
        try:
            return int(x["pmid"])
        except Exception:
            return x["pmid"]
    result = [
        {"id": i, **row} for i, row in enumerate(sorted(unique.values(), key=pmid_sort_key))
    ]
    return result

def create_body(
    annotation_list: list,
    pmid_abstracts: dict,
    prompt: str,
    threshold: int,
    expanded_annotations_dict: dict,
    bodies_outfile: str,
    color_map_outfile: str
):
    outbodies = []
    color_maps = []
    for row in annotation_list:
        idx = row["id"]
        pmid = row["pmid"]
        entity = row["original_text"]
        expanded_text = row["expanded_text"]
        key_entity = (pmid, entity)
        if expanded_text not in expanded_annotations_dict:
            continue
        # Get candidate entities for this expanded_text from expanded_annotations_dict
        candidates_dict = expanded_annotations_dict.get(expanded_text, {})
        if not isinstance(candidates_dict, dict):
            print(f"[DEBUG] Unexpected candidates_dict type for expanded_text: {expanded_text}\nValue: {candidates_dict}\nType: {type(candidates_dict)}")
            continue
        synonyms = [
            Entity(**{
                "label": value.get("name", identifier),
                "identifier": identifier,
                "description": value.get("description", ""),
                "entity_type": value.get("category", ""),
                "taxa": ", ".join([value.get("taxa", "")])
            })
            for identifier, value in candidates_dict.items()
            if identifier != "annotated_text" and (
                (value.get("name_res_rank", -1) > -1 and value.get("name_res_rank", -1) <= threshold) or
                (value.get("sapbert_rank", -1) > -1 and value.get("sapbert_rank", -1) <= threshold)
            )
        ]
        context = SynonymListContext(
            text=pmid_abstracts[pmid],
            entity=entity,
            synonyms=synonyms
        )
        prompt_message = prompt.format(**{
            'text': context.text,
            'query_term': context.entity,
            'synonyms': context.pretty_print_synonyms()
        })
        outbodies.append({"index": idx, "prompt": prompt_message})
        labels = {syn.color_code: syn.label for syn in context.synonyms}
        taxons = {syn.color_code: syn.taxa for syn in context.synonyms}
        identifiers = {syn.color_code: syn.identifier for syn in context.synonyms}
        color_maps.append({
            "index": idx,
            "entity": entity,
            "labels": labels,
            "taxons": taxons,
            "identifiers": identifiers
        })
    # Write output files
    with open(bodies_outfile, "w") as outf:
        for body in outbodies:
            outf.write(json.dumps(body) + "\n")
    with open(color_map_outfile, "w") as cmf:
        for color_map in color_maps:
            cmf.write(json.dumps(color_map) + "\n")

def load_expanded_annotations_jsonl(path):
    """
    Reads expanded_annotations.jsonl and returns a dict:
    { text: { identifier: stuff, identifier: stuff } }
    Ensures all values are dicts. Logs and skips any non-dict values.
    """
    result = {}
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if "error" in obj:
                continue
            text = obj["annotated_text"]
            entry = {}
            for k, v in obj.items():
                if k == "annotated_text":
                    continue
                if isinstance(v, dict):
                    entry[k] = v
                else:
                    print(f"[WARN] Skipping identifier '{k}' for text '{text}' in expanded_annotations.jsonl because value is not a dict: {v}")
            result[text] = entry
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='run_1', help='Run directory name (default: run_1)')
    parser.add_argument('--threshold', type=int, required=True, help='Threshold value (e.g., 5, 10, 20)')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)
    parsed_inputs_dir = os.path.join(run_dir, 'parsed_inputs')
    os.makedirs(parsed_inputs_dir, exist_ok=True)
    annotations_file_name = os.path.join('input_data', 'expanded_annotations.jsonl')
    abstracts_file = os.path.join('input_data', 'corpus_pubtator_normalized_8-4-2025.jsonl')
    prompt_template_file = os.path.join('input_data', 'prompt_template')
    with open(abstracts_file) as f:
        pmid_abstracts = {json.loads(line)['pmid']: json.loads(line)['text'] for line in f if line.strip()}
    with open(prompt_template_file) as f:
        prompt = f.read().strip()
    bodies_outfile = os.path.join(parsed_inputs_dir, f"bodies_{args.threshold}.jsonl")
    color_map_outfile = os.path.join(parsed_inputs_dir, f"bodies_{args.threshold}_colormap.jsonl")
    # Load entity map
    entity_map_file = os.path.join('input_data', 'expanded_annotations_entity_map.json')
    with open(entity_map_file) as f:
        entity_map = json.load(f)
    preprocessed_annotations = preprocess_annotation_map(entity_map)
    # Write preprocessed_annotations to annotation_list.jsonl
    annotation_list_outfile = os.path.join(parsed_inputs_dir, 'annotation_list.jsonl')
    with open(annotation_list_outfile, 'w') as out_f:
        for item in preprocessed_annotations:
            out_f.write(json.dumps(item) + '\n')
    # Load expanded annotations
    expanded_annotations_file = os.path.join('input_data', 'expanded_annotations.jsonl')
    expanded_annotations_dict = load_expanded_annotations_jsonl(expanded_annotations_file)
    # Preprocess annotation map
    # Create body and color map files
    create_body(preprocessed_annotations, pmid_abstracts, prompt, args.threshold, expanded_annotations_dict, bodies_outfile, color_map_outfile)

if __name__ == "__main__":
    main()
