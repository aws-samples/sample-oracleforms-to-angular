"""IngestForms — parse the frmf2xml Forms XML into a structured JSON model.

Input event : { "run_id": "...", "forms_xml_key": "input/forms-xml/SAMPLE_SCREEN.xml" }
Output      : { "forms_structure_key": "pipeline/{run_id}/forms_structure.json",
                "block_count": N, "trigger_count": N }

Extracts blocks, items (with data types / prompts / list values), triggers
(with their PL/SQL), master-detail relations, LOVs/record groups and program
units — everything the analysis stage needs to reason about the UI + logic.
"""
import xml.etree.ElementTree as ET

from common.aws_helpers import s3_get_text, s3_put_json

DEFAULT_FORMS_KEY = "input/forms-xml/SAMPLE_SCREEN.xml"


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _attrs(el) -> dict:
    return {k: v for k, v in el.attrib.items()}


def _parse_block(block_el) -> dict:
    items, triggers = [], []
    for child in block_el:
        tag = _strip_ns(child.tag)
        if tag == "Item":
            item = _attrs(child)
            values = [_attrs(le) for le in child
                      if _strip_ns(le.tag) == "ListElement"]
            # ListElement lives under a <List> wrapper; catch both shapes.
            for wrapper in child:
                if _strip_ns(wrapper.tag) == "List":
                    values += [_attrs(le) for le in wrapper
                               if _strip_ns(le.tag) == "ListElement"]
            if values:
                item["list_values"] = values
            items.append(item)
        elif tag == "Trigger":
            triggers.append(_attrs(child))
    return {
        "name": block_el.get("Name"),
        "query_data_source": block_el.get("QueryDataSource"),
        "dml_target": block_el.get("DMLDataTargetName"),
        "insert_allowed": block_el.get("InsertAllowed"),
        "update_allowed": block_el.get("UpdateAllowed"),
        "delete_allowed": block_el.get("DeleteAllowed"),
        "items": items,
        "triggers": triggers,
    }


def handler(event, _context):
    run_id = event["run_id"]
    forms_key = event.get("forms_xml_key", DEFAULT_FORMS_KEY)

    xml_text = s3_get_text(forms_key)
    root = ET.fromstring(xml_text)

    blocks, relations, lovs, record_groups, program_units = [], [], [], [], []
    form_module = {}

    for el in root.iter():
        tag = _strip_ns(el.tag)
        if tag == "FormModule":
            form_module = _attrs(el)
        elif tag == "Block":
            blocks.append(_parse_block(el))
        elif tag == "Relation":
            relations.append(_attrs(el))
        elif tag == "LOV":
            lovs.append(_attrs(el))
        elif tag == "RecordGroup":
            record_groups.append(_attrs(el))
        elif tag == "ProgramUnit":
            program_units.append(_attrs(el))

    trigger_count = sum(len(b["triggers"]) for b in blocks)
    structure = {
        "run_id": run_id,
        "source_key": forms_key,
        "form_module": form_module,
        "blocks": blocks,
        "relations": relations,
        "lovs": lovs,
        "record_groups": record_groups,
        "program_units": program_units,
        "summary": {
            "block_count": len(blocks),
            "item_count": sum(len(b["items"]) for b in blocks),
            "trigger_count": trigger_count,
            "relation_count": len(relations),
        },
    }

    out_key = f"pipeline/{run_id}/forms_structure.json"
    s3_put_json(out_key, structure)
    return {
        "forms_structure_key": out_key,
        "block_count": len(blocks),
        "trigger_count": trigger_count,
    }
