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

def load_abbreviation_map(abbrev_file):
    pmid_to_abbrev = {}
    with open(abbrev_file) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            pmid = row["pmid"]
            abbr_list = row["abbreviation_map"]  # Now always a list, not a string
            abbr_map = {entry["abbreviation"]: entry["definition"] for entry in abbr_list}
            pmid_to_abbrev[pmid] = abbr_map
    return pmid_to_abbrev

def create_body(
    annotations_file_name: str,
    pmid_abstracts: dict,
    prompt: str,
    threshold: int,
    abbrev_map: dict,
    bodies_outfile: str,
    color_map_outfile: str
):
    outbodies = []
    color_maps = []
    seen = set()  # Track (pmid, entity or definition) pairs
    with open(annotations_file_name) as stream:
        for idx, line in enumerate(stream):
            try:
                annotation_obj = json.loads(line)
            except Exception as e:
                print(line)
                raise e
            entity = annotation_obj['entity']
            pmid = annotation_obj['pmid']
            # Only process if pmid is in abbrev_map
            if pmid not in abbrev_map:
                continue
            # Check for abbreviation replacement
            definition = None
            if pmid in abbrev_map and entity in abbrev_map[pmid]:
                definition = abbrev_map[pmid][entity]
            # Only write if neither entity nor definition has been written for this pmid
            key_entity = (pmid, entity)
            key_def = (pmid, definition) if definition else None
            if key_entity in seen or (key_def and key_def in seen):
                continue
            # If writing the definition, mark both abbreviation and definition as seen
            if definition:
                seen.add(key_entity)
                seen.add(key_def)
                entity_to_use = definition
            else:
                seen.add(key_entity)
                entity_to_use = entity
            context = SynonymListContext(
                text=pmid_abstracts[pmid],
                entity=entity_to_use,
                synonyms=[
                    Entity(**{
                        "label": value["name"],
                        "identifier": identifier,
                        "description": value.get("description", ""),
                        "entity_type": value.get("category", ""),
                        "taxa": ", ".join([value.get("taxa", "")])
                    }) for identifier, value in annotation_obj['annotations'].items()
                    if ((value["name_res_rank"]>-1 and value["name_res_rank"] <= threshold) or (value["sapbert_rank"] >-1 and value["sapbert_rank"] <= threshold))
                ]
            )
            prompt_message = prompt.format(**{
                'text': context.text,
                'query_term': context.entity,
                'synonyms': context.pretty_print_synonyms()
            })
            outbodies.append({"index": idx, "prompt": prompt_message})
            labels = {syn.color_code: syn.label for syn in context.synonyms}
            taxons = {syn.color_code: syn.taxa for syn in context.synonyms}
            color_maps.append({
                "index": idx,
                "entity": entity_to_use,
                "labels": labels,
                "taxons": taxons
            })
    # Write output files
    with open(bodies_outfile, "w") as outf:
        for body in outbodies:
            outf.write(json.dumps(body) + "\n")
    with open(color_map_outfile, "w") as cmf:
        for color_map in color_maps:
            cmf.write(json.dumps(color_map) + "\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='run_1', help='Run directory name (default: run_1)')
    parser.add_argument('--threshold', type=int, required=True, help='Threshold value (e.g., 5, 10, 20)')
    args = parser.parse_args()
    run_dir = os.path.join('data', args.run)
    parsed_inputs_dir = os.path.join(run_dir, 'parsed_inputs')
    os.makedirs(parsed_inputs_dir, exist_ok=True)
    annotations_file_name = os.path.join('input_data', 'annotations-7-30-25.jsonl')
    abstracts_file = os.path.join('input_data', 'corpus_pubtator_normalized_8-4-2025.jsonl')
    prompt_template_file = os.path.join('input_data', 'prompt_template')
    abbrev_file = os.path.join('input_data', 'abbreviation_llm_results.jsonl')
    with open(abstracts_file) as f:
        pmid_abstracts = {json.loads(line)['pmid']: json.loads(line)['text'] for line in f if line.strip()}
    with open(prompt_template_file) as f:
        prompt = f.read().strip()
    abbrev_map = load_abbreviation_map(abbrev_file)
    bodies_outfile = os.path.join(parsed_inputs_dir, f"bodies_{args.threshold}.jsonl")
    color_map_outfile = os.path.join(parsed_inputs_dir, f"bodies_{args.threshold}_colormap.jsonl")
    create_body(annotations_file_name, pmid_abstracts, prompt, args.threshold, abbrev_map, bodies_outfile, color_map_outfile)

if __name__ == "__main__":
    main()
