import sys, json, sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sc_datapad.db")

def query_db(sql, params=()):
      try:
                db = sqlite3.connect(DB_PATH)
                db.row_factory = sqlite3.Row
                rows = db.execute(sql, params).fetchall()
                db.close()
                return [dict(r) for r in rows]
except Exception as e:
        return []

TOOLS = [
      {
                "name": "buscar_mineral",
                "description": "Busca minerales de Star Citizen 4.7 por nombre. Devuelve precio maximo, tradeport y sistema.",
                "inputSchema": {
                              "type": "object",
                              "properties": {
                                                "nombre": {"type": "string", "description": "Nombre del mineral, ej: Quantanium, Hadanite"}
                              },
                              "required": ["nombre"]
                }
      },
      {
                "name": "mejores_precios",
                "description": "Lista los minerales con mayor precio por SCU en Star Citizen 4.7",
                "inputSchema": {
                              "type": "object",
                              "properties": {
                                                "limite": {"type": "integer", "description": "Cuantos resultados mostrar, default 10"}
                              }
                }
      },
      {
                "name": "buscar_nave",
                "description": "Busca naves de Star Citizen por nombre o fabricante. Devuelve rol, cargo, tripulacion y precio.",
                "inputSchema": {
                              "type": "object",
                              "properties": {
                                                "nombre": {"type": "string", "description": "Nombre de la nave o fabricante, ej: Prospector, Aegis"}
                              },
                              "required": ["nombre"]
                }
      },
      {
                "name": "tradeports_refineria",
                "description": "Lista todos los tradeports de Star Citizen que tienen refineria, con su sistema y planeta",
                "inputSchema": {"type": "object", "properties": {}}
      },
      {
                "name": "estadisticas",
                "description": "Muestra cuantos datos hay en la base de datos de SC.DATAPAD y cuando fue la ultima sincronizacion",
                "inputSchema": {"type": "object", "properties": {}}
      }
]

def handle(name, args):
      if name == "buscar_mineral":
                q = "%" + args.get("nombre", "").lower() + "%"
                rows = query_db("SELECT * FROM minerals WHERE LOWER(name) LIKE ? ORDER BY price_max DESC", (q,))
                if not rows:
                              return "No encontrado. Abre SC.DATAPAD en http://localhost:5000 y sincroniza con tu API key de Regolith."
                          lines = [f"Minerales encontrados ({len(rows)}):"]
                for r in rows:
                              lines.append(f"  {r['name']} ({r['type']}): {r['price_max']:,} aUEC/SCU — {r['tradeport']} | {r['system']}")
                          return "\n".join(lines)

      elif name == "mejores_precios":
                n = int(args.get("limite", 10))
                rows = query_db("SELECT * FROM minerals ORDER BY price_max DESC LIMIT ?", (n,))
                if not rows:
                              return "Sin datos. Abre http://localhost:5000 y sincroniza con tu API key de Regolith."
                          lines = [f"Top {n} minerales por precio (aUEC/SCU):"]
                for i, r in enumerate(rows, 1):
                              lines.append(f"  {i}. {r['name']}: {r['price_max']:,} — {r['tradeport']} ({r['system']})")
                          return "\n".join(lines)

      elif name == "buscar_nave":
                q = "%" + args.get("nombre", "").lower() + "%"
                rows = query_db(
                    "SELECT * FROM ships WHERE LOWER(name) LIKE ? OR LOWER(manufacturer) LIKE ? ORDER BY name",
                    (q, q)
                )
                if not rows:
                              return "No encontrado. Sincroniza la BD desde http://localhost:5000"
                          lines = [f"Naves encontradas ({len(rows)}):"]
                for r in rows:
                              precio = f"{r['price_buy']:,} aUEC" if r['price_buy'] else "—"
                              lines.append(f"  {r['name']} ({r['manufacturer']}) | Rol: {r['role']} | Cargo: {r['cargo_scu']} SCU | Tripulacion: {r['crew_max']} | Precio: {precio}")
                          return "\n".join(lines)

      elif name == "tradeports_refineria":
                rows = query_db("SELECT * FROM tradeports WHERE has_refinery=1 ORDER BY system, name")
                if not rows:
                              return "Sin datos. Sincroniza desde http://localhost:5000"
                          lines = [f"Tradeports con refineria ({len(rows)}):"]
                for r in rows:
                              outlaw = " [OUTLAW]" if r['is_outlaw'] else ""
                              lines.append(f"  {r['name']} — {r['planet']} | {r['system']}{outlaw}")
                          return "\n".join(lines)

      elif name == "estadisticas":
                try:
                              db = sqlite3.connect(DB_PATH)
                              m = db.execute("SELECT COUNT(*) as n, MAX(updated_at) as last FROM minerals").fetchone()
                              s = db.execute("SELECT COUNT(*) as n FROM ships").fetchone()
                              t = db.execute("SELECT COUNT(*) as n FROM tradeports").fetchone()
                              r = db.execute("SELECT COUNT(*) as n FROM refinery_bonuses").fetchone()
                              db.close()
                              return (f"SC.DATAPAD — Estado de la base de datos:\n"
                                      f"  Minerales: {m[0]}\n"
                                      f"  Naves: {s[0]}\n"
                                      f"  Tradeports: {t[0]}\n"
                                      f"  Metodos refineria: {r[0]}\n"
                                      f"  Ultima sincronizacion: {m[1] or 'nunca — abre http://localhost:5000'}")
except Exception as e:
            return f"BD no encontrada ({e}). Ejecuta primero: python app.py"

    return f"Herramienta desconocida: {name}"

def main():
      while True:
                try:
                              line = sys.stdin.readline()
                              if not line:
                                                break
                                            req = json.loads(line.strip())
                              method = req.get("method", "")
                              rid = req.get("id")

                    if method == "initialize":
                                      resp = {
                                                            "jsonrpc": "2.0", "id": rid,
                                                            "result": {
                                                                                      "protocolVersion": "2024-11-05",
                                                                                      "capabilities": {"tools": {}},
                                                                                      "serverInfo": {"name": "sc-datapad", "version": "1.0.0"}
                                                            }
                                      }
elif method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
elif method == "tools/call":
                tool_name = req["params"]["name"]
                tool_args = req["params"].get("arguments", {})
                result = handle(tool_name, tool_args)
                resp = {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": str(result)}]}}
else:
                resp = {"jsonrpc": "2.0", "id": rid, "result": {}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
except Exception as e:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(e)}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
      main()
  
