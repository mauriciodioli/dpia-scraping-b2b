"""Local SQLite request history and duplicate-dispatch protection, scoped to user."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from services.query_preparation import PreparationError


class QueryStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS queries (id TEXT PRIMARY KEY,user_id INTEGER, fingerprint TEXT, created REAL, state TEXT, payload TEXT)')
        self.path.chmod(0o600)

    def connect(self):
        connection=sqlite3.connect(self.path,timeout=10)
        connection.row_factory=sqlite3.Row
        return connection

    def reserve(self,id,user_id,body):
        digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row=connection.execute('SELECT * FROM queries WHERE id=?',(id,)).fetchone()
            if row:
                if row['user_id']!=user_id or row['fingerprint']!=digest:
                    raise PreparationError('La solicitud no coincide con la consulta original.',409)
                if row['state']=='complete':return json.loads(row['payload'])
                raise PreparationError('Esta consulta ya fue enviada. Revisá el historial; no se reenviará automáticamente.',409)
            connection.execute('INSERT INTO queries VALUES (?,?,?,?,?,?)',(id,user_id,digest,time.time(),'running','{}'))
        return None

    def finish(self,id,payload):
        with self.connect() as connection:
            connection.execute('UPDATE queries SET state=?,payload=? WHERE id=?',('complete',json.dumps(payload),id))

    def fail(self,id):
        with self.connect() as connection:
            connection.execute('UPDATE queries SET state=? WHERE id=?',('failed',id))

    def history(self,user_id,prepared):
        from services.query_sources import search_terms
        terms=search_terms(prepared['user_message']);items=[]
        with self.connect() as connection:
            records=connection.execute('SELECT payload FROM queries WHERE user_id=? AND state=? ORDER BY created DESC LIMIT 50',(user_id,'complete')).fetchall()
        for record in records:
            payload=json.loads(record['payload'])
            result=payload.get('result') or {}
            if payload.get('context_ids',{}).get('categoria_id') != prepared['ids']['categoria_id']:continue
            if result.get('context',{}).get('categoria')!=prepared['context']['categoria'] or result.get('context',{}).get('pais')!=prepared['context']['pais']:continue
            for row in result.get('items',[]):
                text=(row.get('producto','')+' '+row.get('descripcion','')).lower()
                if not terms or any(term in text for term in terms):items.append(row)
        unique={row['producto'].casefold():row for row in items}
        return list(unique.values())[:24]
