# LOINC FHIR CodeSystem generator

[Русская версия](README.ru.md)

Turns an official LOINC release into a single, complete FHIR R4 `CodeSystem` for `http://loinc.org`. Besides the LOINC terms it includes every LP part, LL answer list and LA answer, so FHIR validators and IG builds can resolve all of them offline.

This repository only has the generator. It contains no LOINC content: you download the release yourself, for free, from loinc.org.

## Requirements

- Python 3.8 or newer. No packages to install.
- A free loinc.org account, to download the release.

## Generating the CodeSystem

1. Sign in at https://loinc.org/downloads/ and download **LOINC Complete** (`Loinc_<version>.zip`, about 90 MB). Check its MD5 checksum against the one on that page.
2. Download the previous release, `Loinc_<previous version>.zip`, from https://loinc.org/archive (see [why](#why-the-previous-release)).
3. Put both zips next to `generate.py` and run:

   ```bash
   python3 generate.py Loinc_2.83.zip --previous Loinc_2.82.zip
   ```

   This writes `CodeSystem-loinc-2.83-parts-answers.json` in about 10 seconds (around 160 MB), and prints how many codes of each kind it contains. The version is read from the zip file name; use `--version` if you renamed it, and `-o` to choose another output file. An extracted release folder works in place of a zip.

Instead of the previous zip, `--previous` also accepts a CodeSystem generated earlier with this script, so each release can build on the last one.

## Why the previous release

LOINC never deletes or reuses codes, but each release's files leave some out. In 2.83, 228 LP parts that were retired disappeared from `Part.csv`, and 2 LA answers that are no longer in any answer list disappeared from `AnswerList.csv`. Data already coded with them is still valid, so `--previous` keeps every code from the previous release that the new one dropped, marked `inactive`. Their `STATUS` comes from the release's `ChangeSnapshot/PartChangeSnapshot.csv`, or is `INACTIVE` when it isn't listed there.

## What's in the CodeSystem

| Codes | Source file | Display | Properties |
|---|---|---|---|
| Terms (e.g. `2160-0`) | `LoincTable/Loinc.csv` | `LONG_COMMON_NAME`; `DisplayName` as a designation | `STATUS`, `inactive` (deprecated), `SHORTNAME`, `VersionFirstReleased`, `VersionLastChanged`, `EXTERNAL_COPYRIGHT_NOTICE`, `CLASS`, `CLASSTYPE`, `ORDER_OBS`, `EXAMPLE_UCUM_UNITS`, the six part axes (`COMPONENT`, `PROPERTY`, `TIME_ASPCT`, `SYSTEM`, `SCALE_TYP`, `METHOD_TYP`) as LP codings from `LoincPartLink_Primary.csv`, `answer-list` from `LoincAnswerListLink.csv` |
| Parts (`LP…`) | `AccessoryFiles/PartFile/Part.csv` | `PartDisplayName`; `PartName` as a designation when different | `STATUS`, `PartTypeName`, `inactive` |
| Answer lists (`LL…`) | `AccessoryFiles/AnswerFile/AnswerList.csv` | `AnswerListName` | `STATUS`, `OID`, `answer` (LA codings) |
| Answers (`LA…`) | `AccessoryFiles/AnswerFile/AnswerList.csv` | `DisplayText` (from the first answer list it appears in) | `STATUS`, `answer-list` (LL codings) |

`inactive` is only present when true. The JSON is written on one line to keep it small.

For LOINC 2.83 the output has 112,405 terms, 75,165 LP parts, 5,009 LL answer lists and 22,363 LA answers.

Not included: the LP grouping codes that only exist in `ComponentHierarchyBySystem.csv` (the folders of LOINC's component hierarchy), LOINC Groups (`LG…`) and translations from `LinguisticVariants`.

## Licenses

The generator is under the [MIT License](LICENSE).

LOINC itself is copyright Regenstrief Institute, Inc. and the LOINC Committee, and is free to use under the [LOINC license](https://loinc.org/license). The generated CodeSystem contains LOINC content, so sharing it is subject to that license; the CodeSystem carries the required copyright notice.
