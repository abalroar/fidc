#!/usr/bin/env python3
"""Extrai, de forma reproduzível, consultas agregadas do embed público de FIDCs.

Uso:
    python extrair_powerbi_publico.py --out ./dados_extraidos

Aviso: este fluxo usa a interface interna de um relatório Power BI "Publish to web".
Ela não é uma API contratual da ANBIMA/Microsoft e pode mudar sem aviso.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


EMBED_URL = (
    "https://app.powerbi.com/view?"
    "r=eyJrIjoiM2M2NzVmOWItMzI0Yi00MTE1LWI5ZmYtZTM0ZWM4ZDUwODNlIiwidCI6Ijk3OTM3M2VkLWQxMzAtNDU4NS1iNTY5LTNjM2NlNjE0MTIyNyJ9"
)
RESOURCE_KEY = "3c675f9b-324b-4115-b9ff-e34ec8d5083e"
DEFAULT_API = "https://wabi-brazil-south-d-primary-api.analysis.windows.net"

SELECTED_VISUALS = {
    "pl_evolucao": "2959d6cf76e7aa199896",
    "contas_investidor_evolucao": "c2bbec47d1121163918f",
    "responsabilidade_limitada": "dd0624d736c04659c6e2",
    "foco_atuacao": "5471ed10513e82edb1cb",
    "ofertas_por_subscritor": "cd3071205d0ac053e309",
    "gestores_evolucao": "970ef58c71b76453ea88",
    "administradores_evolucao": "e0951c0fd958a8f8f045",
    "card_pl": "83865a9cb1817a672e29",
    "card_classes": "9a530226d057b521a539",
    "card_subclasses": "6283af3b1da6de136895",
    "card_contas": "cd41c720516f663c37d9",
    "card_classes_abertas": "d8e4f74c19c30a39d5a0",
    "card_classes_fechadas": "aa58b6858ce4f0b088e2",
    "card_gestores": "326aef2d59a134c8dd01",
    "card_administradores": "da23b456b84c3e2e6c92",
    "card_ofertas": "5f412b6c5d1000143657",
}


def request_headers(content_type: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "ActivityId": str(uuid.uuid4()),
        "RequestId": str(uuid.uuid4()),
        "X-PowerBI-ResourceKey": RESOURCE_KEY,
    }
    if content_type:
        headers["Content-Type"] = "application/json"
    return headers


def http_get_text(url: str, headers: dict[str, str] | None = None) -> str:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=90) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8")


def http_json(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(url, data=data, headers=headers or {}, method=method)
    with urlopen(request, timeout=90) as response:
        payload = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            payload = gzip.decompress(payload)
        return json.loads(payload.decode("utf-8"))


def resolve_api() -> str:
    html = http_get_text(EMBED_URL)
    match = re.search(r"var resolvedClusterUri = '([^']+)'", html)
    if not match:
        return DEFAULT_API
    return match.group(1).replace("-redirect.analysis.windows.net", "-api.analysis.windows.net").rstrip("/")


def fetch_metadata(api: str) -> tuple[dict[str, Any], dict[str, Any]]:
    models_url = f"{api}/public/reports/{RESOURCE_KEY}/modelsAndExploration?preferReadOnlySession=true"
    schema_url = f"{api}/public/reports/conceptualschema"
    models = http_json(models_url, headers=request_headers())
    schema = http_json(schema_url, headers=request_headers())
    return models, schema


def bit_set(mask: int, index: int) -> bool:
    return bool(mask & (1 << index))


def decode_value(value: Any, dictionary_name: str | None, dictionaries: dict[str, list[Any]]) -> Any:
    if dictionary_name and isinstance(value, int):
        values = dictionaries.get(dictionary_name, [])
        if 0 <= value < len(values):
            return values[value]
    if isinstance(value, dict):
        if "V" in value:
            return value["V"]
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def decode_rows(result_data: dict[str, Any]) -> pd.DataFrame:
    descriptor = result_data.get("descriptor", {})
    token_to_name = {
        item.get("Value"): item.get("Name", item.get("Value"))
        for item in descriptor.get("Select", [])
        if item.get("Value")
    }
    output: list[dict[str, Any]] = []

    def decode_encoded(
        encoded: dict[str, Any],
        schema: list[dict[str, Any]],
        previous: list[Any],
        dictionaries: dict[str, list[Any]],
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        if "S" in encoded:
            schema = encoded["S"]
            previous = [None] * len(schema)
        repeat_mask = int(encoded.get("R", 0))
        null_mask = int(encoded.get("Ø", 0))
        compressed = list(encoded.get("C", []))
        cursor = 0
        row: list[Any] = []
        for idx, spec in enumerate(schema):
            token = spec.get("N")
            if token in encoded:
                value = decode_value(encoded[token], spec.get("DN"), dictionaries)
            elif bit_set(repeat_mask, idx):
                value = previous[idx]
            elif bit_set(null_mask, idx):
                value = None
            else:
                value = compressed[cursor] if cursor < len(compressed) else None
                cursor += 1
                value = decode_value(value, spec.get("DN"), dictionaries)
            row.append(value)
        return row, schema

    def as_record(schema: list[dict[str, Any]], row: list[Any]) -> dict[str, Any]:
        return {
            token_to_name.get(spec.get("N"), spec.get("N", f"col_{idx}")): value
            for idx, (spec, value) in enumerate(zip(schema, row))
        }

    for dataset in result_data.get("dsr", {}).get("DS", []):
        dictionaries = dataset.get("ValueDicts", {})
        secondary_members: list[dict[str, Any]] = []
        for secondary_partition in dataset.get("SH", []):
            for grouping_name, encoded_rows in secondary_partition.items():
                if not grouping_name.startswith("DM") or not isinstance(encoded_rows, list):
                    continue
                secondary_schema: list[dict[str, Any]] = []
                secondary_previous: list[Any] = []
                for encoded in encoded_rows:
                    row, secondary_schema = decode_encoded(
                        encoded, secondary_schema, secondary_previous, dictionaries
                    )
                    secondary_previous = row
                    secondary_members.append(as_record(secondary_schema, row))

        for partition in dataset.get("PH", []):
            for grouping_name, encoded_rows in partition.items():
                if not grouping_name.startswith("DM") or not isinstance(encoded_rows, list):
                    continue
                schema: list[dict[str, Any]] = []
                previous: list[Any] = []
                nested_schema: list[dict[str, Any]] = []
                nested_previous: list[Any] = []
                for encoded in encoded_rows:
                    row, schema = decode_encoded(encoded, schema, previous, dictionaries)
                    previous = row
                    primary_record = as_record(schema, row)
                    nested = encoded.get("X")
                    if not isinstance(nested, list):
                        output.append(primary_record)
                        continue
                    member_index = 0
                    for nested_encoded in nested:
                        if "I" in nested_encoded:
                            member_index = int(nested_encoded["I"])
                        nested_row, nested_schema = decode_encoded(
                            nested_encoded, nested_schema, nested_previous, dictionaries
                        )
                        nested_previous = nested_row
                        record = dict(primary_record)
                        if member_index < len(secondary_members):
                            record.update(secondary_members[member_index])
                        record.update(as_record(nested_schema, nested_row))
                        output.append(record)
                        member_index += 1
    return pd.DataFrame(output)


def post_visual_query(
    api: str,
    model_id: int,
    visual: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    body = {
        "version": "1.0.0",
        "queries": [{"Query": json.loads(visual["query"])}],
        "cancelQueries": [],
        "modelId": model_id,
    }
    url = f"{api}/public/reports/querydata?synchronous=true"
    payload = http_json(url, method="POST", headers=request_headers(True), body=body)
    frames = []
    for result in payload.get("results", []):
        data = result.get("result", {}).get("data")
        if data:
            frames.append(decode_rows(data))
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), payload


def visual_catalog(models: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = []
    for section in models["exploration"].get("sections", []):
        for visual in section.get("visualContainers", []):
            config = json.loads(visual["config"])
            single = config.get("singleVisual", {})
            query = json.loads(visual["query"]) if visual.get("query") else None
            select_names = []
            if query:
                command = query.get("Commands", [{}])[0].get("SemanticQueryDataShapeCommand", {})
                select_names = [item.get("Name") for item in command.get("Query", {}).get("Select", [])]
            catalog.append(
                {
                    "page": section.get("displayName"),
                    "visual_name": config.get("name"),
                    "visual_type": single.get("visualType"),
                    "query_hash": visual.get("queryHash"),
                    "fields": " | ".join(filter(None, select_names)),
                    "has_query": bool(query),
                }
            )
    return catalog


def schema_catalog(schema: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for item in schema.get("schemas", []):
        for entity in item.get("schema", {}).get("Entities", []):
            for prop in entity.get("Properties", []):
                rows.append(
                    {
                        "entity": entity.get("Name"),
                        "field": prop.get("Name"),
                        "kind": "measure" if "Measure" in prop else "column",
                        "type": prop.get("Type", {}).get("UnderlyingType") if isinstance(prop.get("Type"), dict) else prop.get("Type"),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    api = resolve_api()
    models, schema = fetch_metadata(api)
    model_id = int(models["models"][0]["id"])
    all_visuals = {
        json.loads(v["config"]).get("name"): v
        for section in models["exploration"].get("sections", [])
        for v in section.get("visualContainers", [])
    }

    visual_rows = visual_catalog(models)
    schema_frame = schema_catalog(schema)
    pd.DataFrame(visual_rows).to_csv(args.out / "catalogo_visuais.csv", index=False)
    schema_frame.to_csv(args.out / "catalogo_campos.csv", index=False)
    (args.out / "catalogos.json").write_text(
        json.dumps(
            {
                "visuais": visual_rows,
                "campos": json.loads(schema_frame.to_json(orient="records", force_ascii=False)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    status_rows = []
    data_bundle: dict[str, list[dict[str, Any]]] = {}
    for output_name, visual_name in SELECTED_VISUALS.items():
        visual = all_visuals.get(visual_name)
        if not visual or not visual.get("query"):
            status_rows.append({"dataset": output_name, "status": "visual/query não encontrado"})
            continue
        frame, payload = post_visual_query(api, model_id, visual)
        frame.to_csv(args.out / f"{output_name}.csv", index=False)
        data_bundle[output_name] = json.loads(frame.to_json(orient="records", force_ascii=False))
        status_rows.append({"dataset": output_name, "status": "ok", "rows": len(frame), "columns": len(frame.columns)})

    metadata = {
        "embed_url": EMBED_URL,
        "resource_key": RESOURCE_KEY,
        "api_cluster": api,
        "model_id": model_id,
        "report_id": models.get("exploration", {}).get("reportId"),
        "model_last_refresh_time": models["models"][0].get("LastRefreshTime"),
        "report_last_updated_time": models.get("exploration", {}).get("report", {}).get("lastUpdatedTime"),
    }
    (args.out / "metadados_tecnicos.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "dados_extraidos.json").write_text(
        json.dumps(data_bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(status_rows).to_csv(args.out / "status_extracao.csv", index=False)
    print(json.dumps({"metadata": metadata, "status": status_rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
