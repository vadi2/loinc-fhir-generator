#!/usr/bin/env python3
"""Build a FHIR R4 LOINC CodeSystem (terms + LP parts + LL answer lists + LA answers) from a LOINC release."""
import argparse
import csv
import json
import re
import sys
import zipfile
from collections import defaultdict
from io import TextIOWrapper

csv.field_size_limit(sys.maxsize)

LOINC = "http://loinc.org"
COPYRIGHT = (
    "This material contains content from LOINC (http://loinc.org). LOINC is copyright "
    "© Regenstrief Institute, Inc. and the Logical Observation Identifiers Names and "
    "Codes (LOINC) Committee and is available at no cost under the license at "
    "http://loinc.org/license. LOINC® is a registered United States trademark of "
    "Regenstrief Institute, Inc."
)


class Release:
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path) if zipfile.is_zipfile(path) else None
        self.root = path
        self.names = self.zip.namelist() if self.zip else None

    def open(self, rel):
        if self.zip:
            hits = [n for n in self.names if n.endswith(rel)]
            if not hits:
                raise SystemExit(f"{rel} not found in {self.root}")
            return TextIOWrapper(self.zip.open(min(hits, key=len)), encoding="utf-8-sig", newline="")
        return open(f"{self.root}/{rel}", encoding="utf-8-sig", newline="")

    def rows(self, rel):
        with self.open(rel) as f:
            yield from csv.DictReader(f)


def prop(code, kind, value):
    return {"code": code, kind: value}


def coding(code, display=None):
    c = {"system": LOINC, "code": code}
    if display:
        c["display"] = display
    return c


def build(release, version, previous=None):
    term_lists = defaultdict(list)
    for r in release.rows("AccessoryFiles/AnswerFile/LoincAnswerListLink.csv"):
        term_lists[r["LoincNumber"]].append(prop("answer-list", "valueCoding", coding(r["AnswerListId"], r["AnswerListName"])))

    concepts = []
    for r in release.rows("LoincTable/Loinc.csv"):
        code = r["LOINC_NUM"]
        c = {"code": code, "display": r["LONG_COMMON_NAME"]}
        if r["DisplayName"]:
            c["designation"] = [{"use": {"system": LOINC, "code": "DisplayName"}, "value": r["DisplayName"]}]
        props = [prop("STATUS", "valueString", r["STATUS"])]
        if r["STATUS"] == "DEPRECATED":
            props.append(prop("inactive", "valueBoolean", True))
        for k in ("SHORTNAME", "VersionFirstReleased", "VersionLastChanged", "EXTERNAL_COPYRIGHT_NOTICE"):
            if r[k]:
                props.append(prop(k, "valueString", r[k]))
        props.append(prop("CLASS", "valueString", r["CLASS"]))
        props.append(prop("CLASSTYPE", "valueString", r["CLASSTYPE"]))
        if r["ORDER_OBS"]:
            props.append(prop("ORDER_OBS", "valueString", r["ORDER_OBS"]))
        if r["EXAMPLE_UCUM_UNITS"]:
            props.append(prop("EXAMPLE_UCUM_UNITS", "valueString", r["EXAMPLE_UCUM_UNITS"]))
        props += term_lists.get(code, [])
        c["property"] = props
        concepts.append(c)
    n_terms = len(concepts)

    n_parts = 0
    for r in release.rows("AccessoryFiles/PartFile/Part.csv"):
        c = {"code": r["PartNumber"], "display": r["PartDisplayName"] or r["PartName"]}
        if r["PartName"] and r["PartName"] != c["display"]:
            c["designation"] = [{"use": {"system": LOINC, "code": "PartName"}, "value": r["PartName"]}]
        props = [prop("STATUS", "valueString", r["Status"]), prop("PartTypeName", "valueString", r["PartTypeName"])]
        if r["Status"] in ("DEPRECATED", "INACTIVE"):
            props.append(prop("inactive", "valueBoolean", True))
        c["property"] = props
        concepts.append(c)
        n_parts += 1

    lists, answers = {}, {}
    for r in release.rows("AccessoryFiles/AnswerFile/AnswerList.csv"):
        ll = r["AnswerListId"]
        if ll not in lists:
            lists[ll] = {"code": ll, "display": r["AnswerListName"], "property": [prop("STATUS", "valueString", "ACTIVE")]}
            if r["AnswerListOID"]:
                lists[ll]["property"].append(prop("OID", "valueString", r["AnswerListOID"]))
        la = r["AnswerStringId"]
        if not la:
            continue
        lists[ll]["property"].append(prop("answer", "valueCoding", coding(la, r["DisplayText"])))
        if la not in answers:
            answers[la] = {"code": la, "display": r["DisplayText"], "property": [prop("STATUS", "valueString", "ACTIVE")]}
        answers[la]["property"].append(prop("answer-list", "valueCoding", coding(ll, r["AnswerListName"])))
    concepts += lists.values()
    concepts += answers.values()

    seen = set()
    for c in concepts:
        if c["code"] in seen:
            raise SystemExit(f"duplicate code {c['code']}")
        seen.add(c["code"])

    # LOINC codes are never reused, but a release drops retired parts from Part.csv and
    # answers no longer in any list from AnswerList.csv; keep them as inactive concepts.
    carried = 0
    if previous:
        snapshot = {r["PartNumber"]: r["ValueCurrent"]
                    for r in release.rows("AccessoryFiles/ChangeSnapshot/PartChangeSnapshot.csv")
                    if r["PROPERTY"] == "STATUS"}
        for old in previous["concept"]:
            if old["code"] in seen:
                continue
            c = {"code": old["code"], "display": old["display"]}
            if old.get("designation"):
                c["designation"] = old["designation"]
            keep = [p for p in old.get("property", []) if p["code"] in ("PartTypeName", "SHORTNAME", "CLASS", "CLASSTYPE", "VersionFirstReleased")]
            c["property"] = [prop("STATUS", "valueString", snapshot.get(old["code"], "INACTIVE")), prop("inactive", "valueBoolean", True)] + keep
            concepts.append(c)
            seen.add(c["code"])
            carried += 1

    props = [
        ("STATUS", "string", "Status of the concept: ACTIVE, TRIAL, DISCOURAGED, DEPRECATED (terms); ACTIVE, INACTIVE, DEPRECATED (parts)"),
        ("inactive", "boolean", "True if the concept is deprecated or inactive, or was dropped from this release"),
        ("SHORTNAME", "string", "Short name of the term"),
        ("VersionFirstReleased", "string", "LOINC version in which the term was first released"),
        ("VersionLastChanged", "string", "LOINC version in which the term was last changed"),
        ("EXTERNAL_COPYRIGHT_NOTICE", "string", "Third-party copyright notice for the term"),
        ("CLASS", "string", "Arbitrary classification of the term"),
        ("CLASSTYPE", "string", "1=Laboratory, 2=Clinical, 3=Claims attachments, 4=Surveys"),
        ("ORDER_OBS", "string", "Order, Observation, Both or Subset"),
        ("EXAMPLE_UCUM_UNITS", "string", "Example UCUM units"),
        ("answer-list", "Coding", "Answer list (LL) linked to a term, or containing an answer"),
        ("answer", "Coding", "Answer (LA) contained in an answer list"),
        ("PartTypeName", "string", "Type of a LOINC part (LP)"),
        ("OID", "string", "OID of an answer list"),
    ]
    cs = {
        "resourceType": "CodeSystem",
        "id": "loinc",
        "url": LOINC,
        "identifier": [{"system": "urn:ietf:rfc:3986", "value": "urn:oid:2.16.840.1.113883.6.1"}],
        "version": version,
        "name": "LOINC",
        "title": f"LOINC {version} terms, parts, answer lists and answers",
        "status": "active",
        "experimental": False,
        "publisher": "Regenstrief Institute, Inc.",
        "description": f"LOINC {version} generated from the official release: all LOINC terms, LP parts, LL answer lists and LA answers. Parts and answers dropped from the release files since the previous version are kept as inactive concepts.",
        "copyright": COPYRIGHT,
        "caseSensitive": False,
        "valueSet": "http://loinc.org/vs",
        "compositional": False,
        "versionNeeded": False,
        "content": "complete",
        "count": len(concepts),
        "property": [{"code": c, "uri": "http://hl7.org/fhir/concept-properties#inactive" if c == "inactive" else f"http://loinc.org/property/{c}", "description": d, "type": t} for c, t, d in props],
        "concept": concepts,
    }
    stats = {"terms": n_terms, "parts": n_parts, "answer lists": len(lists), "answers": len(answers), "carried forward": carried, "total": len(concepts)}
    return cs, stats


def infer_version(path):
    m = re.search(r"(\d+\.\d+)", path.rstrip("/").rsplit("/", 1)[-1])
    if not m:
        raise SystemExit(f"cannot infer the LOINC version from {path}; pass --version")
    return m.group(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("release", help="Loinc_X.YY.zip or an extracted release folder")
    ap.add_argument("-o", "--output", help="output file (default CodeSystem-loinc-<version>-parts-answers.json)")
    ap.add_argument("--version", help="LOINC version (default: read from the zip name)")
    ap.add_argument("--previous", help="previous release zip/folder, or a CodeSystem generated from it; "
                    "codes it has that this release dropped are kept as inactive")
    a = ap.parse_args()
    version = a.version or infer_version(a.release)
    previous = None
    if a.previous and a.previous.endswith(".json"):
        previous = json.load(open(a.previous, encoding="utf-8"))
    elif a.previous:
        previous = build(Release(a.previous), infer_version(a.previous))[0]
    cs, stats = build(Release(a.release), version, previous)
    out = a.output or f"CodeSystem-loinc-{version}-parts-answers.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cs, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(out, json.dumps(stats))


if __name__ == "__main__":
    main()
