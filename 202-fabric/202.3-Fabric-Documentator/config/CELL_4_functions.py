import requests
import json
import base64 as _b64

# =============================================================================
# HELPERS DE API
# =============================================================================

def api_get(url, label=""):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("value", data)
        else:
            print(f"  warning  {label}: HTTP {resp.status_code} -- {resp.text[:120]}")
            return []
    except Exception as e:
        print(f"  error {label}: {e}")
        return []


# =============================================================================
# WORKSPACES
# =============================================================================

def get_workspaces():
    print("Obteniendo workspaces...")
    data = api_get(f"{FABRIC_API}/workspaces", "workspaces")
    print(f"   -> {len(data)} workspace(s)")
    return data


# =============================================================================
# PIPELINES
# =============================================================================

def get_pipelines(workspace_id):
    items = api_get(f"{FABRIC_API}/workspaces/{workspace_id}/dataPipelines", "pipelines")
    result = []
    for p in items:
        result.append({
            "id":           p.get("id"),
            "name":         p.get("displayName"),
            "description":  p.get("description", ""),
            "type":         p.get("type"),
            "createdDate":  p.get("createdDate", ""),
            "modifiedDate": p.get("modifiedDate", "")
        })
    return result


# =============================================================================
# NOTEBOOKS
# =============================================================================

def get_notebooks(workspace_id):
    items = api_get(f"{FABRIC_API}/workspaces/{workspace_id}/notebooks", "notebooks")
    result = []
    for nb in items:
        nb_detail = api_get(
            f"{FABRIC_API}/workspaces/{workspace_id}/notebooks/{nb['id']}",
            f"notebook:{nb.get('displayName','?')}"
        )
        code_cells = []
        if INCLUDE_NOTEBOOK_CODE:
            definition = nb_detail.get("definition", {}) if isinstance(nb_detail, dict) else {}
            for part in definition.get("parts", []):
                payload = part.get("payload", "")
                if payload:
                    try:
                        decoded = _b64.b64decode(payload).decode("utf-8", errors="replace")
                        code_cells.append(decoded[:4000])
                    except Exception:
                        pass
        result.append({
            "id":           nb.get("id"),
            "name":         nb.get("displayName"),
            "description":  nb.get("description", ""),
            "createdDate":  nb.get("createdDate", ""),
            "modifiedDate": nb.get("modifiedDate", ""),
            "code":         code_cells
        })
    return result


# =============================================================================
# LAKEHOUSES
# =============================================================================

STAGING_LH_PREFIX = "StagingLakehouseForDataflows"


def get_lakehouses(workspace_id):
    items = api_get(f"{FABRIC_API}/workspaces/{workspace_id}/lakehouses", "lakehouses")
    result = []
    for lh in items:
        lh_id   = lh.get("id")
        lh_name = lh.get("displayName", "")
        if lh_name.startswith(STAGING_LH_PREFIX):
            print(f"  info  Lakehouse '{lh_name}' es Staging de Dataflows -- omitido.")
            tables = []
        else:
            tables = get_lakehouse_tables_spark(lh_name) if INCLUDE_TABLE_SCHEMAS else []
        props  = lh.get("properties", {})
        sql_ep = ""
        if isinstance(props, dict):
            sep    = props.get("sqlEndpointProperties", {})
            sql_ep = sep.get("connectionString", "") if isinstance(sep, dict) else ""
        result.append({
            "id":           lh_id,
            "name":         lh_name,
            "description":  lh.get("description", ""),
            "createdDate":  lh.get("createdDate", ""),
            "modifiedDate": lh.get("modifiedDate", ""),
            "sqlEndpoint":  sql_ep,
            "tables":       tables
        })
    return result


def get_lakehouse_tables_spark(lakehouse_name):
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()

        try:
            schemas_raw = [r[0] for r in spark.sql("SHOW SCHEMAS").collect()]
        except Exception:
            schemas_raw = ["default"]

        def clean_schema(s):
            parts = s.split(".")
            return parts[-1] if parts else s

        schemas = list(dict.fromkeys(
            clean_schema(s) for s in schemas_raw
            if clean_schema(s) not in ("information_schema", "sys", "")
        ))
        if not schemas:
            schemas = ["default"]

        tables = []
        for schema in schemas:
            try:
                if schema == "default":
                    tbl_df = spark.sql("SHOW TABLES")
                else:
                    tbl_df = spark.sql(f"SHOW TABLES IN `{schema}`")

                for row in tbl_df.collect():
                    tname = (
                        row["tableName"] if "tableName" in row.__fields__ else
                        row["name"]      if "name"      in row.__fields__ else
                        str(row[1])
                    )
                    if not tname:
                        continue

                    full_ref = f"`{schema}`.`{tname}`" if schema != "default" else f"`{tname}`"
                    schema_cols = []
                    try:
                        for r in spark.sql(f"DESCRIBE TABLE {full_ref}").collect():
                            col_name = str(r[0])
                            col_type = str(r[1])
                            comment  = str(r[2]) if len(r) > 2 else ""
                            if col_name and not col_name.startswith("#") and col_type:
                                schema_cols.append({
                                    "column":  col_name,
                                    "type":    col_type,
                                    "comment": clean_comment(comment) if "clean_comment" in dir() else comment
                                })
                    except Exception as e_desc:
                        schema_cols = [{"column": f"(Error: {str(e_desc)[:60]})", "type": "", "comment": ""}]

                    tables.append({
                        "schema":      schema,
                        "name":        tname,
                        "format":      "delta",
                        "schema_cols": schema_cols
                    })

            except Exception as e_tbl:
                print(f"  warning Lakehouse '{lakehouse_name}' -- schema '{schema}': {str(e_tbl)[:100]}")

        return tables

    except Exception as e:
        print(f"  warning Spark no disponible para Lakehouse '{lakehouse_name}': {e}")
        return []


# =============================================================================
# DATA WAREHOUSES
# =============================================================================

STAGING_DW_PREFIXES = (
    "StagingWarehouseForDataflows",
    "DataflowsStagingWarehouse",
)
STAGING_DW_PREFIX = STAGING_DW_PREFIXES[0]  # backward compat


def get_warehouses(workspace_id):
    items = api_get(f"{FABRIC_API}/workspaces/{workspace_id}/warehouses", "warehouses")
    result = []
    for wh in items:
        wh_id    = wh.get("id")
        wh_name  = wh.get("displayName", "")
        props    = wh.get("properties", {})
        conn_str = ""
        if isinstance(props, dict):
            conn_str = props.get("connectionString", "")
        tables = get_warehouse_schema_spark(wh_name, conn_str) if INCLUDE_TABLE_SCHEMAS else []
        result.append({
            "id":               wh_id,
            "name":             wh_name,
            "description":      wh.get("description", ""),
            "createdDate":      wh.get("createdDate", ""),
            "modifiedDate":     wh.get("modifiedDate", ""),
            "connectionString": conn_str,
            "tables":           tables
        })
    return result
# =============================================================================
# DW LAYER RESOLUTION  -- insertar justo antes de get_warehouse_schema_spark
# =============================================================================

DW_SCHEMA_FIXED = {
    "bronze":  "bronze", "brz":     "bronze", "tmp":     "bronze",
    "temp":    "bronze", "stg":     "bronze", "staging": "bronze", "raw": "bronze",
    "silver":  "silver", "slv":     "silver",
    "gold":    "gold",   "gld":     "gold",
}

DW_SCHEMA_AMBIGUOUS = {"dwh", "dw", "dbo", "int", "core", "mart", "dm", "pbi", "report"}

DW_TABLE_INFIX_TO_LAYER = [
    ("_TD_",  "gold"),
    ("_TH_",  "gold"),
    ("_TA_",  "silver"),
    ("_BRZ_", "bronze"),
    ("_TMP_", "bronze"),
    ("_STG_", "bronze"),
]

DW_TABLE_PREFIX_TO_LAYER = [
    ("BRZ_",  "bronze"), ("TMP_",  "bronze"), ("STG_",  "bronze"),
    ("TEMP_", "bronze"), ("RAW_",  "bronze"),
    ("SLV_",  "silver"), ("INT_",  "silver"), ("SRC_",  "silver"),
    ("CMN_",  "silver"), ("PRD_",  "silver"),
    ("GLD_",  "gold"),   ("PBI_",  "gold"),   ("RPT_",  "gold"),
    ("DM_",   "gold"),   ("TD_",   "gold"),   ("TH_",   "gold"),
]


def _dw_resolve_layer(schema, table_name):
    s           = schema.lower()
    tname_upper = table_name.upper()
    for infix, layer in DW_TABLE_INFIX_TO_LAYER:
        if infix in tname_upper:
            return layer
    if s in DW_SCHEMA_FIXED:
        return DW_SCHEMA_FIXED[s]
    for prefix, layer in DW_TABLE_PREFIX_TO_LAYER:
        if tname_upper.startswith(prefix):
            return layer
    return "silver"


def _get_dw_jdbc_token():
    try:
        import notebookutils
        return notebookutils.credentials.getToken("https://database.windows.net/")
    except Exception as e:
        print(f"  warning  _get_dw_jdbc_token: {e}")
        return None


def get_dw_tables_by_layer(all_warehouses, layer):
    result = []
    seen   = set()
    for wh in (all_warehouses or []):
        if any(wh.get("name", "").startswith(p) for p in STAGING_DW_PREFIXES):
            continue
        for t in wh.get("tables", []):
            t_layer = t.get("layer") or _dw_resolve_layer(
                t.get("schema", ""), t.get("name", ""))
            if t_layer == layer:
                key = f"{t.get('schema','')}.{t.get('name','')}"
                if key not in seen:
                    seen.add(key)
                    result.append(t)
    return sorted(result, key=lambda t: (t.get("schema", ""), t.get("name", "")))

def get_warehouse_schema_spark(warehouse_name, connection_string=""):
    """
    Lee el esquema del Data Warehouse.
 
    Orden de intentos (no rompe los métodos existentes):
      Método 1 — SHOW TABLES via Spark SQL (original, Lakehouse-backed DW)
      Método 2 — INFORMATION_SCHEMA via Spark SQL (original)
      Método 3 — JDBC con token AAD  ← NUEVO, solo si 1 y 2 fallan
 
    Devuelve lista de tablas con estructura idéntica a get_lakehouse_tables_spark:
        [{
            "schema":      "dwh",
            "name":        "PRD_TD_Estados",
            "type":        "TABLE",          ← TABLE o VIEW
            "format":      "sql",            ← para compatibilidad con schema_table
            "layer":       "silver",         ← campo nuevo para CELL_6d
            "schema_cols": [                 ← igual que Lakehouse
                {"column": "CodEstado", "type": "varchar", "nullable": True}
            ]
        }]
    """
    # --- Staging: omitir siempre ---
    if any(warehouse_name.startswith(p) for p in STAGING_DW_PREFIXES):
        print(f"  info  DW '{warehouse_name}' es Staging -- omitido.")
        return []
 
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
 
        # -----------------------------------------------------------------
        # Método 1 — SHOW TABLES via Spark (original, sin cambios)
        # -----------------------------------------------------------------
        try:
            rows = spark.sql(f"SHOW TABLES IN `{warehouse_name}`").collect()
            if rows:
                tables = []
                for row in rows:
                    tname = (
                        row["tableName"] if "tableName" in row.__fields__ else
                        row["name"]      if "name"      in row.__fields__ else
                        str(row[1])
                    )
                    if not tname:
                        continue
                    schema_cols = []
                    try:
                        for c in spark.sql(
                                f"DESCRIBE TABLE `{warehouse_name}`.`{tname}`"
                        ).collect():
                            col_name = str(c[0])
                            col_type = str(c[1])
                            if col_name and not col_name.startswith("#") and col_type:
                                schema_cols.append({
                                    "column":   col_name,
                                    "type":     col_type,
                                    "nullable": True
                                })
                    except Exception:
                        pass
                    tables.append({
                        "schema":      "dbo",
                        "name":        tname,
                        "type":        "TABLE",
                        "format":      "sql",
                        "layer":       _dw_resolve_layer("dbo", tname),
                        "schema_cols": schema_cols
                    })
                if tables:
                    print(f"  OK  DW '{warehouse_name}': {len(tables)} tabla(s) via Spark M1")
                    return tables
        except Exception:
            pass
 
        # -----------------------------------------------------------------
        # Método 2 — INFORMATION_SCHEMA via Spark (original, sin cambios)
        # -----------------------------------------------------------------
        try:
            query = f"""
                SELECT
                    c.TABLE_SCHEMA,
                    c.TABLE_NAME,
                    t.TABLE_TYPE,
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    c.IS_NULLABLE
                FROM [{warehouse_name}].INFORMATION_SCHEMA.COLUMNS c
                JOIN [{warehouse_name}].INFORMATION_SCHEMA.TABLES  t
                  ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
                 AND c.TABLE_NAME   = t.TABLE_NAME
                WHERE c.TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA', 'sys')
                ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
            """
            rows = spark.sql(query).collect()
            if rows:
                tables_dict = {}
                for r in rows:
                    key = (r["TABLE_SCHEMA"], r["TABLE_NAME"])
                    if key not in tables_dict:
                        tables_dict[key] = {
                            "schema":      r["TABLE_SCHEMA"],
                            "name":        r["TABLE_NAME"],
                            "type":        r["TABLE_TYPE"],
                            "format":      "sql",
                            "layer":       _dw_resolve_layer(
                                               r["TABLE_SCHEMA"], r["TABLE_NAME"]),
                            "schema_cols": []
                        }
                    tables_dict[key]["schema_cols"].append({
                        "column":   r["COLUMN_NAME"],
                        "type":     r["DATA_TYPE"],
                        "nullable": r["IS_NULLABLE"] == "YES"
                    })
                result = list(tables_dict.values())
                print(f"  OK  DW '{warehouse_name}': {len(result)} tabla(s) via Spark M2")
                return result
        except Exception:
            pass
 
    except Exception:
        pass
 
    # -----------------------------------------------------------------
    # Método 3 — JDBC con token AAD (NUEVO — solo llega aquí si M1 y M2 fallan)
    # No usa pyodbc, no mata la sesión Livy
    # -----------------------------------------------------------------
    if not connection_string:
        print(f"  info  DW '{warehouse_name}': sin connection_string para JDBC.")
        return []
 
    print(f"  info  DW '{warehouse_name}': Spark no puede leerlo, intentando JDBC...")
 
    token = _get_dw_jdbc_token()
    if not token:
        print(f"  warning  DW '{warehouse_name}': no se pudo obtener token JDBC.")
        return []
 
    # Limpiar endpoint (puede venir con http:// o sin protocolo)
    endpoint = connection_string.strip().rstrip("/")
    for prefix in ("jdbc:sqlserver://", "https://", "http://"):
        if endpoint.startswith(prefix):
            endpoint = endpoint[len(prefix):]
 
    jdbc_url = (
        f"jdbc:sqlserver://{endpoint}:1433;"
        f"database={warehouse_name};"
        f"encrypt=true;"
        f"trustServerCertificate=false;"
        f"loginTimeout=30;"
    )
 
    # Sin ORDER BY (limitación JDBC/Spark — se ordena después en Python)
    jdbc_query = """
        SELECT
            s.name      AS schema_name,
            t.name      AS table_name,
            'TABLE'     AS object_type,
            c.name      AS column_name,
            tp.name     AS data_type,
            c.max_length,
            c.is_nullable,
            c.column_id AS ordinal
        FROM sys.tables t
        JOIN sys.schemas s  ON t.schema_id   = s.schema_id
        JOIN sys.columns c  ON t.object_id   = c.object_id
        JOIN sys.types   tp ON c.user_type_id = tp.user_type_id
        WHERE s.name NOT IN (
            'information_schema','sys','guest',
            'db_owner','db_accessadmin','db_securityadmin','db_ddladmin',
            'db_backupoperator','db_datareader','db_datawriter',
            'db_denydatareader','db_denydatawriter'
        )
        UNION ALL
        SELECT
            s.name, v.name, 'VIEW',
            c.name, tp.name,
            c.max_length, c.is_nullable, c.column_id
        FROM sys.views v
        JOIN sys.schemas s  ON v.schema_id   = s.schema_id
        JOIN sys.columns c  ON v.object_id   = c.object_id
        JOIN sys.types   tp ON c.user_type_id = tp.user_type_id
        WHERE s.name NOT IN (
            'information_schema','sys','guest',
            'db_owner','db_accessadmin','db_securityadmin','db_ddladmin',
            'db_backupoperator','db_datareader','db_datawriter',
            'db_denydatareader','db_denydatawriter'
        )
    """
 
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
 
        df = (spark.read
              .format("jdbc")
              .option("url",         jdbc_url)
              .option("query",       jdbc_query)
              .option("accessToken", token)
              .option("driver",      "com.microsoft.sqlserver.jdbc.SQLServerDriver")
              .load())
 
        # Ordenar en Spark (no en SQL por limitación de subquery)
        rows = df.orderBy("schema_name", "table_name", "ordinal").collect()
 
    except Exception as e:
        print(f"  warning  DW '{warehouse_name}' JDBC error: {str(e)[:200]}")
        return []
 
    if not rows:
        print(f"  info  DW '{warehouse_name}': JDBC sin tablas.")
        return []
 
    # Construir estructura
    tables_dict = {}
    for r in rows:
        schema = r["schema_name"]
        tname  = r["table_name"]
        key    = (schema, tname)
        if key not in tables_dict:
            tables_dict[key] = {
                "schema":      schema,
                "name":        tname,
                "type":        r["object_type"],
                "format":      "sql",
                "layer":       _dw_resolve_layer(schema, tname),
                "schema_cols": []
            }
        tables_dict[key]["schema_cols"].append({
            "column":   r["column_name"],
            "type":     r["data_type"],
            "nullable": bool(r["is_nullable"])
        })
 
    result = list(tables_dict.values())
 
    # Log resumen por capa
    layers = {}
    for t in result:
        l = t["layer"]
        layers[l] = layers.get(l, 0) + 1
    print(f"  OK  DW '{warehouse_name}': {len(result)} objeto(s) via JDBC M3")
    for layer, count in sorted(layers.items()):
        print(f"       -> {layer}: {count} objeto(s)")
 
    return result

# =============================================================================
# SEMANTIC MODELS
# =============================================================================

def get_semantic_models(workspace_id):
    items = api_get(f"{FABRIC_API}/workspaces/{workspace_id}/semanticModels", "semantic_models")
    if not items:
        items = api_get(f"{POWERBI_API}/groups/{workspace_id}/datasets", "pbi_datasets")
    result = []
    for ds in (items if isinstance(items, list) else []):
        ds_id   = ds.get("id") or ds.get("datasetId")
        ds_name = ds.get("displayName") or ds.get("name", "")
        tables_raw = api_get(
            f"{POWERBI_API}/groups/{workspace_id}/datasets/{ds_id}/tables",
            f"ds_tables:{ds_name}"
        )
        rels_raw = api_get(
            f"{POWERBI_API}/groups/{workspace_id}/datasets/{ds_id}/relationships",
            f"ds_rels:{ds_name}"
        )
        tables_detail = []
        for t in (tables_raw if isinstance(tables_raw, list) else []):
            tables_detail.append({
                "name":     t.get("name", ""),
                "columns":  [{"name": c.get("name",""), "dataType": c.get("dataType",""), "isHidden": c.get("isHidden",False)} for c in t.get("columns",[])],
                "measures": [{"name": m.get("name",""), "expression": m.get("expression","")} for m in t.get("measures",[])]
            })
        result.append({
            "id":            ds_id,
            "name":          ds_name,
            "description":   ds.get("description", ""),
            "configuredBy":  ds.get("configuredBy", ""),
            "createdDate":   ds.get("createdDate", ""),
            "modifiedDate":  ds.get("modifiedDate", ""),
            "isRefreshable": ds.get("isRefreshable", False),
            "tables":        tables_detail,
            "relationships": [
                {
                    "fromTable":              r.get("fromTable",""),
                    "fromColumn":             r.get("fromColumn",""),
                    "toTable":                r.get("toTable",""),
                    "toColumn":               r.get("toColumn",""),
                    "crossFilteringBehavior": r.get("crossFilteringBehavior","")
                }
                for r in (rels_raw if isinstance(rels_raw, list) else [])
            ]
        })
    return result


# =============================================================================
# REPORTS
# =============================================================================

def get_reports(workspace_id):
    reports = api_get(f"{POWERBI_API}/groups/{workspace_id}/reports", "reports")
    result = []
    for r in (reports if isinstance(reports, list) else []):
        result.append({
            "id":               r.get("id"),
            "name":             r.get("name"),
            "description":      r.get("description", ""),
            "datasetId":        r.get("datasetId", ""),
            "datasetName":      r.get("datasetName", ""),
            "createdBy":        r.get("createdBy", ""),
            "createdDateTime":  r.get("createdDateTime", ""),
            "modifiedDateTime": r.get("modifiedDateTime", "")
        })
    return result


# =============================================================================
# FOLDER NAMES (Bronze / Silver / Gold)
# =============================================================================

def get_folder_names(workspace_id):
    """
    Detecta las carpetas Bronze, Silver y Gold del workspace.
    Resuelve nombres via API de folders.
    Tambien detecta la carpeta padre de las capas (ETL, Data, etc.)
    para el diagrama de estructura.
    """
    items = api_get(
        f"{FABRIC_API}/workspaces/{workspace_id}/items",
        "workspace_items_folders"
    )

    folders = {"bronze": None, "silver": None, "gold": None, "etl_parent": None}

    # 1. Recoger todos los folderIds unicos
    folder_ids = set()
    for item in (items if isinstance(items, list) else []):
        fid = item.get("folderId", "")
        if fid:
            folder_ids.add(fid)

    # 2. Resolver nombre y parentId de cada carpeta via API
    folder_id_to_info = {}
    for fid in folder_ids:
        try:
            resp = requests.get(
                f"{FABRIC_API}/workspaces/{workspace_id}/folders/{fid}",
                headers=HEADERS,
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                folder_id_to_info[fid] = {
                    "name":     data.get("displayName", ""),
                    "parentId": data.get("parentFolderId", None)
                }
        except Exception as e:
            print(f"  warning get_folder_name {fid[:8]}: {e}")

    # 3. Buscar bronze/silver/gold en los nombres resueltos
    for fid, info in folder_id_to_info.items():
        name_lower = info["name"].lower()
        if "bronze" in name_lower and not folders["bronze"]:
            folders["bronze"] = info["name"]
            # Guardar folderId del padre de Bronze para el diagrama
            parent_id = info.get("parentId")
            if parent_id and parent_id in folder_id_to_info:
                folders["etl_parent"] = folder_id_to_info[parent_id]["name"]
        elif "silver" in name_lower and not folders["silver"]:
            folders["silver"] = info["name"]
        elif "gold" in name_lower and not folders["gold"]:
            folders["gold"] = info["name"]

    # 4. Fallback a nombres estandar
    if not folders["bronze"]:
        folders["bronze"] = "001 - Data - Bronze"
        print("  info  Carpeta Bronze no detectada -- usando nombre estandar")
    if not folders["silver"]:
        folders["silver"] = "002 - Data - Silver"
        print("  info  Carpeta Silver no detectada -- usando nombre estandar")
    if not folders["gold"]:
        folders["gold"] = "003 - Data - Gold"
        print("  info  Carpeta Gold no detectada -- usando nombre estandar")

    print(f"  Bronze:     {folders['bronze']}")
    print(f"  Silver:     {folders['silver']}")
    print(f"  Gold:       {folders['gold']}")
    print(f"  ETL Parent: {folders['etl_parent'] or '(raiz workspace)'}")
    return folders


def get_lakehouse_files(lakehouse_name):
    """
    Lista las carpetas de primer y segundo nivel en Files/ del Lakehouse.
    Se usa cuando el Lakehouse no tiene tablas Delta registradas
    (datos en formato fichero: parquet, csv, json, etc.)
    Retorna lista de dicts con name, path, subfolders.
    """
    base_path = "/lakehouse/default/Files"
    result    = []

    try:
        import os
        if not os.path.exists(base_path):
            return []

        for item in sorted(os.listdir(base_path)):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                # Contar ficheros y subcarpetas
                try:
                    subitems   = os.listdir(item_path)
                    subfolders = [s for s in subitems
                                  if os.path.isdir(os.path.join(item_path, s))]
                    files      = [s for s in subitems
                                  if os.path.isfile(os.path.join(item_path, s))]
                    # Detectar formatos
                    formats = set()
                    for s in subitems:
                        sp = os.path.join(item_path, s)
                        if os.path.isdir(sp):
                            # Ver ficheros dentro
                            for f in os.listdir(sp)[:5]:
                                ext = os.path.splitext(f)[1].lower()
                                if ext:
                                    formats.add(ext.lstrip("."))
                        else:
                            ext = os.path.splitext(s)[1].lower()
                            if ext:
                                formats.add(ext.lstrip("."))

                    result.append({
                        "name":       item,
                        "path":       item_path,
                        "subfolders": subfolders,
                        "files":      files,
                        "formats":    sorted(formats),
                        "n_items":    len(subitems)
                    })
                except Exception:
                    result.append({
                        "name":       item,
                        "path":       item_path,
                        "subfolders": [],
                        "files":      [],
                        "formats":    [],
                        "n_items":    0
                    })

    except Exception as e:
        print(f"  warning get_lakehouse_files '{lakehouse_name}': {e}")

    return result


print("OK get_folder_names y get_lakehouse_files actualizadas")
 

# =============================================================================
# CAPACITY INFO
# =============================================================================

def get_capacity_info(capacity_id):
    try:
        caps_fabric = api_get(f"{FABRIC_API}/capacities", "capacities_fabric")
        for cap in (caps_fabric if isinstance(caps_fabric, list) else []):
            if cap.get("id") == capacity_id:
                print(f"  Capacidad encontrada via Fabric API: {cap.get('displayName')} [{cap.get('sku')}]")
                return {
                    "displayName": cap.get("displayName", "--"),
                    "sku":         cap.get("sku", "--"),
                    "region":      cap.get("region", "--"),
                    "state":       cap.get("state", "--"),
                    "admins":      [],
                    "source":      "API"
                }
    except Exception as e:
        print(f"  warning Fabric API capacities: {e}")

    try:
        caps_pbi = api_get(f"{POWERBI_API}/capacities", "capacities_pbi")
        for cap in (caps_pbi if isinstance(caps_pbi, list) else []):
            if cap.get("id") == capacity_id:
                print(f"  Capacidad encontrada via PBI API: {cap.get('displayName')} [{cap.get('sku')}]")
                return {
                    "displayName": cap.get("displayName", "--"),
                    "sku":         cap.get("sku", "--"),
                    "region":      cap.get("region", "--"),
                    "state":       cap.get("state", "--"),
                    "admins":      cap.get("admins", []),
                    "source":      "API"
                }
    except Exception as e:
        print(f"  warning PBI API capacities: {e}")

    print(f"  info  Capacidad {capacity_id[:8]}... no visible via API -- usando CAPACITY_INFO_OVERRIDE")
    return {
        "displayName": CAPACITY_INFO_OVERRIDE.get("displayName", "--"),
        "sku":         CAPACITY_INFO_OVERRIDE.get("sku", "--"),
        "region":      CAPACITY_INFO_OVERRIDE.get("region", "--"),
        "state":       CAPACITY_INFO_OVERRIDE.get("state", "Active"),
        "admins":      CAPACITY_INFO_OVERRIDE.get("admins", []),
        "source":      "manual"
    }


# =============================================================================
# PIPELINE DEFINITION + FOLDER STRUCTURE (v3.1)
# =============================================================================

def get_pipeline_definition(ws_id, pipeline_id):
    try:
        resp = requests.post(
            f"{FABRIC_API}/workspaces/{ws_id}/dataPipelines/{pipeline_id}/getDefinition",
            headers=HEADERS,
            timeout=30
        )
        if resp.status_code != 200:
            print(f"  warning Pipeline definition HTTP {resp.status_code}")
            return []
        parts = resp.json().get("definition", {}).get("parts", [])
        for part in parts:
            if "pipeline-content" in part.get("path", ""):
                payload = part.get("payload", "")
                if payload:
                    decoded = _b64.b64decode(payload + "==").decode("utf-8", errors="replace")
                    try:
                        data = json.loads(decoded)
                    except Exception:
                        idx = decoded.rfind("}")
                        try:
                            data = json.loads(decoded[:idx+1] + "]}}")
                        except Exception:
                            data = {}
                    return data.get("properties", {}).get("activities", [])
        return []
    except Exception as e:
        print(f"  warning Error leyendo pipeline: {e}")
        return []


def get_folder_structure(ws_id):
    items   = api_get(f"{FABRIC_API}/workspaces/{ws_id}/items", "ws_items_folders")
    folders = {}
    for item in items:
        if item.get("type", "").lower() == "folder":
            fid = item.get("id", "")
            folders[fid] = {
                "name":     item.get("displayName", ""),
                "parentId": item.get("parentFolderId", None),
                "items":    []
            }
    for item in items:
        if item.get("type", "").lower() != "folder":
            fid = item.get("folderId", "")
            if fid in folders:
                folders[fid]["items"].append({
                    "name": item.get("displayName", ""),
                    "type": item.get("type", "")
                })
    return folders


def detect_main_pipeline(pipelines):
    if not pipelines:
        return None

    def score(p):
        name = p.get("name", "").lower().replace(" ", "_").replace("-", "_")
        if name.startswith("000") or "_000_" in name or name.endswith("_000"):
            return 10
        if "000" in name:
            return 9
        if "carga_completa" in name:
            return 8
        if "carga_complete" in name:
            return 7
        if "master" in name:
            return 6
        if "main" in name:
            return 5
        return 0

    best = max(pipelines, key=score)
    if score(best) > 0:
        print(f"  Pipeline principal detectado: '{best['name']}'")
        return best

    manual_name = PIPELINE_CONFIG.get("main_pipeline_name", "").strip()
    if manual_name:
        found = next((p for p in pipelines if p["name"] == manual_name), None)
        if found:
            print(f"  Pipeline principal desde config manual: '{found['name']}'")
            return found
        else:
            print(f"  warning Pipeline '{manual_name}' no encontrado. Usando el primero.")

    print(f"  info  Usando primer pipeline como principal: '{pipelines[0]['name']}'")
    return pipelines[0]


def get_pipeline_schedule_time():
    try:
        hora_str = AUTOSCALE_CONFIG.get("hora_inicio", "6:00")
        offset   = int(AUTOSCALE_CONFIG.get("pipeline_schedule_offset", 10))
        h, m     = map(int, hora_str.split(":"))
        total    = h * 60 + m + offset
        return f"{total//60}:{total%60:02d}"
    except Exception:
        return AUTOSCALE_CONFIG.get("hora_inicio", "--")

# =============================================================================
# AÑADIR AL FINAL DE CELL_4_functions.py
# Nuevas funciones para 4.3 y 4.4
# =============================================================================

def get_storage_folder_name(ws_id, all_items):
    """
    Detecta automaticamente la carpeta de almacenamiento buscando
    el folderId donde estan los Lakehouses y Warehouses reales.
    Luego resuelve el nombre via API de folders.
    Fallback: STORAGE_FOLDER_NAME de Celda 2b.
    """
    STAGING_PREFIXES = ("StagingLakehouseForDataflows", "StagingWarehouseForDataflows")

    # 1. Encontrar folderId de los items de almacenamiento reales
    storage_folder_id = None
    for item in all_items:
        item_type = item.get("type", "")
        item_name = item.get("displayName", "")
        folder_id = item.get("folderId", "")
        if (item_type in ("Lakehouse", "Warehouse")
                and folder_id
                and not any(item_name.startswith(p) for p in STAGING_PREFIXES)):
            storage_folder_id = folder_id
            break

    if not storage_folder_id:
        fallback = STORAGE_FOLDER_NAME if "STORAGE_FOLDER_NAME" in dir() else "100 - Almacenamiento"
        print(f"  info  Carpeta almacenamiento no detectada -- usando fallback: {fallback}")
        return fallback

    # 2. Resolver nombre via API
    try:
        resp = requests.get(
            f"{FABRIC_API}/workspaces/{ws_id}/folders/{storage_folder_id}",
            headers=HEADERS, timeout=15
        )
        if resp.status_code == 200:
            name = resp.json().get("displayName", "")
            if name:
                print(f"  OK  Carpeta almacenamiento: '{name}'")
                return name
    except Exception as e:
        print(f"  warning  get_storage_folder: {e}")

    fallback = STORAGE_FOLDER_NAME if "STORAGE_FOLDER_NAME" in dir() else "100 - Almacenamiento"
    print(f"  info  Usando fallback: {fallback}")
    return fallback


def get_deployment_pipelines(ws_id):
    """
    Lee los deployment pipelines de Fabric y sus stages.
    Retorna lista de dicts con id, displayName, stages.
    """
    pipelines = api_get(f"{FABRIC_API}/deploymentPipelines", "deployment_pipelines")
    result    = []

    for dp in (pipelines if isinstance(pipelines, list) else []):
        dp_id   = dp.get("id", "")
        dp_name = dp.get("displayName", "")

        # Leer stages
        try:
            resp = requests.get(
                f"{FABRIC_API}/deploymentPipelines/{dp_id}/stages",
                headers=HEADERS, timeout=20
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
            # Ordenar por order
            stages.sort(key=lambda x: x.get("order", 0))
        except Exception as e:
            print(f"  warning  stages for '{dp_name}': {e}")
            stages = []

        result.append({
            "id":          dp_id,
            "displayName": dp_name,
            "description": dp.get("description", ""),
            "stages":      stages,
        })

    print(f"  -> {len(result)} deployment pipeline(s)")
    return result


def get_semantic_model_details(workspace_id, sm_id, sm_name):
    """
    Enriquece un semantic model con detalles de:
    - dataset completo (modo, storage, configuredBy, etc.)
    - datasources (tipo de origen, nombre del lakehouse/DW)
    - refreshSchedule
    - refresh history (ultimo refresh)
    """
    details = {
        "configuredBy":    "",
        "targetStorageMode": "",
        "createdDate":     "",
        "webUrl":          "",
        "isRefreshable":   False,
        "datasources":     [],
        "refreshSchedule": {},
        "lastRefresh":     {},
        "storageMode":     "unknown",
    }

    # 1. Dataset completo
    try:
        resp = requests.get(
            f"{POWERBI_API}/groups/{workspace_id}/datasets/{sm_id}",
            headers=HEADERS, timeout=15
        )
        if resp.status_code == 200:
            ds = resp.json()
            details["configuredBy"]     = ds.get("configuredBy", "")
            details["targetStorageMode"]= ds.get("targetStorageMode", "")
            details["createdDate"]      = ds.get("createdDate", "")
            details["webUrl"]           = ds.get("webUrl", "")
            details["isRefreshable"]    = ds.get("isRefreshable", False)
            # Determinar modo de almacenamiento
            tsm = ds.get("targetStorageMode", "").lower()
            if "premium" in tsm or "directlake" in tsm:
                details["storageMode"] = "DirectLake"
            elif "import" in tsm:
                details["storageMode"] = "Import"
            else:
                details["storageMode"] = ds.get("targetStorageMode", "")
    except Exception as e:
        print(f"  warning dataset details '{sm_name}': {e}")

    # 2. Datasources
    try:
        resp = requests.get(
            f"{POWERBI_API}/groups/{workspace_id}/datasets/{sm_id}/datasources",
            headers=HEADERS, timeout=15
        )
        if resp.status_code == 200:
            for src in resp.json().get("value", []):
                src_type = src.get("datasourceType", "")
                conn     = src.get("connectionDetails", {})
                # Resolver nombre legible del origen
                if src_type == "AzureDataLakeStorage":
                    # Extraer nombre del lakehouse desde el path de OneLake
                    path = conn.get("path", "")
                    # Path formato: /{ws_id}/{lh_id}/...
                    # Buscar nombre en project_data si esta disponible
                    lh_name = ""
                    try:
                        parts = [p for p in path.strip("/").split("/") if p]
                        lh_id = parts[1] if len(parts) > 1 else ""
                        for ws in project_data.get("workspaces", []):
                            for lh in ws.get("lakehouses", []):
                                if lh.get("id", "") == lh_id:
                                    lh_name = lh.get("name", "")
                    except Exception:
                        pass
                    details["datasources"].append({
                        "type":    "Lakehouse (OneLake)",
                        "name":    lh_name or conn.get("path", ""),
                        "server":  conn.get("server", ""),
                    })
                elif src_type in ("Sql", "AnalysisServices"):
                    details["datasources"].append({
                        "type":   "Data Warehouse (SQL)",
                        "name":   conn.get("database", "") or conn.get("server",""),
                        "server": conn.get("server", ""),
                    })
                else:
                    details["datasources"].append({
                        "type":   src_type,
                        "name":   conn.get("server", "") or conn.get("url", ""),
                        "server": conn.get("server", ""),
                    })
    except Exception as e:
        print(f"  warning datasources '{sm_name}': {e}")

    # 3. Refresh schedule
    try:
        resp = requests.get(
            f"{POWERBI_API}/groups/{workspace_id}/datasets/{sm_id}/refreshSchedule",
            headers=HEADERS, timeout=15
        )
        if resp.status_code == 200:
            rs = resp.json()
            details["refreshSchedule"] = {
                "enabled":         rs.get("enabled", False),
                "days":            rs.get("days", []),
                "times":           rs.get("times", []),
                "localTimeZoneId": rs.get("localTimeZoneId", "UTC"),
                "notifyOption":    rs.get("notifyOption", ""),
            }
    except Exception as e:
        print(f"  warning refreshSchedule '{sm_name}': {e}")

    # 4. Ultimo refresh
    try:
        resp = requests.get(
            f"{POWERBI_API}/groups/{workspace_id}/datasets/{sm_id}/refreshes?$top=1",
            headers=HEADERS, timeout=15
        )
        if resp.status_code == 200:
            refreshes = resp.json().get("value", [])
            if refreshes:
                last = refreshes[0]
                details["lastRefresh"] = {
                    "refreshType": last.get("refreshType", ""),
                    "startTime":   last.get("startTime", ""),
                    "endTime":     last.get("endTime", ""),
                    "status":      last.get("status", ""),
                }
    except Exception as e:
        print(f"  warning refresh history '{sm_name}': {e}")

    return details

print("OK CELL_4_functions cargada -- todas las funciones API disponibles")

