# RavexUtils

Monorepo de utilidades Python para diversos servicios.

## Paquetes

- **cloudflare**: Utilidades para bypass de Cloudflare
- **pumpfun**: Cliente para la API de Pump.fun
- **pumpportal**: Cliente WebSocket para PumpPortal
- **shared_lib**: Biblioteca compartida con funcionalidades comunes
- **telegram**: Utilidades para bots de Telegram

## Instalación

### Desde Git

Instala los paquetes directamente desde el repositorio:

```bash
# Usando pip
pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/cloudflare
pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/pumpfun
pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/pumpportal
pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/telegram
pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/shared_lib

# Usando uv (recomendado - más rápido)
uv pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/cloudflare
uv pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/pumpfun
uv pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/pumpportal
uv pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/telegram
uv pip install git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/shared_lib
```

### En pyproject.toml

Añade las dependencias en tu proyecto:

```toml
[project]
dependencies = [
    "cloudflare @ git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/cloudflare",
    "pumpfun @ git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/pumpfun",
    "pumpportal @ git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/pumpportal",
    "telegram @ git+https://github.com/TU-USUARIO/ravexutils.git#subdirectory=packages/telegram",
]
```

### Instalación local (desarrollo)

Para desarrollo local:

```bash
pip install -e packages/cloudflare
pip install -e packages/pumpfun
pip install -e packages/pumpportal
pip install -e packages/telegram
pip install -e packages/shared_lib
```

## Desarrollo

Este proyecto usa [uv](https://github.com/astral-sh/uv) para la gestión de dependencias.

```bash
# Instalar dependencias de desarrollo
uv sync

# Ejecutar tests
pytest packages/pumpfun/tests
```

## Requisitos

- Python >= 3.14
- uv (opcional pero recomendado)
