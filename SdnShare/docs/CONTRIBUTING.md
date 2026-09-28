# Guía de Contribución

## Branch Strategy

```
main                          ← producción estable
├── feature/infra/...         ← cambios en infra/
├── feature/pipeline/...      ← cambios en pipeline/
├── feature/ml/...            ← cambios en ml/
└── fix/...                   ← correcciones
```

**Formato:** `feature/{modulo}/{descripcion}` o `fix/{descripcion}`

## Reglas de PR

- Todo PR debe pasar `make test` en CI
- PRs en `pipeline/schemas.py` requieren aprobación de **2+ personas**
- Incluir descripción de **qué** cambia y **por qué**

## Captura de Datos

Cada sesión de captura debe generar un `run_id` único:

```bash
# Generar run_id y crear directorio
python3 scripts/generate_run_id.py --create-dir

# El directorio data/raw/{run_id}/ se crea con metadata.json
# EDITAR metadata.json con los parámetros del experimento ANTES de capturar
```

> ⚠️ **Nunca commitear archivos en `data/`** — el `.gitignore` ya los excluye.

## Dependencias

```bash
# Instalar core
pip install -e .

# Instalar con ML
pip install -e ".[ml]"

# Instalar todo (dev + ml + notebooks)
pip install -e ".[all]"
```

## Estructura de Commits

```
tipo(módulo): descripción corta

feat(pipeline): agregar feature extraction de TCP flags
fix(infra): corregir topología spine-leaf con 4 hosts
docs(ml): documentar hiperparámetros del experimento 001
```
