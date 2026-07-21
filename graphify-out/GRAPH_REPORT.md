# Graph Report - .  (2026-07-15)

## Corpus Check
- Corpus is ~11,342 words - fits in a single context window. You may not need a graph.

## Summary
- 63 nodes · 79 edges · 12 communities (9 shown, 3 thin omitted)
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_UI Shell & Machine Selection|UI Shell & Machine Selection]]
- [[_COMMUNITY_Profile-Driven Data Engine|Profile-Driven Data Engine]]
- [[_COMMUNITY_Excel Import & Mapping|Excel Import & Mapping]]
- [[_COMMUNITY_Docs Core Architecture|Docs: Core Architecture]]
- [[_COMMUNITY_Docs Machine Profile & CSV|Docs: Machine Profile & CSV]]
- [[_COMMUNITY_Docs UI & Duplicate Detection|Docs: UI & Duplicate Detection]]
- [[_COMMUNITY_Docs Excel Import Feature|Docs: Excel Import Feature]]
- [[_COMMUNITY_Build & Packaging|Build & Packaging]]
- [[_COMMUNITY_Profile Builder (CSV Sniffing)|Profile Builder (CSV Sniffing)]]
- [[_COMMUNITY_Sidecar Metadata Store|Sidecar Metadata Store]]
- [[_COMMUNITY_ExcelRow Data Model|ExcelRow Data Model]]
- [[_COMMUNITY_Workbook IO|Workbook I/O]]

## God Nodes (most connected - your core abstractions)
1. `Configurador de Parámetros de Planta` - 13 edges
2. `App (Main Window)` - 10 edges
3. `DataStore` - 10 edges
4. `Profile` - 9 edges
5. `ImportDialog` - 6 edges
6. `AddMachineDialog` - 5 edges
7. `Sidecar (metadata store)` - 4 edges
8. `profiles_dir` - 4 edges
9. `golden_roundtrip test` - 4 edges
10. `DuplicatesDialog` - 3 edges

## Surprising Connections (you probably didn't know these)
- `Profile` --references--> `Maquina 232 Profile JSON`  [EXTRACTED]
  src/profile.py → profiles/maquina_232.json
- `Sidecar (metadata store)` --semantically_similar_to--> `DataStore`  [INFERRED] [semantically similar]
  src/metadata.py → src/datastore.py
- `Byte-Perfect CSV Round-Trip` --conceptually_related_to--> `golden_roundtrip test`  [INFERRED]
  src/datastore.py → tests/test_engine.py
- `pyinstaller >=6.0` --conceptually_related_to--> `build.bat`  [INFERRED]
  requirements.txt → README.md
- `openpyxl >=3.1` --conceptually_related_to--> `excel_import.py`  [INFERRED]
  requirements.txt → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Profile-Driven Data Load/Save Pipeline** — src_profile_profile, src_datastore_datastore, src_profile_campo [INFERRED 0.95]
- **New Machine Onboarding Flow** — src_app_addmachinedialog, src_profile_builder_build_scaffold, src_profile_profile, src_paths_profiles_dir [EXTRACTED 1.00]
- **Excel Import Diff-and-Apply Flow** — src_app_importdialog, src_excel_import_read_rows_generic, src_datastore_datastore [EXTRACTED 1.00]

## Communities (12 total, 3 thin omitted)

### Community 0 - "UI Shell & Machine Selection"
Cohesion: 0.23
Nodes (13): Sidecar Metadata Separation Pattern, AddMachineDialog, App (Main Window), _cargar_perfiles function, DuplicatesDialog, MachineSelector Dialog, main function, RecordDialog (+5 more)

### Community 1 - "Profile-Driven Data Engine"
Cohesion: 0.23
Nodes (12): Byte-Perfect CSV Round-Trip, Profile-Driven Generic Data Engine, Maquina 232 Profile JSON, DataStore, _format_value helper, _to_number helper, Campo dataclass, _campo_from_dict (+4 more)

### Community 2 - "Excel Import & Mapping"
Cohesion: 0.25
Nodes (8): ImportDialog, guess_mapping (legacy), guess_mapping_generic, normalize_code, normalize_value, read_headers, read_rows (legacy), read_rows_generic

### Community 3 - "Docs: Core Architecture"
Cohesion: 0.33
Nodes (7): Byte-perfect File Reconstruction, Configurador de Parámetros de Planta, datastore.py, paths.py, profile.py, run.bat, test_engine.py

### Community 4 - "Docs: Machine Profile & CSV"
Cohesion: 0.40
Nodes (5): Máquina 232, profiles/maquina_232.json, profile_builder.py, Machine Profile (JSON), recetas232.csv

### Community 5 - "Docs: UI & Duplicate Detection"
Cohesion: 0.50
Nodes (4): app.py, Duplicate Detection Feature, ttkbootstrap, ttkbootstrap >=1.10

### Community 6 - "Docs: Excel Import Feature"
Cohesion: 0.67
Nodes (4): Excel Import Feature, excel_import.py, openpyxl, openpyxl >=3.1

### Community 7 - "Build & Packaging"
Cohesion: 1.00
Nodes (3): build.bat, Portable EXE (ConfiguradorPlanta.exe), pyinstaller >=6.0

### Community 8 - "Profile Builder (CSV Sniffing)"
Cohesion: 0.67
Nodes (3): build_scaffold, sniff_csv, _sniff_tipo

## Knowledge Gaps
- **22 isolated node(s):** `Maquina 232 Profile JSON`, `RecordDialog`, `_to_number helper`, `_format_value helper`, `open_workbook` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `App (Main Window)` connect `UI Shell & Machine Selection` to `Profile-Driven Data Engine`, `Excel Import & Mapping`?**
  _High betweenness centrality (0.168) - this node is a cross-community bridge._
- **Why does `Configurador de Parámetros de Planta` connect `Docs: Core Architecture` to `Docs: Machine Profile & CSV`, `Docs: UI & Duplicate Detection`, `Docs: Excel Import Feature`, `Build & Packaging`, `Sidecar Metadata Store`?**
  _High betweenness centrality (0.133) - this node is a cross-community bridge._
- **Why does `DataStore` connect `Profile-Driven Data Engine` to `UI Shell & Machine Selection`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `DataStore` (e.g. with `Byte-Perfect CSV Round-Trip` and `Profile-Driven Generic Data Engine`) actually correct?**
  _`DataStore` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Maquina 232 Profile JSON`, `RecordDialog`, `_to_number helper` to the rest of the system?**
  _23 weakly-connected nodes found - possible documentation gaps or missing edges._