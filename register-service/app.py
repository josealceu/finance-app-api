from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import redis, os, uuid, datetime as dt

DB_URL = os.getenv('DB_URL')
engine = create_engine(DB_URL, pool_pre_ping=True)
redis_cli = redis.Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379'), decode_responses=True)

app = FastAPI()

class TransIn(BaseModel):
    valor: float = Field(gt=0)
    categoria: str
    data: str   # yyyy-mm-dd
    descricao: str | None = ""
    status: str = "Pago"

class TransOut(TransIn):
    id: str

# -------------- CREATE ----------------
@app.post('/transacoes', response_model=TransOut)
async def add(t: TransIn):
    tid = str(uuid.uuid4())
    _persist_mysql(tid, t)
    _index_redis(tid, t)
    return t.model_dump() | {"id": tid}

# -------------- UPDATE ----------------
@app.put('/transacoes/{tid}', response_model=TransOut)
async def edit(tid: str = Path(..., title="ID da transação"), t: TransIn | None = None):
    # 1. checa existência
    with engine.connect() as conn:
        exists = conn.scalar(text("SELECT COUNT(*) FROM transactions WHERE id=:id"), {"id": tid})
    if not exists:
        raise HTTPException(404, 'Transação não encontrada')

    # 2. atualiza MySQL
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE transactions SET valor=:v,categoria=:c,data=:d,descricao=:desc,status=:s WHERE id=:id
            """),
            {"id": tid, "v": t.valor, "c": t.categoria, "d": t.data, "desc": t.descricao, "s": t.status})
    except SQLAlchemyError:
        raise HTTPException(500, 'DB error')

    # 3. atualiza Redis
    timestamp = int(dt.date.fromisoformat(t.data).strftime('%s'))
    pipe = redis_cli.pipeline()
    pipe.hset(f'txn:{tid}', mapping=t.model_dump())
    pipe.zadd('idx:data', {tid: timestamp})
    # remove de categorias antigas (simples: brute-force)
    pipe.srem('idx:cat:ganho', tid)
    pipe.srem('idx:cat:gasto', tid)
    pipe.sadd(f'idx:cat:{t.categoria}', tid)
    pipe.execute()
    return t.model_dump() | {"id": tid}

# ---------- utilidades internas ----------

def _persist_mysql(tid: str, t: TransIn):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS transactions (
                  id CHAR(36) PRIMARY KEY,
                  valor DECIMAL(10,2) NOT NULL,
                  categoria ENUM('ganho','gasto') NOT NULL,
                  data DATE NOT NULL,
                  descricao VARCHAR(255),
                  status ENUM('Pago','Pendente','Atrasado')
                )"""))
            conn.execute(text("""
                INSERT INTO transactions(id,valor,categoria,data,descricao,status)
                VALUES (:id,:v,:c,:d,:desc,:s)
            """),
            dict(id=tid, v=t.valor, c=t.categoria, d=t.data, desc=t.descricao, s=t.status))
    except SQLAlchemyError:
        raise HTTPException(500, 'DB error')

def _index_redis(tid:str, t: TransIn):
    timestamp = int(dt.date.fromisoformat(t.data).strftime('%s'))
    redis_cli.hset(f'txn:{tid}', mapping=t.model_dump())
    redis_cli.zadd('idx:data', {tid: timestamp})
    redis_cli.sadd(f'idx:cat:{t.categoria}', tid)