# Fabric Plug & Play 🔌

Infraestructura lista para desplegar en Azure con Microsoft Fabric, Automation Account, Key Vault y Log Analytics. Diseñado para ser reproducible en DEV y PROD desde el primer día.

---

## Estructura del proyecto

```
fabric-plug-and-play/
├── bicep/
│   ├── main.bicep                   # Entry point (subscription scope)
│   ├── parameters.json              # Parámetros base
│   └── modules/
│       ├── resourceGroup.bicep
│       ├── automationAccount.bicep  # Con Managed Identity
│       ├── logAnalytics.bicep
│       ├── keyVault.bicep
│       └── fabricCapacity.bicep
│
├── config/
│   ├── fabric-config.json           # Workspaces, lakehouses, schedule
│   ├── env-dev.json
│   └── env-prod.json
│
├── scripts/
│   ├── manage_fabric_capacity.py    # CLI: start / stop / scale / status
│   ├── deploy.sh                    # Despliegue desde Bash
│   └── deploy.ps1                   # Despliegue desde PowerShell
│
├── runbooks/
│   ├── fabric_start.py              # Runbook: inicia capacidad (MI)
│   └── fabric_stop.py               # Runbook: detiene capacidad (MI)
│
├── automation/
│   └── schedule.json                # Schedules + variables de Automation
│
└── README.md
```

---

## Prerrequisitos

| Herramienta         | Versión mínima |
|---------------------|----------------|
| Azure CLI           | 2.55+          |
| Bicep CLI           | 0.24+          |
| Python              | 3.10+          |
| jq (para deploy.sh) | 1.6+           |

```bash
# Instalar dependencias Python
pip install azure-identity azure-keyvault-secrets azure-mgmt-resource requests
```

---

## Configuración inicial

### 1. Rellena los archivos de entorno

Edita `config/env-dev.json` y `config/env-prod.json` con:
- `subscription_id` y `tenant_id` de tu Azure
- `client_id` del Service Principal
- `admin_email` para Fabric

### 2. Crea el Service Principal (si no tienes uno)

```bash
az ad sp create-for-rbac \
  --name "sp-fabric-plug-and-play" \
  --role "Contributor" \
  --scopes "/subscriptions/<SUBSCRIPTION_ID>"
```

Guarda el `appId` (client_id) y `password` (client_secret).

---

## Despliegue

### Bash
```bash
./scripts/deploy.sh dev
./scripts/deploy.sh prod
```

### PowerShell
```powershell
.\scripts\deploy.ps1 -Env dev
.\scripts\deploy.ps1 -Env prod
```

---

## Post-despliegue manual (una sola vez)

### 1. Asignar rol a la Managed Identity del Automation Account

```bash
AA_PRINCIPAL_ID=$(az automation account show \
  --resource-group rg-fpp-dev \
  --name aa-fpp-dev \
  --query identity.principalId -o tsv)

az role assignment create \
  --assignee "$AA_PRINCIPAL_ID" \
  --role "Contributor" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-fpp-dev"
```

### 2. Crear variables en el Automation Account

En el portal (o via CLI), crear las siguientes variables (ver `automation/schedule.json`):

| Variable | Valor |
|---|---|
| FABRIC_SUBSCRIPTION | Tu Subscription ID |
| FABRIC_RESOURCE_GROUP | `rg-fpp-dev` |
| FABRIC_CAPACITY_NAME | `fabric-fpp-dev` |
| FABRIC_ENV | `dev` |

---

## Uso del script de gestión

```bash
# Ver estado actual
python scripts/manage_fabric_capacity.py --env dev --action status

# Iniciar capacidad
python scripts/manage_fabric_capacity.py --env dev --action start

# Detener capacidad
python scripts/manage_fabric_capacity.py --env dev --action stop

# Escalar a F4
python scripts/manage_fabric_capacity.py --env dev --action scale --sku F4
```

Variables de entorno requeridas para Service Principal:
```bash
export AZURE_CLIENT_SECRET="<tu_client_secret>"
```

---

## Autenticación

| Contexto | Modo | Credencial |
|---|---|---|
| Local / CI-CD | Service Principal | `env-*.json` + `AZURE_CLIENT_SECRET` |
| Runbooks | Managed Identity | Automático — sin secrets |

---

## Próximos pasos (Fase 2 — Fabric)

- [ ] Despliegue de Workspaces (Bronze / Silver / Gold)
- [ ] Creación de Lakehouses y Data Warehouse
- [ ] Excel de control de tablas de ingesta
- [ ] Framework de logging con actividad de Fabric
- [ ] Notebooks de ingesta parametrizados

---

## Convención de nombres

| Recurso | Patrón | Ejemplo DEV |
|---|---|---|
| Resource Group | `rg-{prefix}-{env}` | `rg-fpp-dev` |
| Automation Account | `aa-{prefix}-{env}` | `aa-fpp-dev` |
| Key Vault | `kv-{prefix}-{env}` | `kv-fpp-dev` |
| Log Analytics | `law-{prefix}-{env}` | `law-fpp-dev` |
| Fabric Capacity | `fabric-{prefix}-{env}` | `fabric-fpp-dev` |
