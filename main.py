import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()
DB_URL = os.environ.get("DATABASE_URL", "")

def conn():
    url = DB_URL.replace("postgres://", "postgresql://", 1) if DB_URL.startswith("postgres://") else DB_URL
    return psycopg2.connect(url, cursor_factory=RealDictCursor)

@app.on_event("startup")
def startup():
    if not DB_URL:
        print("AVISO: DATABASE_URL nao definida"); return
    try:
        c = conn(); cur = c.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS funcionarios (id SERIAL PRIMARY KEY, nome TEXT NOT NULL, cargo TEXT DEFAULT \'\', tipo TEXT DEFAULT \'mensal\', salario NUMERIC(12,2) DEFAULT 0, criado_em TIMESTAMP DEFAULT NOW())")
        cur.execute("CREATE TABLE IF NOT EXISTS gastos (id SERIAL PRIMARY KEY, data DATE NOT NULL, cat TEXT NOT NULL, ipi_sub TEXT DEFAULT \'\', valor NUMERIC(12,2) NOT NULL, func_id INTEGER REFERENCES funcionarios(id) ON DELETE SET NULL, descricao TEXT DEFAULT \'\', observacao TEXT DEFAULT \'\', criado_em TIMESTAMP DEFAULT NOW())")
        cur.execute("CREATE TABLE IF NOT EXISTS ipi_cats (id SERIAL PRIMARY KEY, nome TEXT UNIQUE NOT NULL)")
        cur.execute("SELECT COUNT(*) as n FROM ipi_cats")
        if cur.fetchone()["n"] == 0:
            for nome in ["Material de Limpeza","EPI","Sinalizacao","Manutencao","Outros IPI"]:
                cur.execute("INSERT INTO ipi_cats(nome) VALUES(%s) ON CONFLICT DO NOTHING",(nome,))
        c.commit(); cur.close(); c.close(); print("DB OK")
    except Exception as e:
        print("DB ERRO:", e)

class FuncionarioIn(BaseModel):
    nome: str
    cargo: Optional[str] = ""
    tipo: Optional[str] = "mensal"
    salario: Optional[float] = 0.0

class GastoIn(BaseModel):
    data: str
    cat: str
    ipi_sub: Optional[str] = ""
    valor: float
    func_id: Optional[int] = None
    descricao: Optional[str] = ""
    observacao: Optional[str] = ""

class IpiCatIn(BaseModel):
    nome: str

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/funcionarios")
def get_funcionarios():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM funcionarios ORDER BY nome")
    r = [dict(x) for x in cur.fetchall()]
    cur.close(); c.close(); return r

@app.post("/api/funcionarios")
def post_funcionario(b: FuncionarioIn):
    c = conn(); cur = c.cursor()
    cur.execute("INSERT INTO funcionarios(nome,cargo,tipo,salario) VALUES(%s,%s,%s,%s) RETURNING *",(b.nome.strip(),b.cargo or "",b.tipo or "mensal",b.salario or 0))
    r = dict(cur.fetchone()); c.commit(); cur.close(); c.close(); return r

@app.delete("/api/funcionarios/{fid}")
def del_funcionario(fid: int):
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE gastos SET func_id=NULL WHERE func_id=%s",(fid,))
    cur.execute("DELETE FROM funcionarios WHERE id=%s",(fid,))
    c.commit(); cur.close(); c.close(); return {"ok":True}

@app.get("/api/gastos")
def get_gastos(de:Optional[str]=None,ate:Optional[str]=None,cat:Optional[str]=None,func_id:Optional[int]=None):
    c = conn(); cur = c.cursor()
    q = "SELECT g.*,f.nome as func_nome FROM gastos g LEFT JOIN funcionarios f ON g.func_id=f.id WHERE 1=1"
    p = []
    if de: q+=" AND g.data>=%s"; p.append(de)
    if ate: q+=" AND g.data<=%s"; p.append(ate)
    if cat: q+=" AND g.cat=%s"; p.append(cat)
    if func_id: q+=" AND g.func_id=%s"; p.append(func_id)
    q+=" ORDER BY g.data DESC, g.criado_em DESC"
    cur.execute(q,p)
    rows=[]
    for x in cur.fetchall():
        d=dict(x); d["data"]=str(d["data"]); d["valor"]=float(d["valor"]); rows.append(d)
    cur.close(); c.close(); return rows

@app.post("/api/gastos")
def post_gasto(b: GastoIn):
    c = conn(); cur = c.cursor()
    cur.execute("INSERT INTO gastos(data,cat,ipi_sub,valor,func_id,descricao,observacao) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",(b.data,b.cat,b.ipi_sub or "",b.valor,b.func_id,b.descricao or "",b.observacao or ""))
    d=dict(cur.fetchone()); c.commit(); cur.close(); c.close()
    d["data"]=str(d["data"]); d["valor"]=float(d["valor"]); return d

@app.delete("/api/gastos/{gid}")
def del_gasto(gid: int):
    c = conn(); cur = c.cursor()
    cur.execute("DELETE FROM gastos WHERE id=%s",(gid,))
    c.commit(); cur.close(); c.close(); return {"ok":True}

@app.get("/api/ipi-cats")
def get_ipi_cats():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM ipi_cats ORDER BY nome")
    r=[dict(x) for x in cur.fetchall()]
    cur.close(); c.close(); return r

@app.post("/api/ipi-cats")
def post_ipi_cat(b: IpiCatIn):
    c = conn(); cur = c.cursor()
    try:
        cur.execute("INSERT INTO ipi_cats(nome) VALUES(%s) RETURNING *",(b.nome.strip(),))
        r=dict(cur.fetchone()); c.commit()
    except psycopg2.errors.UniqueViolation:
        c.rollback(); raise HTTPException(400,"Categoria ja existe")
    finally:
        cur.close(); c.close()
    return r

@app.delete("/api/ipi-cats/{cid}")
def del_ipi_cat(cid: int):
    c = conn(); cur = c.cursor()
    cur.execute("DELETE FROM ipi_cats WHERE id=%s",(cid,))
    c.commit(); cur.close(); c.close(); return {"ok":True}

@app.get("/", response_class=HTMLResponse)
def index():
    return open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8").read()
