# ⬡ SC.DATAPAD — Star Citizen Alpha 4.7

Alternativa a Regolith con base de datos propia. Sincroniza datos de minerales, tradeports, naves y refinería desde la API de Regolith (UEX Corp) y los guarda en SQLite.

## Estructura

```
sc-datapad/
├── app.py              # Backend Flask + proxy Regolith + API REST
├── static/
│   └── index.html      # Frontend completo
├── requirements.txt
├── Procfile            # Para Railway
├── render.yaml         # Para Render.com
└── railway.json        # Para Railway
```

## Ejecutar localmente

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

## Despliegue en Railway (gratis, recomendado)

1. Crea una cuenta en https://railway.app
2. Crea un nuevo proyecto → "Deploy from GitHub repo"
3. Sube este código a un repo de GitHub (ver instrucciones abajo)
4. Railway detecta automáticamente Python y despliega
5. Tu app estará en: https://sc-datapad-xxxx.up.railway.app

## Despliegue en Render.com (alternativa gratuita)

1. Crea cuenta en https://render.com
2. "New Web Service" → conecta tu repo de GitHub
3. Render detecta `render.yaml` automáticamente
4. El disco persistente guarda la base de datos entre deploys

## Subir a GitHub (primera vez)

```bash
git init
git add .
git commit -m "SC.DATAPAD inicial"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/sc-datapad.git
git push -u origin main
```

## Variables de entorno

| Variable    | Default              | Descripción                  |
|-------------|----------------------|------------------------------|
| PORT        | 5000                 | Puerto del servidor          |
| DB_PATH     | sc_datapad.db        | Ruta del archivo SQLite      |
| FLASK_ENV   | production           | Entorno Flask                |

## API endpoints

| Endpoint                  | Descripción                          |
|---------------------------|--------------------------------------|
| GET /api/minerals         | Lista minerales con precios          |
| GET /api/tradeports       | Lista tradeports                     |
| GET /api/ships            | Lista naves                          |
| GET /api/refinery         | Bonos de refinería                   |
| GET /api/stats            | Estadísticas de la BD                |
| POST /api/regolith/proxy  | Proxy hacia api.regolith.rocks       |
