#!/usr/bin/env python3
# Fabric Auto-Scaling System — Capa 4: Guardian + Acción
# ========================================================
# Runbook: guardian_and_scale
# Tipo:    Python 3.8 (Azure Automation)
# Schedule: cada 5 minutos (o el intervalo configurado)
#
# Responsabilidades:
#   1. Verificar estado de la Fabric capacity
#   2. Si está pausada → resumir antes de lanzar los notebooks
#   3. Disparar el Fabric Pipeline (Capas 1+2+3) vía REST API
#   4. Esperar a que el pipeline termine (poll con timeout)
#   5. Leer decision_pending desde OneLake vía API
#   6. Ejecutar la acción (scale_up / scale_down / pause)
#   7. Actualizar decision_log con el resultado real
#   8. Marcar decision_pending como consumed=True
#
# Variables de Automation Account requeridas (encriptadas):
#   AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
#   AZURE_SUBSCRIPTION_ID, FABRIC_RESOURCE_GROUP
#   FABRIC_CAPACITY_ID, FABRIC_CAPACITY_NAME
#   FABRIC_WORKSPACE_ID, FABRIC_PIPELINE_ID
#   ONELAKE_ACCOUNT_NAME  (ej: "onelake")
#   DRY_RUN               ("true" | "false")
# ========================================================

import os
import sys
import json
import time
import uuid
import traceback
import requests
from datetime import datetime, timezone, timedelta


# ── SECCIÓN 1: Configuración ──────────────────────────────────────────────────
# Lee desde variables de Automation Account (no hay nada hardcodeado aquí).

def load_config() -> dict:
    """
    Lee todas las variables desde el entorno de Automation Account.
    Falla explícitamente si falta alguna variable obligatoria.
    """
    required = [
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_SUBSCRIPTION_ID",
        "FABRIC_RESOURCE_GROUP",
        "FABRIC_CAPACITY_ID",
        "FABRIC_WORKSPACE_ID",
        "FABRIC_PIPELINE_ID",
        "ONELAKE_ACCOUNT_NAME",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Variables de Automation Account no configuradas: {missing}\n"
            f"Configúralas en: Automation Account → Variables"
        )

    return {
        "tenant_id":           os.environ["AZURE_TENANT_ID"],
        "client_id":           os.environ["AZURE_CLIENT_ID"],
        "client_secret":       os.environ["AZURE_CLIENT_SECRET"],
        "subscription_id":     os.environ["AZURE_SUBSCRIPTION_ID"],
        "resource_group":      os.environ["FABRIC_RESOURCE_GROUP"],
        "capacity_id":         os.environ["FABRIC_CAPACITY_ID"],
        "capacity_name":       os.environ.get("FABRIC_CAPACITY_NAME", ""),
        "workspace_id":        os.environ["FABRIC_WORKSPACE_ID"],
        "pipeline_id":         os.environ["FABRIC_PIPELINE_ID"],
        "onelake_account":     os.environ["ONELAKE_ACCOUNT_NAME"],
        "lakehouse_name":      os.environ.get("FABRIC_LAKEHOUSE_NAME", "AutoScalingSystem"),

        # Tablas Delta (deben coincidir con las Capas 1-3)
        "table_decision_pending": "decision_pending",
        "table_decision_log":     "decision_log",

        # SKU ladder (debe coincidir con Capa 3)
        "sku_ladder": ["F2","F4","F8","F16","F32","F64","F128","F256","F512","F1024","F2048"],

        # Coste por hora EUR por SKU (para actualizar decision_log)
        "sku_cost_eur_per_hour": {
            "F2":0.36,"F4":0.72,"F8":1.44,"F16":2.88,"F32":5.76,
            "F64":11.52,"F128":23.04,"F256":46.08,"F512":92.16,
            "F1024":184.32,"F2048":368.64,
        },

        # Timeouts y reintentos
        "resume_wait_seconds":      120,   # espera tras resume antes de lanzar pipeline
        "pipeline_poll_interval_s": 15,    # segundos entre polls de estado del pipeline
        "pipeline_timeout_minutes": 12,    # timeout total esperando el pipeline
        "api_timeout_seconds":      20,
        "scale_action_retries":     3,     # reintentos si la acción de escalado falla
        "scale_retry_wait_seconds": 30,

        # Modo seguro
        "dry_run": os.environ.get("DRY_RUN", "false").lower() == "true",

        # Diagnóstico
        "verbose": os.environ.get("VERBOSE", "true").lower() == "true",
    }


# ── SECCIÓN 2: Autenticación ──────────────────────────────────────────────────

def get_token(config: dict, resource: str) -> str:
    """
    Obtiene Bearer token via Service Principal (client_credentials).
    resource: "https://management.azure.com/" | "https://storage.azure.com/"
              | "https://api.fabric.microsoft.com/"
    """
    url = f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/token"
    payload = {
        "grant_type":    "client_credentials",
        "client_id":     config["client_id"],
        "client_secret": config["client_secret"],
        "resource":      resource,
    }
    resp = requests.post(url, data=payload, timeout=config["api_timeout_seconds"])
    resp.raise_for_status()
    token = resp.json()["access_token"]
    if config.get("verbose"):
        print(f"✅ Token obtenido para resource: {resource.split('/')[2]}")
    return token


# ── SECCIÓN 3: Cliente Fabric Capacity REST API ───────────────────────────────

class FabricCapacityClient:
    """
    Wrapper sobre la ARM REST API de Fabric Capacity.
    Operaciones: get_state, resume, suspend, change_sku.
    """
    BASE = "https://management.azure.com"
    API  = "2023-11-01"

    def __init__(self, config: dict):
        self.config = config
        self._token_arm = None
        sub  = config["subscription_id"]
        rg   = config["resource_group"]
        cap  = config["capacity_id"]
        self._cap_url = (
            f"{self.BASE}/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.Fabric/capacities/{cap}"
        )

    def _headers(self) -> dict:
        if not self._token_arm:
            self._token_arm = get_token(self.config, "https://management.azure.com/")
        return {
            "Authorization": f"Bearer {self._token_arm}",
            "Content-Type":  "application/json",
        }

    def get_state(self) -> dict:
        """Devuelve estado actual: sku, state, provisioningState."""
        resp = requests.get(
            self._cap_url,
            headers=self._headers(),
            params={"api-version": self.API},
            timeout=self.config["api_timeout_seconds"],
        )
        resp.raise_for_status()
        data  = resp.json()
        props = data.get("properties", {})
        state = {
            "sku":                data.get("sku", {}).get("name", "unknown"),
            "state":              props.get("state", "unknown"),
            "provisioning_state": props.get("provisioningState", "unknown"),
        }
        if self.config.get("verbose"):
            print(f"📡 Estado capacity: {state}")
        return state

    def resume(self) -> bool:
        """Resume la capacity. Devuelve True si éxito."""
        if self.config["dry_run"]:
            print("🔵 DRY RUN — resume simulado.")
            return True
        resp = requests.post(
            f"{self._cap_url}/resume",
            headers=self._headers(),
            params={"api-version": self.API},
            timeout=self.config["api_timeout_seconds"],
        )
        # 200 = completado, 202 = aceptado (asíncrono)
        success = resp.status_code in (200, 202)
        if self.config.get("verbose"):
            print(f"▶️  Resume: HTTP {resp.status_code} → {'OK' if success else 'FALLO'}")
        return success

    def suspend(self) -> bool:
        """Suspende (pausa) la capacity."""
        if self.config["dry_run"]:
            print("🔵 DRY RUN — suspend simulado.")
            return True
        resp = requests.post(
            f"{self._cap_url}/suspend",
            headers=self._headers(),
            params={"api-version": self.API},
            timeout=self.config["api_timeout_seconds"],
        )
        success = resp.status_code in (200, 202)
        if self.config.get("verbose"):
            print(f"⏸️  Suspend: HTTP {resp.status_code} → {'OK' if success else 'FALLO'}")
        return success

    def change_sku(self, target_sku: str) -> bool:
        """Cambia el SKU de la capacity (scale up o down)."""
        if self.config["dry_run"]:
            print(f"🔵 DRY RUN — change_sku a {target_sku} simulado.")
            return True
        payload = {"sku": {"name": target_sku, "tier": "Fabric"}}
        resp = requests.patch(
            self._cap_url,
            headers=self._headers(),
            params={"api-version": self.API},
            json=payload,
            timeout=self.config["api_timeout_seconds"],
        )
        success = resp.status_code in (200, 202)
        if self.config.get("verbose"):
            print(f"⚙️  Change SKU → {target_sku}: HTTP {resp.status_code} "
                  f"→ {'OK' if success else 'FALLO'}")
        if not success:
            print(f"   Respuesta: {resp.text[:300]}")
        return success

    def wait_for_stable_state(self, max_wait_seconds: int = 180) -> str:
        """
        Espera hasta que provisioningState sea 'Succeeded' o 'Failed'.
        Útil después de change_sku para confirmar que el cambio completó.
        """
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            state = self.get_state()
            ps = state["provisioning_state"]
            if ps in ("Succeeded", "Failed", "Canceled"):
                return ps
            if self.config.get("verbose"):
                print(f"   Esperando estado estable... ({ps})")
            time.sleep(15)
        return "Timeout"


# ── SECCIÓN 4: Cliente Fabric Pipeline API ────────────────────────────────────

class FabricPipelineClient:
    """
    Dispara y monitoriza un Fabric Data Pipeline vía REST API.
    """
    BASE = "https://api.fabric.microsoft.com/v1"

    def __init__(self, config: dict):
        self.config      = config
        self._token_fab  = None
        self._ws         = config["workspace_id"]
        self._pipeline   = config["pipeline_id"]

    def _headers(self) -> dict:
        if not self._token_fab:
            self._token_fab = get_token(
                self.config, "https://api.fabric.microsoft.com/"
            )
        return {
            "Authorization": f"Bearer {self._token_fab}",
            "Content-Type":  "application/json",
        }

    def trigger_run(self) -> str | None:
        """
        Dispara el pipeline. Devuelve el runId o None si falla.
        """
        if self.config["dry_run"]:
            fake_id = str(uuid.uuid4())
            print(f"🔵 DRY RUN — pipeline trigger simulado. runId={fake_id}")
            return fake_id

        url  = (f"{self.BASE}/workspaces/{self._ws}"
                f"/dataPipelines/{self._pipeline}/jobs/instances"
                f"?jobType=Pipeline")
        resp = requests.post(
            url,
            headers=self._headers(),
            json={},
            timeout=self.config["api_timeout_seconds"],
        )
        if resp.status_code in (200, 202):
            # El runId viene en el header Location o en el body
            run_id = None
            if "Location" in resp.headers:
                # Extraer ID del header Location
                run_id = resp.headers["Location"].split("/")[-1].split("?")[0]
            elif resp.text:
                try:
                    run_id = resp.json().get("id")
                except Exception:
                    pass
            if self.config.get("verbose"):
                print(f"🚀 Pipeline disparado. runId={run_id}")
            return run_id
        else:
            print(f"❌ Error disparando pipeline: HTTP {resp.status_code} {resp.text[:300]}")
            return None

    def poll_until_complete(self, run_id: str) -> str:
        """
        Hace polling del estado del pipeline hasta que complete o timeout.
        Devuelve el estado final: 'Succeeded' | 'Failed' | 'Cancelled' | 'Timeout'
        """
        if self.config["dry_run"]:
            print("🔵 DRY RUN — pipeline completado (simulado).")
            return "Succeeded"

        url      = (f"{self.BASE}/workspaces/{self._ws}"
                    f"/dataPipelines/{self._pipeline}/jobs/instances/{run_id}")
        deadline = time.time() + (self.config["pipeline_timeout_minutes"] * 60)
        poll_s   = self.config["pipeline_poll_interval_s"]

        while time.time() < deadline:
            try:
                resp = requests.get(
                    url,
                    headers=self._headers(),
                    timeout=self.config["api_timeout_seconds"],
                )
                resp.raise_for_status()
                data   = resp.json()
                status = data.get("status", "Unknown")
                if self.config.get("verbose"):
                    print(f"   Pipeline status: {status}")
                if status in ("Succeeded", "Failed", "Cancelled", "Canceled"):
                    return status
            except Exception as e:
                print(f"⚠️  Error en poll pipeline: {e}")
            time.sleep(poll_s)

        print(f"⏱️  Timeout esperando pipeline ({self.config['pipeline_timeout_minutes']} min)")
        return "Timeout"


# ── SECCIÓN 5: Leer decision_pending desde OneLake ────────────────────────────

def read_decision_pending(config: dict, arm_token: str) -> dict | None:
    """
    Lee el registro más reciente no consumido de decision_pending.
    Accede a OneLake vía Azure Data Lake Storage Gen2 REST API
    (OneLake es compatible con ADLS Gen2).

    Alternativa más robusta para producción: usar la Fabric SQL Analytics
    Endpoint para hacer un SELECT directo sobre la Delta table.
    """
    # Intentar via Fabric SQL Analytics Endpoint (más fiable que ADLS directo)
    try:
        return _read_via_sql_endpoint(config, arm_token)
    except Exception as e:
        if config.get("verbose"):
            print(f"⚠️  SQL endpoint falló ({e}), intentando vía ADLS...")
        try:
            return _read_via_adls(config, arm_token)
        except Exception as e2:
            print(f"❌ No se pudo leer decision_pending: {e2}")
            return None


def _read_via_sql_endpoint(config: dict, arm_token: str) -> dict | None:
    """
    Consulta el SQL Analytics Endpoint del Lakehouse.
    Requiere que el Lakehouse tenga habilitado el endpoint SQL.
    """
    # Obtener token para Fabric API
    fab_token = get_token(config, "https://analysis.windows.net/powerbi/api")
    ws_id     = config["workspace_id"]
    lh_name   = config["lakehouse_name"]
    cap_id    = config["capacity_id"]
    table     = config["table_decision_pending"]

    # Obtener SQL connection string del Lakehouse
    list_url = f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/lakehouses"
    resp = requests.get(
        list_url,
        headers={"Authorization": f"Bearer {fab_token}"},
        timeout=config["api_timeout_seconds"],
    )
    resp.raise_for_status()
    lakehouses = resp.json().get("value", [])
    lakehouse  = next((l for l in lakehouses if l["displayName"] == lh_name), None)

    if not lakehouse:
        raise ValueError(f"Lakehouse '{lh_name}' no encontrado en workspace {ws_id}")

    sql_endpoint = lakehouse.get("properties", {}).get(
        "sqlEndpointProperties", {}
    ).get("connectionString", "")

    if not sql_endpoint:
        raise ValueError("SQL endpoint no disponible en el Lakehouse")

    # Ejecutar query via TDS (Tabular Data Stream) no está disponible directamente
    # en REST — usar Fabric REST execute query si está disponible
    # Por ahora raise para que el fallback ADLS se active
    raise NotImplementedError("SQL endpoint directo requiere ODBC/TDS driver")


def _read_via_adls(config: dict, arm_token: str) -> dict | None:
    """
    Lee el archivo _delta_log más reciente de decision_pending vía ADLS Gen2.
    Estrategia: buscar los Parquet files más recientes en la partición de la capacity.
    """
    storage_token = get_token(config, "https://storage.azure.com/")
    account       = config["onelake_account"]
    workspace_id  = config["workspace_id"]
    lakehouse     = config["lakehouse_name"]
    table         = config["table_decision_pending"]
    cap_id        = config["capacity_id"]

    # Ruta en OneLake: {workspace_id}/{lakehouse}.Lakehouse/Tables/{table}/
    base_path = (f"https://{account}.dfs.fabric.microsoft.com/"
                 f"{workspace_id}/{lakehouse}.Lakehouse/Tables/{table}/")

    headers = {
        "Authorization": f"Bearer {storage_token}",
        "x-ms-version":  "2023-11-03",
    }

    # Listar archivos Parquet en la partición de la capacity
    list_url = (f"{base_path}?resource=filesystem&recursive=true"
                f"&directory=capacity_id={cap_id}")
    resp = requests.get(
        list_url.replace("?resource=filesystem&", "?"),
        headers={**headers, "x-ms-version": "2023-11-03"},
        params={
            "resource":  "directory",
            "recursive": "true",
        },
        timeout=config["api_timeout_seconds"],
    )

    if resp.status_code == 404:
        if config.get("verbose"):
            print("ℹ️  Tabla decision_pending no existe aún → sin decisión pendiente.")
        return None

    resp.raise_for_status()
    files = resp.json().get("paths", [])
    parquet_files = [
        f["name"] for f in files
        if f["name"].endswith(".parquet") and "consumed=false" in f["name"]
    ]

    if not parquet_files:
        if config.get("verbose"):
            print("ℹ️  Sin decisiones pendientes sin consumir.")
        return None

    # Leer el Parquet más reciente
    latest_file = sorted(parquet_files)[-1]
    file_url    = f"https://{account}.dfs.fabric.microsoft.com/{latest_file}"
    file_resp   = requests.get(file_url, headers=headers,
                               timeout=config["api_timeout_seconds"])
    file_resp.raise_for_status()

    # Parsear Parquet en memoria
    import io
    try:
        import pyarrow.parquet as pq
        table_data = pq.read_table(io.BytesIO(file_resp.content))
        df         = table_data.to_pydict()
        if not df.get("run_id"):
            return None
        # Devolver el primer registro no consumido
        idx = 0
        return {k: (v[idx] if isinstance(v, list) else v) for k, v in df.items()}
    except ImportError:
        # pyarrow no disponible en este entorno de Automation
        # Fallback: el runbook no puede leer el Parquet directamente.
        # En este caso, la decisión se infiere del pipeline exitoso (NOOP seguro).
        print("⚠️  pyarrow no disponible. No se puede leer decision_pending.")
        print("   Instala pyarrow en el Automation Account environment.")
        return None


# ── SECCIÓN 6: Actualizar decision_log tras ejecución ────────────────────────

def update_decision_log_after_action(
    run_id:          str,
    action_executed: bool,
    sku_after:       str | None,
    error_msg:       str | None,
    config:          dict,
    arm_token:       str,
):
    """
    Actualiza el registro de decision_log con el resultado real de la acción.
    Usa la Fabric REST API para ejecutar un UPDATE sobre la Delta table.

    Nota: esta operación se hace vía Fabric Notebook API (trigger de un
    notebook de actualización) ya que Delta no soporta UPDATE directo via ADLS.
    En su lugar, loguea el resultado en una tabla separada update_log que
    la Capa 3 puede unir con decision_log en las consultas.
    """
    if config["dry_run"]:
        print(f"🔵 DRY RUN — decision_log update simulado para run_id={run_id}")
        return

    # Estrategia pragmática: escribir un registro en decision_log_updates
    # que los notebooks de Fabric leen con un JOIN.
    # Esto evita necesitar Spark desde Automation para hacer el UPDATE.
    storage_token = get_token(config, "https://storage.azure.com/")
    account       = config["onelake_account"]
    workspace_id  = config["workspace_id"]
    lakehouse     = config["lakehouse_name"]

    update_record = {
        "run_id":           run_id,
        "updated_at":       datetime.now(timezone.utc).isoformat(),
        "action_executed":  action_executed,
        "sku_after":        sku_after or "",
        "error_message":    error_msg or "",
        "source":           "guardian_and_scale",
    }

    # Escribir como JSON lines en OneLake (append-friendly, no requiere Spark)
    upload_path = (
        f"https://{account}.dfs.fabric.microsoft.com/"
        f"{workspace_id}/{lakehouse}.Lakehouse/Files/"
        f"decision_log_updates/{run_id}.json"
    )
    resp = requests.put(
        upload_path,
        headers={
            "Authorization": f"Bearer {storage_token}",
            "x-ms-version":  "2023-11-03",
            "x-ms-blob-type": "BlockBlob",
            "Content-Type":   "application/json",
        },
        data=json.dumps(update_record).encode("utf-8"),
        timeout=config["api_timeout_seconds"],
    )
    if resp.status_code in (200, 201):
        if config.get("verbose"):
            print(f"✅ decision_log_update escrito para run_id={run_id}")
    else:
        print(f"⚠️  No se pudo escribir decision_log_update: HTTP {resp.status_code}")


def mark_pending_consumed(run_id: str, config: dict):
    """
    Marca la decisión como consumed=True.
    Usa el mismo mecanismo de archivo JSON en Files/ para evitar Spark.
    El notebook de Fabric leerá estos marcadores y actualizará la Delta table.
    """
    if config["dry_run"]:
        return

    storage_token = get_token(config, "https://storage.azure.com/")
    account       = config["onelake_account"]
    workspace_id  = config["workspace_id"]
    lakehouse     = config["lakehouse_name"]

    marker = {
        "run_id":      run_id,
        "consumed":    True,
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    path = (
        f"https://{account}.dfs.fabric.microsoft.com/"
        f"{workspace_id}/{lakehouse}.Lakehouse/Files/"
        f"pending_consumed/{run_id}.json"
    )
    requests.put(
        path,
        headers={
            "Authorization":  f"Bearer {storage_token}",
            "x-ms-version":   "2023-11-03",
            "x-ms-blob-type": "BlockBlob",
            "Content-Type":   "application/json",
        },
        data=json.dumps(marker).encode("utf-8"),
        timeout=config["api_timeout_seconds"],
    )


# ── SECCIÓN 7: Ejecutar acción de escalado con rollback ──────────────────────

def execute_action(
    action:   str,
    decision: dict,
    client:   FabricCapacityClient,
    config:   dict,
) -> tuple[bool, str | None, str | None]:
    """
    Ejecuta la acción de escalado con reintentos y rollback si falla.
    Devuelve (success, sku_after, error_message).
    """
    sku_current = decision.get("sku_current", "unknown")
    sku_target  = decision.get("sku_target")
    retries     = config["scale_action_retries"]
    wait_s      = config["scale_retry_wait_seconds"]

    for attempt in range(1, retries + 1):
        try:
            if action == "pause":
                ok = client.suspend()
                if ok:
                    return True, None, None
                raise RuntimeError("suspend() devolvió False")

            elif action in ("scale_up", "scale_down"):
                if not sku_target:
                    return False, None, "sku_target no definido en la decisión"

                ok = client.change_sku(sku_target)
                if not ok:
                    raise RuntimeError(f"change_sku({sku_target}) devolvió False")

                # Esperar confirmación del cambio de SKU
                final_state = client.wait_for_stable_state(max_wait_seconds=180)
                if final_state == "Succeeded":
                    return True, sku_target, None
                elif final_state == "Failed":
                    # Rollback: volver al SKU anterior
                    print(f"❌ SKU change falló. Intentando rollback a {sku_current}...")
                    client.change_sku(sku_current)
                    return False, sku_current, f"SKU change falló (provisioningState=Failed)"
                else:
                    return False, None, f"Estado inesperado: {final_state}"

            elif action == "noop":
                return True, sku_current, None

            else:
                return False, None, f"Acción desconocida: {action}"

        except Exception as e:
            err = f"Intento {attempt}/{retries}: {type(e).__name__}: {e}"
            print(f"⚠️  {err}")
            if attempt < retries:
                print(f"   Reintentando en {wait_s}s...")
                time.sleep(wait_s)
            else:
                return False, None, err

    return False, None, "Máximo de reintentos alcanzado"


# ── SECCIÓN 8: Entrypoint principal ──────────────────────────────────────────

def main():
    print("=" * 60)
    print("  FABRIC AUTO-SCALING — Capa 4: Guardian + Acción")
    print(f"  Run UTC: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    config = load_config()

    try:
        cap_client      = FabricCapacityClient(config)
        pipeline_client = FabricPipelineClient(config)

        # ── 1. Estado actual de la capacity ───────────────────────────────────
        cap_state = cap_client.get_state()

        # ── 2. Resume si está pausada ─────────────────────────────────────────
        if cap_state["state"].lower() in ("paused", "suspended"):
            print(f"⏸️  Capacity pausada. Iniciando resume...")
            ok = cap_client.resume()
            if not ok:
                print("❌ No se pudo resumir la capacity. Abortando ciclo.")
                return

            print(f"⏳ Esperando {config['resume_wait_seconds']}s para que la capacity esté lista...")
            time.sleep(config["resume_wait_seconds"])

            # Verificar que está activa
            cap_state = cap_client.get_state()
            if cap_state["state"].lower() not in ("active", "succeeded"):
                print(f"❌ Capacity en estado inesperado tras resume: {cap_state['state']}")
                return

        # Verificar que no hay operación en curso (cambio de SKU previo)
        if cap_state["provisioning_state"] == "Updating":
            print("⏳ Cambio de SKU en curso. Esperando estado estable...")
            cap_client.wait_for_stable_state(max_wait_seconds=180)

        # ── 3. Disparar Fabric Pipeline (Capas 1 + 2 + 3) ────────────────────
        print("\n🚀 Disparando Fabric Pipeline...")
        run_id = pipeline_client.trigger_run()
        if not run_id:
            print("❌ No se pudo disparar el pipeline. Abortando ciclo.")
            return

        # ── 4. Esperar a que el pipeline complete ─────────────────────────────
        print(f"⏳ Esperando pipeline (timeout={config['pipeline_timeout_minutes']} min)...")
        pipeline_status = pipeline_client.poll_until_complete(run_id)
        print(f"   Pipeline finalizado con estado: {pipeline_status}")

        if pipeline_status not in ("Succeeded", "Succeeded"):
            if pipeline_status == "Timeout":
                print("⏱️  Pipeline no completó en el tiempo esperado. "
                      "La decisión del ciclo anterior se usará si existe.")
            else:
                print(f"⚠️  Pipeline en estado {pipeline_status}. Revisando decisión pendiente...")

        # ── 5. Leer decisión de la Capa 3 ────────────────────────────────────
        arm_token = get_token(config, "https://management.azure.com/")
        decision  = read_decision_pending(config, arm_token)

        if not decision:
            print("ℹ️  Sin decisión pendiente → ciclo completado sin acción.")
            return

        action    = decision.get("action", "noop")
        dec_runid = decision.get("run_id", "unknown")
        print(f"\n📋 Decisión recibida: action={action}, run_id={dec_runid}")
        print(f"   Razón: {decision.get('reason', 'N/A')}")

        # ── 6. Ejecutar acción ────────────────────────────────────────────────
        success, sku_after, error_msg = execute_action(
            action=action,
            decision=decision,
            client=cap_client,
            config=config,
        )

        if success:
            print(f"✅ Acción '{action}' ejecutada correctamente."
                  + (f" SKU → {sku_after}" if sku_after else ""))
        else:
            print(f"❌ Acción '{action}' falló: {error_msg}")

        # ── 7. Actualizar logs ────────────────────────────────────────────────
        update_decision_log_after_action(
            run_id          = dec_runid,
            action_executed = success,
            sku_after       = sku_after,
            error_msg       = error_msg,
            config          = config,
            arm_token       = arm_token,
        )
        mark_pending_consumed(dec_runid, config)

        print(f"\n✅ Ciclo completo finalizado.")
        print(f"   action={action} | success={success} | sku_after={sku_after}")

    except Exception as e:
        print(f"❌ Error crítico en guardian_and_scale: {type(e).__name__}: {e}")
        traceback.print_exc()
        # No relanzamos la excepción: Automation reintentará en el siguiente schedule.
        # Si quieres alertas, añadir aquí una llamada a un webhook/Teams/email.


# Azure Automation ejecuta el script directamente (no __main__)
main()
