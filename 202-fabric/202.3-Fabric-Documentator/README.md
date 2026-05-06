# 🔷 Fabric Project Documentator

> Automatic technical documentation generator for Microsoft Fabric projects.

Reads workspace metadata directly via the Fabric & Power BI REST APIs and produces a professional **Word (.docx)** and **PDF** document — no manual copy-paste, no stale docs.

---

## ✨ What it documents

| Section | Content |
|---|---|
| 1. Overview | Project description, client, version, security level |
| 2. Fabric Workspace | Architecture diagrams, capacity info, autoscaling |
| 3. Data Layer | Bronze / Silver / Gold with table schemas |
| 4. Orchestration Layer | Pipelines with diagrams, storage, deployment |
| 5. Consumption Layer | Semantic Models, Power BI report tabs |

---

## 🚀 Quick Start

### Requirements
- Microsoft Fabric workspace with at least one Lakehouse
- Contributor access to the workspace
- A GitHub Fine-grained PAT (read-only on this repo) for the installer

### Step 1 — Run the installer
1. Import `INSTALL.ipynb` into your Fabric workspace
2. Set `DEST_LAKEHOUSE` to your Lakehouse name and paste your GitHub PAT
3. Run All — it downloads all config files to the Lakehouse automatically

### Step 2 — Configure the project
Open `FabricProjectDocumentator.ipynb` and edit **Cell 2**:

```python
DOC_CLIENT   = "Client Name"
DOC_REF      = "P26-000001"
DOC_AUTHOR   = "Your Name"
DOC_SECURITY = "External"
DOC_VERSION  = "V1"
```

And **Cell 2b** — your workspaces:

```python
WORKSPACE_PURPOSES = {
    "MyProject_Development": "Development – Datalake, ETL",
    "MyProject_Production":  "Production  – Datalake, ETL",
}
```

### Step 3 — Generate
Run All. The document is saved to:
```
MyLakehouse/Files/docs/FabricProjectDocumentation_YYYYMMDD_HHMM.docx
```

---

## 📁 Repository structure

```
fabric-project-documentator/
├── README.md
├── INSTALL.ipynb                        ← Run once in Fabric to install
├── notebook/
│   └── FabricProjectDocumentator.ipynb  ← Main notebook
├── config/                              ← Cell modules (auto-downloaded)
│   ├── CELL_4_functions.py
│   ├── CELL_4_additions_v33.py
│   ├── CELL_5_v33.py
│   ├── CELL_6a_style_helpers.py
│   ├── CELL_6b_v32.py
│   ├── CELL_6c_section2.py
│   ├── CELL_6d_v33.py
│   ├── CELL_6e_v33.py
│   ├── CELL_6f_additions_v33.py
│   └── CELL_6f_consumption_v35.py
├── assets/
│   └── project_logo.jpg                 ← Replace with your logo
└── docs/
    └── CHANGELOG.md
```

---

## ⚙️ Customization

### Logo
Upload your logo to:
```
Files/docs/img/project_logo.jpg
```

### Manual screenshots (optional override)
Place screenshots in `Files/docs/img/` named `FiguraN.png` — they automatically replace the auto-generated diagrams:
```
Figura1.png  ← Azure architecture diagram
Figura2.png  ← Runbook diagram
Figura3.png  ← Folder structure diagram
```

### Power BI tabs
Edit in Cell 2b:
```python
POWERBI_TABS = [
    {"name": "Overview",   "description": "General KPIs..."},
    {"name": "Sales",      "description": "Sales analysis..."},
    {"name": "Financial",  "description": "Key financial indicators..."},
]
```

---

## 🗑️ Uninstall

```python
import shutil
shutil.rmtree("/lakehouse/default/Files/docs/config", ignore_errors=True)
shutil.rmtree("/lakehouse/default/Files/docs/img",    ignore_errors=True)
print("Config files removed")
```

Then delete `FabricProjectDocumentator.ipynb` from the workspace manually.

---

## 📋 Changelog

See [CHANGELOG.md](docs/CHANGELOG.md)

---

## 👤 Author

**Edgar Estevez** — [github.com/ecartolariesteves](https://github.com/ecartolariesteves)

---

## 📄 License

MIT — free to use, modify and distribute.
