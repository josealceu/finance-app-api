import express from 'express';
import axios from 'axios';
import Redis from 'ioredis';

const app = express();
app.use(express.json());
const redis = new Redis(process.env.REDIS_URL || 'redis://redis:6379');
const REGISTER_URL = process.env.REGISTER_URL || 'http://register-service:4000';
const REPORT_URL   = process.env.REPORT_URL   || 'http://report-service:5000';

const cacheGet = (k)=>redis.get(k).then(v=>v?JSON.parse(v):null);
const cacheSet = (k,v,ttl=60)=>redis.set(k,JSON.stringify(v),'EX',ttl);

// ---------- Cadastro ----------
app.post('/cadastrar-ganhos',  (req,res)=>handleCreate(req,res,'ganho'));
app.post('/cadastrar-gastos',  (req,res)=>handleCreate(req,res,'gasto'));

async function handleCreate(req,res,cat){
  try{
    const payload = { ...req.body, categoria:cat };
    const { data } = await axios.post(`${REGISTER_URL}/transacoes`,payload);
    // limpa caches relacionados
    await redis.del('cache:resumo-geral');
    await redis.del(`cache:cat:${cat}`);
    res.status(201).json(data);
  }catch(e){ res.status(500).json({error:'erro ao cadastrar'}); }
}

// ---------- Consultas com cache ----------
app.get('/resumo-geral', async (_req,res)=>{
  const key='cache:resumo-geral';
  const hit = await cacheGet(key);
  if(hit) return res.json(hit);
  const { data } = await axios.get(`${REPORT_URL}/resumo-geral`);
  await cacheSet(key,data);
  res.json(data);
});

// ------------- Editar pelo ID -------------
app.patch('/editar/:id', async (req,res)=>{
  const { id } = req.params;
  try{
    const { data } = await axios.put(`${REGISTER_URL}/transacoes/${id}`, req.body);
    // invalida todos os caches relevantes
    await redis.del('cache:resumo-geral');
    await redis.del('cache:cat:ganho');
    await redis.del('cache:cat:gasto');
    await redis.del('cache:tx:all:all');
    res.json({ id, message: 'Editado com sucesso', data });
  }catch(e){
    res.status(e?.response?.status||500).json({ error: e?.response?.data || 'erro ao editar' });
  }
});

app.get('/categoria/:nome', async (req,res)=>{
  const cat=req.params.nome;
  const key=`cache:cat:${cat}`;
  const hit = await cacheGet(key);
  if(hit) return res.json(hit);
  const { data } = await axios.get(`${REPORT_URL}/categoria/${cat}`);
  await cacheSet(key,data);
  res.json(data);
});

app.get('/transacoes', async (req,res)=>{
  const { mes, ano } = req.query;
  const key=`cache:tx:${mes||'all'}:${ano||'all'}`;
  const hit = await cacheGet(key);
  if(hit) return res.json(hit);
  const { data } = await axios.get(`${REPORT_URL}/transacoes`, { params:{mes,ano}});
  await cacheSet(key,data);
  res.json(data);
});

app.listen(3000, ()=>console.log('Gateway ✔  porta 3000'));
