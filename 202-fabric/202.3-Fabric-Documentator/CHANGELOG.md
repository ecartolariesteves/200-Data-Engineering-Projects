# Changelog

All notable changes to Fabric Project Documentator are documented here.

---

## [1.0.0] — 2026-05

### Added
- Initial public release
- Auto-documentation of Fabric workspaces via REST API
- Word (.docx) output with professional styling
- PDF output generation
- Sections: Overview, Workspace, Data Layer (Bronze/Silver/Gold), Orchestration, Consumption
- Auto-generated architecture diagrams using Pillow (no external tools required)
- Pipeline diagrams with activity flow visualization
- Lakehouse folder structure tables with file format detection
- Data Warehouse schema reader via SQL Analytics Endpoint
- Semantic Model documentation
- Power BI report tab placeholders
- `INSTALL.ipynb` — one-click installer that downloads config files from GitHub
- Manual screenshot override system (`Figura1.png`, `Figura2.png`, ...)
- Capacity info (SKU, autoscaling, throttling)

### Architecture
- Modular cell design: each section is a standalone `.py` module loaded at runtime
- All colors and styles centralized in `CELL_6a_style_helpers.py`
- Diagrams generated with PIL/Pillow — no Matplotlib or external chart libs needed
