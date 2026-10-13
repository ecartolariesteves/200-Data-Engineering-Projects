def get_storage_folder_name(ws_id, all_items):
    STAGING = ("StagingLakehouseForDataflows", "StagingWarehouseForDataflows")
    storage_folder_id = None
    for item in all_items:
        item_type = item.get("type", "")
        item_name = item.get("displayName", "")
        folder_id = item.get("folderId", "")
        if (item_type in ("Lakehouse", "Warehouse")
                and folder_id
                and not any(item_name.startswith(p) for p in STAGING)):
            storage_folder_id = folder_id
            break

    if not storage_folder_id:
        fallback = STORAGE_FOLDER_NAME if "STORAGE_FOLDER_NAME" in dir() else "100 - Almacenamiento"
        print(f"  info Carpeta almacenamiento no detectada -- usando fallback: {fallback}")
        return fallback

    try:
        resp = requests.get(
            f"{FABRIC_API}/workspaces/{ws_id}/folders/{storage_folder_id}",
            headers=HEADERS,
            timeout=15
        )
        if resp.status_code == 200:
            name = resp.json().get("displayName", "")
            if name:
                print(f"  OK Carpeta almacenamiento: '{name}'")
                return name
    except Exception as e:
        print(f"  warning get_storage_folder: {e}")

    fallback = STORAGE_FOLDER_NAME if "STORAGE_FOLDER_NAME" in dir() else "100 - Almacenamiento"
    print(f"  info Usando fallback: {fallback}")
    return fallback


def get_deployment_pipelines(ws_id):
    pipelines = api_get(f"{FABRIC_API}/deploymentPipelines", "deployment_pipelines")
    result    = []
    for dp in (pipelines if isinstance(pipelines, list) else []):
        dp_id   = dp.get("id", "")
        dp_name = dp.get("displayName", "")
        try:
            resp = requests.get(
                f"{FABRIC_API}/deploymentPipelines/{dp_id}/stages",
                headers=HEADERS,
                timeout=20
            )
            stages = []
            if resp.status_code == 200:
                for s in resp.json().get("value", []):
                    stages.append({
                        "id":            s.get("id", ""),
                        "order":         s.get("order", 0),
                        "displayName":   s.get("displayName", ""),
                        "workspaceId":   s.get("workspaceId", ""),
                        "workspaceName": s.get("workspaceName", ""),
                        "isPublic":      s.get("isPublic", False),
                    })
            stages.sort(key=lambda x: x.get("order", 0))
        except Exception as e:
            print(f"  warning stages for '{dp_name}': {e}")
            stages = []
        result.append({
            "id":          dp_id,
            "displayName": dp_name,
            "description": dp.get("description", ""),
            "stages":      stages,
        })
    print(f"  -> {len(result)} deployment pipeline(s)")
    return result


print("OK CELL_4_additions_v33 cargado")
