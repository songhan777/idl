"""Offline structural and example checks for this repository's OpenAPI profile.

This is not an API implementation, HTTP integration test, or compatibility diff.
Only document-local JSON Pointer references are accepted, before any validators run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterator
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
OPERATIONS = {
    ("/v1/projects", "get"): ("listProjects", "200", [], []),
    ("/v1/projects", "post"): ("createProject", "201", ["idempotency-key"], ["etag", "location"]),
    ("/v1/projects/{projectId}", "get"): ("getProject", "200", [], ["etag"]),
    ("/v1/projects/{projectId}", "patch"): ("updateProject", "200", ["if-match"], ["etag"]),
    ("/v1/projects/{projectId}", "delete"): ("deleteProject", "204", ["if-match"], []),
}


class ContractError(ValueError):
    """The contract violates the repository's declared profile."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys rather than silently selecting the last value."""


def unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ContractError(f"Duplicate YAML key {key!r}, line {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_contract(path: Path) -> dict:
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ContractError("OpenAPI document must be an object")
    return document


def escape(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def walk(value: Any, pointer: str = "#", mode: str = "openapi") -> Iterator[tuple[str, Any]]:
    """Walk specification objects, never example/default/const instance data.

    Schema property maps hold arbitrary business names, so their map itself must
    not be interpreted as a schema (a property may literally be named '$ref').
    """
    if mode in {"schema-map", "example-map"}:
        if isinstance(value, dict):
            child_mode = "schema" if mode == "schema-map" else "example"
            for key, child in value.items():
                yield from walk(child, f"{pointer}/{escape(key)}", child_mode)
        return
    if mode == "schema-array":
        if isinstance(value, list):
            for index, child in enumerate(value):
                yield from walk(child, f"{pointer}/{index}", "schema")
        return
    yield pointer, value
    if mode == "example":
        return  # Example Object $ref is structural, but its value is opaque data.
    if isinstance(value, dict):
        for key, child in value.items():
            if mode == "schema":
                if key in {"properties", "patternProperties", "$defs", "dependentSchemas"}:
                    child_mode = "schema-map"
                elif key in {"allOf", "anyOf", "oneOf", "prefixItems"}:
                    child_mode = "schema-array"
                elif key in {"items", "contains", "additionalProperties", "unevaluatedProperties",
                             "unevaluatedItems", "propertyNames", "if", "then", "else", "not", "contentSchema"}:
                    child_mode = "schema"
                else:
                    continue  # Includes examples, default, enum, const and annotations.
            else:
                if key == "example":
                    continue
                if key == "examples":
                    child_mode = "example-map"
                elif key == "schema":
                    child_mode = "schema"
                elif pointer == "#/components" and key == "schemas":
                    child_mode = "schema-map"
                else:
                    child_mode = "openapi"
            yield from walk(child, f"{pointer}/{escape(key)}", child_mode)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{pointer}/{index}", mode)


def resolve(document: dict, reference: str) -> Any:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise ContractError(f"Only local JSON Pointer references are allowed: {reference!r}")
    current: Any = document
    try:
        for token in unquote(reference[2:]).split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            current = current[int(token)] if isinstance(current, list) else current[token]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ContractError(f"Unresolved reference: {reference}") from exc
    return current


def dereference(document: dict, value: dict) -> dict:
    seen: set[str] = set()
    while isinstance(value, dict) and "$ref" in value:
        reference = value["$ref"]
        if reference in seen:
            raise ContractError(f"Cyclic non-schema reference: {reference}")
        seen.add(reference)
        value = resolve(document, reference)
    return value


def schema_errors(document: dict, pointer: str, value: Any) -> list[str]:
    resolve(document, pointer)
    # Keeping the complete document as the root preserves #/components references.
    root = dict(document)
    root["$ref"] = pointer
    validator = Draft202012Validator(root, format_checker=FormatChecker())
    return [f"{error.json_path}: {error.message}" for error in validator.iter_errors(value)]


def examples(document: dict, media: dict) -> Iterator[Any]:
    if "example" in media:
        yield media["example"]
    if isinstance(media.get("examples"), dict):
        for example in media["examples"].values():
            example = dereference(document, example)
            if "externalValue" in example:
                raise ContractError("externalValue examples are unsupported; commit local inline values")
            if "value" not in example:
                raise ContractError("An Example Object must contain value in this repository")
            yield example["value"]


def check_profile(document: dict) -> int:
    if document.get("openapi") != "3.1.0":
        raise ContractError("Repository baseline requires openapi: 3.1.0")
    if document.get("jsonSchemaDialect") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractError("Repository baseline requires JSON Schema 2020-12")
    for pointer, value in walk(document):
        if isinstance(value, dict) and "$ref" in value:
            resolve(document, value["$ref"])
        if isinstance(value, dict) and ("$dynamicRef" in value or "$id" in value):
            raise ContractError(f"$id/$dynamicRef require an extended resolver profile: {pointer}")

    # All user references were checked first, so this validation cannot retrieve them.
    validate(document)
    identifiers: set[str] = set()
    found_operations: set[tuple[str, str]] = set()
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in METHODS:
                continue
            identifier = operation.get("operationId")
            if not identifier or identifier in identifiers:
                raise ContractError(f"operationId must be present and unique: {path} {method}")
            identifiers.add(identifier)
            key = (path, method)
            if key not in OPERATIONS:
                raise ContractError(f"Operation is outside the current five-operation profile: {key}")
            expected_id, success_status, request_headers, success_headers = OPERATIONS[key]
            found_operations.add(key)
            if identifier != expected_id or success_status not in operation["responses"]:
                raise ContractError(f"Expected operationId/success response missing: {expected_id}")
            parameters = [dereference(document, item) for item in
                          path_item.get("parameters", []) + operation.get("parameters", [])]
            header_parameters = {item["name"].lower(): item for item in parameters if item.get("in") == "header"}
            for header_name in request_headers:
                if header_parameters.get(header_name, {}).get("required") is not True:
                    raise ContractError(f"Required request header missing: {identifier} {header_name}")
            expected_scope = "projects:read" if method == "get" else "projects:write"
            if operation.get("security") != [{"oauth2": [expected_scope]}]:
                raise ContractError(f"Explicit operation security required: {identifier}")
            for status, response in operation["responses"].items():
                if not isinstance(status, str) or not status.isdigit():
                    raise ContractError(f"Use quoted explicit HTTP status codes: {identifier}")
                response = dereference(document, response)
                headers = {key.lower(): value for key, value in response.get("headers", {}).items()}
                required_headers = ["cache-control", "x-request-id"]
                if status == success_status:
                    required_headers += success_headers
                if status == "401":
                    required_headers += ["www-authenticate"]
                if status in {"429", "503"}:
                    required_headers += ["retry-after"]
                for required_header in required_headers:
                    header = headers.get(required_header)
                    if not header or dereference(document, header).get("required") is not True:
                        raise ContractError(f"Required response header missing: {identifier} {status} {required_header}")
                if status == "204" and "content" in response:
                    raise ContractError(f"204 must not declare content: {identifier}")
                if int(status) < 400:
                    continue
                content = response.get("content", {})
                if set(content) != {"application/problem+json"}:
                    raise ContractError(f"Errors require application/problem+json: {identifier} {status}")
                media = content["application/problem+json"]
                if media.get("schema", {}).get("$ref") != "#/components/schemas/Problem":
                    raise ContractError(f"Errors must use the shared Problem schema: {identifier} {status}")
                values = list(examples(document, media))
                if not values or any(value.get("status") != int(status) for value in values):
                    raise ContractError(f"Error example HTTP status mismatch: {identifier} {status}")
    if found_operations != set(OPERATIONS):
        raise ContractError(f"Required operations missing: {set(OPERATIONS) - found_operations}")
    for name in ("CreateProject", "UpdateProject"):
        schema = document["components"]["schemas"][name]
        if schema.get("additionalProperties") is not False:
            raise ContractError(f"Requests must reject unknown fields: {name}")
    for name in ("Project", "ProjectPage", "Problem", "ValidationError"):
        schema = document["components"]["schemas"][name]
        if schema.get("additionalProperties", True) is not True:
            raise ContractError(f"Responses must tolerate additive fields: {name}")
    return len(identifiers)


def verify(document: dict, fixtures: list[dict]) -> dict[str, int]:
    operation_count = check_profile(document)
    example_count = 0
    for pointer, value in walk(document):
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("schema"), dict):
            for sample in examples(document, value):
                errors = schema_errors(document, f"{pointer}/schema", sample)
                if errors:
                    raise ContractError(f"Invalid example at {pointer}: {'; '.join(errors)}")
                example_count += 1
        # JSON Schema examples is an array, unlike OpenAPI Example Object maps.
        if isinstance(value.get("examples"), list):
            for sample in value["examples"]:
                errors = schema_errors(document, pointer, sample)
                if errors:
                    raise ContractError(f"Invalid schema example at {pointer}: {'; '.join(errors)}")
                example_count += 1
    names: set[str] = set()
    for fixture in fixtures:
        if fixture["name"] in names or not isinstance(fixture["valid"], bool):
            raise ContractError("Fixture names must be unique and valid must be boolean")
        names.add(fixture["name"])
        errors = schema_errors(document, fixture["schema"], fixture["value"])
        if bool(errors) == fixture["valid"]:
            raise ContractError(f"Unexpected fixture result {fixture['name']}: {errors}")
    return {"operations": operation_count, "examples": example_count, "fixtures": len(fixtures)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=ROOT / "contracts/openapi.yaml")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "contracts/fixtures.json")
    args = parser.parse_args()
    try:
        report = verify(load_contract(args.contract), json.loads(args.fixtures.read_text(encoding="utf-8")))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: " + ", ".join(f"{count} {name}" for name, count in report.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
