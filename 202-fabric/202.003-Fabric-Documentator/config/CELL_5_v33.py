from datetime import datetime

print("=" * 60)
print("Iniciando recoleccion de metadatos...")
print("=" * 60)

all_workspaces = get_workspaces()

workspaces = [
    w for w in all_workspaces
    if w.get("displayName") in WORKSPACE_PURPOSES
]

if not workspaces:
    raise ValueError(
        f"No se encontraron los workspaces definidos en WORKSPACE_PURPOSES.\n"
        f"Definidos: {list(WORKSPACE_PURPOSES.keys())}\n"
        f"Disponibles: {[w.get('displayName') for w in all_workspaces]}"
    )

print(f"\nDocumentando {len(workspaces)} workspace(s):")
for w in workspaces:
    print(f"   - {w['displayName']} -- {WORKSPACE_PURPOSES[w['displayName']]}")

print("\nObteniendo informacion de capacidad...")
capacity_id   = next((w.get("capacityId") for w in workspaces if w.get("capacityId")), None)
capacity_info = get_capacity_info(capacity_id) if capacity_id else {**CAPACITY_INFO_OVERRIDE, "source": "manual"}
print(f"   -> {capacity_info['displayName']} | {capacity_info['sku']} | {capacity_info['region']}")

project_data = {
    "generated_at":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "all_workspaces":       all_workspaces,
    "capacity_info":        capacity_info,
    "capacity_id":          capacity_id or "--",
    "workspaces":           [],
    "deployment_pipelines": []
}

for ws in workspaces:
    ws_id   = ws.get("id")
    ws_name = ws.get("displayName", "Unknown")
    print(f"\n{'--'*25}")
    print(f"Workspace: {ws_name} [{ws_id}]")
    print(f"{'--'*25}")

    print("  Pipelines...")
    pipelines = get_pipelines(ws_id)
    print(f"     -> {len(pipelines)} pipeline(s)")

    print("  Notebooks...")
    notebooks = get_notebooks(ws_id)
    print(f"     -> {len(notebooks)} notebook(s)")

    print("  Lakehouses...")
    lakehouses = get_lakehouses(ws_id)
    # Enriquecer lakehouses con ficheros si no tienen tablas Delta reales
    STAGING_PREFIXES = ("StagingLakehouseForDataflows", "DataflowsStagingLakehouse")
    STAGING_SCHEMAS  = {
        "StagingLakehouseForDataflows", "DataflowsStagingLakehouse",
        "DataflowsStagingWarehouse",    "StagingWarehouseForDataflows"
    }
    for lh in lakehouses:
        if lh["name"].startswith(STAGING_PREFIXES):
            lh["files"] = []
            continue
        real_tables = [
            t for t in lh.get("tables", [])
            if t.get("schema", "") not in STAGING_SCHEMAS
            and not any(t.get("schema","").startswith(p) for p in STAGING_PREFIXES)
        ]
        if not real_tables:
            lh["files"] = get_lakehouse_files(lh["name"])
            if lh["files"]:
                print(f"     -> {lh['name']}: {len(lh['files'])} carpetas en Files/")
        else:
            lh["files"] = []
    print(f"     -> {len(lakehouses)} lakehouse(s)")

    print("  Data Warehouses...")
    warehouses = get_warehouses(ws_id)
    print(f"     -> {len(warehouses)} warehouse(s)")

    print("  Semantic Models...")
    semantic_models_raw = get_semantic_models(ws_id)
    semantic_models = []
    for sm in semantic_models_raw:
        sm_id      = sm.get("id", "")
        sm_name    = sm.get("name", "")
        sm_details = get_semantic_model_details(ws_id, sm_id, sm_name)
        sm["details"] = sm_details
        semantic_models.append(sm)
    print(f"     -> {len(semantic_models)} modelo(s)")

    print("  Reports...")
    reports = get_reports(ws_id)
    print(f"     -> {len(reports)} reporte(s)")

    print("  Carpetas de datos...")
    folder_names = get_folder_names(ws_id)

    print("  Carpeta de almacenamiento...")
    all_ws_items   = api_get(f"{FABRIC_API}/workspaces/{ws_id}/items", "all_items")
    storage_folder = get_storage_folder_name(ws_id, all_ws_items)

    print("  Pipeline principal...")
    main_p                   = detect_main_pipeline(pipelines)
    main_pipeline_activities = []
    main_pipeline_name       = ""
    if main_p:
        main_pipeline_name       = main_p["name"]
        main_pipeline_activities = get_pipeline_definition(ws_id, main_p["id"])
        print(f"     -> '{main_pipeline_name}' ({len(main_pipeline_activities)} actividades)")

    real_lh = [lh for lh in lakehouses
               if not lh["name"].startswith("StagingLakehouseForDataflows")]
    real_dw = [dw for dw in warehouses
               if not dw["name"].startswith("StagingWarehouseForDataflows")]

    project_data["workspaces"].append({
        "id":                       ws_id,
        "name":                     ws_name,
        "purpose":                  WORKSPACE_PURPOSES.get(ws_name, "--"),
        "type":                     ws.get("type", ""),
        "capacityId":               ws.get("capacityId", ""),
        "state":                    ws.get("state", "Active"),
        "pipelines":                pipelines,
        "notebooks":                notebooks,
        "lakehouses":               lakehouses,
        "warehouses":               warehouses,
        "semantic_models":          semantic_models,
        "reports":                  reports,
        "folder_names":             folder_names,
        "storage_folder":           storage_folder,
        "main_pipeline_activities": main_pipeline_activities,
        "main_pipeline_name":       main_pipeline_name,
        "_has_lakehouse":           len(real_lh) > 0,
        "_has_dw":                  len(real_dw) > 0,
        "_has_pipelines":           len(pipelines) > 0,
        "_has_notebooks":           len(notebooks) > 0,
        "_has_semantic_models":     len(semantic_models) > 0,
        "_has_reports":             len(reports) > 0,
    })

# Deployment pipelines
print("\nLeyendo deployment pipelines...")
ws_id_first = project_data["workspaces"][0]["id"] if project_data["workspaces"] else None
if ws_id_first:
    project_data["deployment_pipelines"] = get_deployment_pipelines(ws_id_first)

print(f"\nOK Recoleccion completada -- {datetime.now().strftime('%H:%M:%S')}")
print(f"   {len(project_data['workspaces'])} workspace(s) procesado(s)")
print(f"   {len(project_data['deployment_pipelines'])} deployment pipeline(s)")
