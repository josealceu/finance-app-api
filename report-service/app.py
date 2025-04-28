from fastapi import FastAPI, Query
from sqlalchemy import create_engine, text
import redis, os, datetime as dt
from functools import wraps   

engine = create_engine(os.getenv('DB_URL'), pool_pre_ping=True)
redis_cli = redis.Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379'), decode_responses=True)
app = FastAPI()

# -------- helpers --------
CACHE_TTL = 60  # segundos

def cache(key):
    """Decorator simples que guarda o resultado no Redis **sem** quebrar a assinatura
    da função original — isso evita o erro de validação do FastAPI.
    """
    def deco(func):
        @wraps(func)                       # <- preserva assinatura 💡
        async def wrapper(*args, **kwargs):
            hit = redis_cli.get(key)
            if hit:
                return eval(hit)
            result = await func(*args, **kwargs)
            redis_cli.set(key, str(result), ex=CACHE_TTL)
            return result
        return wrapper
    return deco

# -------- endpoints --------
@app.get('/resumo-geral')
@cache('report:geral')
async def resumo_geral():
    with engine.connect() as conn:
        ganhos = conn.scalar(text("SELECT COALESCE(SUM(valor),0) FROM transactions WHERE categoria='ganho'"))
        gastos = conn.scalar(text("SELECT COALESCE(SUM(valor),0) FROM transactions WHERE categoria='gasto'"))
    saldo = (ganhos or 0) - (gastos or 0)
    return {"ganhos": ganhos or 0, "gastos": gastos or 0, "saldo": saldo}

@app.get('/categoria/{cat}')
async def por_categoria(cat:str):
    with engine.connect() as conn:
        total = conn.scalar(text("SELECT COALESCE(SUM(valor),0) FROM transactions WHERE categoria=:c"), {"c": cat})
    return {"categoria": cat, "total": total or 0}

@app.get('/transacoes')
async def lista(mes: int | None = Query(None, ge=1, le=12), ano: int | None = Query(None, ge=2000)):
    query = "SELECT * FROM transactions"
    params = {}
    if mes and ano:
        query += " WHERE MONTH(data)=:m AND YEAR(data)=:y"
        params = {"m": mes, "y": ano}
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows]