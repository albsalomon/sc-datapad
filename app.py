import os
import sqlite3
import json
import requests
from flask import Flask, jsonify, request, g, send_from_directory

app = Flask(__name__, static_folder="static", template_folder="templates")

DB_PATH = os.environ.get("DB_PATH", "sc_datapad.db")
REGOLITH_API = "https://api.regolith.rocks"

# ─── Base de datos ────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS minerals (
            code        TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            type        TEXT DEFAULT 'Ore',
            price_max   INTEGER DEFAULT 0,
            price_avg   INTEGER DEFAULT 0,
            tradeport   TEXT DEFAULT '—',
            system      TEXT DEFAULT '—',
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tradeports (
            code        TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            system      TEXT DEFAULT '—',
            planet      TEXT DEFAULT '—',
            faction     TEXT DEFAULT '—',
            has_refinery INTEGER DEFAULT 0,
            is_outlaw    INTEGER DEFAULT 0,
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ships (
            code        TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            manufacturer TEXT DEFAULT '—',
            role        TEXT DEFAULT '—',
            cargo_scu   INTEGER DEFAULT 0,
            crew_max    INTEGER DEFAULT 1,
            price_buy   INTEGER DEFAULT 0,
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS refinery_bonuses (
            method      TEXT PRIMARY KEY,
            bonus       TEXT DEFAULT '—',
            time_mod    TEXT DEFAULT '—',
            cost_mod    TEXT DEFAULT '—',
            description TEXT DEFAULT '',
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS api_cache (
            key         TEXT PRIMARY KEY,
            data        TEXT NOT NULL,
            cached_at   TEXT DEFAULT (datetime('now'))
        );
    """)
    db.commit()
    db.close()
    print("✓ Base de datos inicializada:", DB_PATH)

# ─── Proxy Regolith (resuelve CORS) ──────────────────────────────────────────

@app.route("/api/regolith/proxy", methods=["POST"])
def regolith_proxy():
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        return jsonify({"error": "API key requerida"}), 401

    body = request.get_json()
    if not body or "query" not in body:
        return jsonify({"error": "Query GraphQL requerida"}), 400

    try:
        resp = requests.post(
            REGOLITH_API,
            json=body,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            timeout=15
        )
        data = resp.json()

        # Si viene bien, guardar en cache y en BD
        if resp.status_code == 200 and "data" in data:
            save_to_db(data["data"])

        return jsonify(data), resp.status_code

    except requests.exceptions.ConnectionError:
        return jsonify({"error": "No se pudo conectar con api.regolith.rocks"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def save_to_db(data):
    """Persiste los datos de Regolith en SQLite."""
    db = sqlite3.connect(DB_PATH)
    try:
        lookups = data.get("lookups", {})
        uex = lookups.get("UEX", {}) if lookups else {}

        # Minerales / precios máximos
        max_prices = uex.get("maxPrices", {}) or {}
        for code, info in max_prices.items():
            if not isinstance(info, dict):
                continue
            db.execute("""
                INSERT INTO minerals (code, name, type, price_max, tradeport, system, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name, type=excluded.type,
                    price_max=excluded.price_max, tradeport=excluded.tradeport,
                    system=excluded.system, updated_at=excluded.updated_at
            """, (
                code,
                info.get("name", code),
                info.get("kind", "Ore"),
                int(info.get("price_sell") or info.get("price") or 0),
                info.get("outpost_name") or info.get("terminal_name") or "—",
                info.get("star_system_name") or "—"
            ))

        # Tradeports
        tradeports = uex.get("tradeports", {}) or {}
        for code, tp in tradeports.items():
            if not isinstance(tp, dict):
                continue
            db.execute("""
                INSERT INTO tradeports (code, name, system, planet, faction, has_refinery, is_outlaw, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name, system=excluded.system, planet=excluded.planet,
                    faction=excluded.faction, has_refinery=excluded.has_refinery,
                    is_outlaw=excluded.is_outlaw, updated_at=excluded.updated_at
            """, (
                code,
                tp.get("name", code),
                tp.get("star_system_name") or "—",
                tp.get("planet_name") or "—",
                tp.get("faction_name") or "—",
                1 if tp.get("has_refinery") else 0,
                1 if tp.get("is_outlaw_friendly") else 0
            ))

        # Naves
        ships = uex.get("ships", {}) or {}
        for code, s in ships.items():
            if not isinstance(s, dict):
                continue
            db.execute("""
                INSERT INTO ships (code, name, manufacturer, role, cargo_scu, crew_max, price_buy, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name, manufacturer=excluded.manufacturer,
                    role=excluded.role, cargo_scu=excluded.cargo_scu,
                    crew_max=excluded.crew_max, price_buy=excluded.price_buy,
                    updated_at=excluded.updated_at
            """, (
                code,
                s.get("name", code),
                s.get("manufacturer_name") or "—",
                s.get("focus") or s.get("role") or "—",
                int(s.get("scu") or 0),
                int(s.get("crew_max") or s.get("crew") or 1),
                int(s.get("price_buy") or 0)
            ))

        # Bonos de refinería
        bonuses = uex.get("refineryBonuses", {}) or {}
        for method, info in bonuses.items():
            if isinstance(info, dict):
                bonus = str(info.get("bonus_pct") or info.get("yield_bonus") or "—")
                time_mod = str(info.get("time_modifier") or "—")
                cost_mod = str(info.get("cost_modifier") or "—")
                desc = str(info.get("description") or info.get("desc") or "")
            else:
                bonus = str(info)
                time_mod = cost_mod = "—"
                desc = ""
            db.execute("""
                INSERT INTO refinery_bonuses (method, bonus, time_mod, cost_mod, description, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(method) DO UPDATE SET
                    bonus=excluded.bonus, time_mod=excluded.time_mod,
                    cost_mod=excluded.cost_mod, description=excluded.description,
                    updated_at=excluded.updated_at
            """, (method, bonus, time_mod, cost_mod, desc))

        db.commit()
        print(f"✓ DB actualizada: {len(max_prices)} minerales, {len(tradeports)} tradeports, {len(ships)} naves")
    except Exception as e:
        print("✗ Error guardando en DB:", e)
        db.rollback()
    finally:
        db.close()

# ─── API REST — leer desde BD ─────────────────────────────────────────────────

@app.route("/api/minerals")
def api_minerals():
    db = get_db()
    q = request.args.get("q", "").lower()
    type_f = request.args.get("type", "")
    sort = request.args.get("sort", "price_max")
    order = "DESC" if request.args.get("order", "desc") == "desc" else "ASC"

    allowed_sort = {"price_max", "price_avg", "name", "type", "system"}
    if sort not in allowed_sort:
        sort = "price_max"

    sql = "SELECT * FROM minerals WHERE 1=1"
    params = []
    if q:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(code) LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if type_f:
        sql += " AND type = ?"
        params.append(type_f)
    sql += f" ORDER BY {sort} {order}"

    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/tradeports")
def api_tradeports():
    db = get_db()
    q = request.args.get("q", "").lower()
    system = request.args.get("system", "")
    refinery = request.args.get("refinery", "")

    sql = "SELECT * FROM tradeports WHERE 1=1"
    params = []
    if q:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(planet) LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if system:
        sql += " AND system = ?"
        params.append(system)
    if refinery == "1":
        sql += " AND has_refinery = 1"
    sql += " ORDER BY system, name"

    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/ships")
def api_ships():
    db = get_db()
    q = request.args.get("q", "").lower()
    role = request.args.get("role", "")
    sort = request.args.get("sort", "name")
    order = "ASC" if request.args.get("order", "asc") == "asc" else "DESC"

    allowed_sort = {"name", "cargo_scu", "crew_max", "price_buy", "role"}
    if sort not in allowed_sort:
        sort = "name"

    sql = "SELECT * FROM ships WHERE 1=1"
    params = []
    if q:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(manufacturer) LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if role:
        sql += " AND role = ?"
        params.append(role)
    sql += f" ORDER BY {sort} {order}"

    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/refinery")
def api_refinery():
    db = get_db()
    rows = db.execute("SELECT * FROM refinery_bonuses ORDER BY method").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/stats")
def api_stats():
    db = get_db()
    minerals = db.execute("SELECT COUNT(*) as n, MAX(updated_at) as last FROM minerals").fetchone()
    tradeports = db.execute("SELECT COUNT(*) as n FROM tradeports").fetchone()
    ships = db.execute("SELECT COUNT(*) as n FROM ships").fetchone()
    refinery = db.execute("SELECT COUNT(*) as n FROM refinery_bonuses").fetchone()
    return jsonify({
        "minerals": minerals["n"],
        "tradeports": tradeports["n"],
        "ships": ships["n"],
        "refinery": refinery["n"],
        "last_update": minerals["last"] or "—"
    })

# ─── Servir frontend ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# ─── Arranque ─────────────────────────────────────────────────────────────────

# Inicializar DB al importar el módulo (necesario para gunicorn)
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") != "production"
    print(f"🚀 SC.DATAPAD corriendo en http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
