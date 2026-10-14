import os, re, json, sqlite3, asyncio, logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
DB_PATH=os.getenv("PHENOM_DB_PATH","phenom.db")
COINS={
 "bitcoin":("Bitcoin","BTC"),"ethereum":("Ethereum","ETH"),"solana":("Solana","SOL"),
 "ripple":("XRP","XRP"),"dogecoin":("Dogecoin","DOGE"),"avalanche-2":("Avalanche","AVAX"),
 "cardano":("Cardano","ADA"),"chainlink":("Chainlink","LINK"),"the-open-network":("Toncoin","TON")
}
POS_WORDS={"approve","approved","partnership","launch","launched","integration","adoption","growth","record","surge","bullish","buyback","upgrade","mainnet","etf","inflow","beats","beat","profit"}
NEG_WORDS={"hack","hacked","exploit","lawsuit","investigation","secures? breach","outage","suspended","delist","delisted","fraud","scam","bearish","dump","liquidation","bankrupt","resign","reject","rejected","breach","stolen","loss","losses"}

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, asset TEXT, source TEXT,
          event_type TEXT, score REAL, details TEXT)""")
        con.commit()

def log_event(asset, source, event_type, score, details):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO events(ts,asset,source,event_type,score,details) VALUES(?,?,?,?,?,?)",
          (datetime.now(timezone.utc).isoformat(),asset,source,event_type,score,json.dumps(details)[:8000]))
        con.commit()

def keyword_sentiment(text):
    words=set(re.findall(r"[a-zA-Z]+", (text or "").lower()))
    pos=sum(1 for w in POS_WORDS if w in words)
    neg=sum(1 for w in NEG_WORDS if w in words)
    total=pos+neg
    return (pos-neg)/total if total else 0.0

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app=FastAPI(title="Phenom Crypto AI API",version="0.2.0",lifespan=lifespan)
from pathlib import Path

if Path("static").is_dir():
    app.mount(
        "/static",
        StaticFiles(directory="static"),
        name="static"
    )

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/api/health")
def health():
    return {
      "status":"ok",
      "time_utc":datetime.now(timezone.utc).isoformat(),
      "x_configured":bool(os.getenv("X_BEARER_TOKEN")),
      "alpaca_configured":bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET")),
      "market_source":"CoinGecko public API",
      "trading":"disabled"
    }

@app.get("/api/market/crypto")
async def crypto_market():
    ids=",".join(COINS.keys())
    url="https://api.coingecko.com/api/v3/coins/markets"
    params={"vs_currency":"usd","ids":ids,"price_change_percentage":"1h,24h,7d,30d","per_page":100,"page":1}
    async with httpx.AsyncClient(timeout=15) as client:
        r=await client.get(url,params=params,headers={"accept":"application/json"})
    if r.status_code != 200:
        raise HTTPException(502,f"Proveedor de datos cripto respondió {r.status_code}; inténtalo más tarde.")
    out=[]
    for d in r.json():
        p24=d.get("price_change_percentage_24h")
        p7=d.get("price_change_percentage_7d_in_currency")
        p30=d.get("price_change_percentage_30d_in_currency")
        if p7 is None: p7=d.get("price_change_percentage_7d")
        if p30 is None: p30=d.get("price_change_percentage_30d")
        out.append({
          "id":d["id"],"name":d["name"],"symbol":d["symbol"].upper(),
          "price_usd":d.get("current_price"),"market_cap":d.get("market_cap"),
          "volume_24h":d.get("total_volume"),"change_1h":d.get("price_change_percentage_1h_in_currency"),
          "change_24h":p24,"change_7d":p7,"change_30d":p30,
          "updated_at":d.get("last_updated"),"source":"CoinGecko"
        })
    return {"as_of_utc":datetime.now(timezone.utc).isoformat(),"data":out}

@app.get("/api/news/x")
async def x_news(query: str = "bitcoin OR crypto OR altcoin OR memecoin", limit: int = 20):
    token=os.getenv("X_BEARER_TOKEN")
    if not token:
        raise HTTPException(424,"X no está conectado. Añade X_BEARER_TOKEN en el servidor; nunca lo pongas en el HTML.")
    limit=max(10,min(limit,100))
    params={"query":query+" -is:retweet","max_results":limit,
            "tweet.fields":"created_at,public_metrics,lang,author_id,context_annotations",
            "expansions":"author_id","user.fields":"name,username,verified,public_metrics"}
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.get("https://api.x.com/2/tweets/search/recent",params=params,
            headers={"Authorization":f"Bearer {token}"})
    if r.status_code != 200:
        raise HTTPException(r.status_code if r.status_code < 500 else 502,
            f"X API no disponible ({r.status_code}). Revisa permisos, cuota y credenciales.")
    payload=r.json()
    users={u["id"]:u for u in payload.get("includes",{}).get("users",[])}
    items=[]
    for post in payload.get("data",[]):
        user=users.get(post.get("author_id"),{})
        text=post.get("text","")
        sent=keyword_sentiment(text)
        metrics=post.get("public_metrics",{})
        items.append({
          "id":post["id"],"text":text,"created_at":post.get("created_at"),
          "author":user.get("name","Unknown"),"username":user.get("username",""),
          "verified":user.get("verified",False),"followers":user.get("public_metrics",{}).get("followers_count"),
          "likes":metrics.get("like_count",0),"reposts":metrics.get("retweet_count",0),
          "url":f"https://x.com/{user.get('username','i')}/status/{post['id']}",
          "sentiment_heuristic":sent,"sentiment_note":"Puntuación por palabras clave; no es análisis semántico validado."
        })
    log_event("market","X","social_scan",0,{"query":query,"count":len(items)})
    return {"as_of_utc":datetime.now(timezone.utc).isoformat(),"source":"X API v2 recent search","data":items}

@app.get("/api/stocks")
async def stocks(symbols: str = "AAPL,MSFT,NVDA,TSLA,COIN"):
    key=os.getenv("ALPACA_API_KEY"); secret=os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        raise HTTPException(424,"Datos de acciones no conectados. Configura credenciales de datos de Alpaca en el servidor.")
    syms=",".join(s.strip().upper() for s in symbols.split(",") if s.strip())[:300]
    url="https://data.alpaca.markets/v2/stocks/snapshots"
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.get(url,params={"symbols":syms,"feed":"iex"},
          headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret})
    if r.status_code != 200:
        raise HTTPException(502,f"Proveedor de acciones respondió {r.status_code}; revisa el plan y las claves.")
    data=r.json(); out=[]
    for sym,snap in data.items():
        trade=snap.get("latestTrade") or {}
        prev=(snap.get("prevDailyBar") or {}).get("c")
        price=trade.get("p")
        out.append({"symbol":sym,"price":price,"previous_close":prev,
          "change_pct":((price/prev-1)*100 if price and prev else None),
          "timestamp":trade.get("t"),"source":"Alpaca IEX"})
    return {"as_of_utc":datetime.now(timezone.utc).isoformat(),"data":out}

class RiskPlan(BaseModel):
    asset: str
    entry_price: float
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    capital_usd: float = 100.0
    max_risk_pct: float = 1.0

@app.post("/api/risk/plan")
def risk_plan(p: RiskPlan):
    if p.entry_price <= 0 or p.capital_usd <= 0:
        raise HTTPException(400,"El precio de entrada y el capital deben ser positivos.")
    if not (0.1 <= p.stop_loss_pct <= 50 and 0.1 <= p.take_profit_pct <= 100):
        raise HTTPException(400,"Los porcentajes de stop-loss/take-profit están fuera del rango permitido.")
    if not (0.1 <= p.max_risk_pct <= 5):
        raise HTTPException(400,"El riesgo por operación debe estar entre 0.1% y 5% para este prototipo.")
    stop=p.entry_price*(1-p.stop_loss_pct/100)
    take=p.entry_price*(1+p.take_profit_pct/100)
    risk_budget=p.capital_usd*p.max_risk_pct/100
    position_size=min(p.capital_usd,risk_budget/(p.stop_loss_pct/100))
    return {"asset":p.asset,"entry_reference":p.entry_price,"stop_loss":stop,"take_profit":take,
      "capital_available":p.capital_usd,"risk_budget_usd":risk_budget,
      "suggested_position_usd":position_size,
      "reward_risk_ratio":p.take_profit_pct/p.stop_loss_pct,
      "note":"Plan ilustrativo. Stops pueden ejecutarse peor que el precio fijado por gaps, slippage o falta de liquidez. No se envían órdenes."}

@app.get("/api/events")
def events(limit:int=30):
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory=sqlite3.Row
        rows=con.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?",(max(1,min(limit,100)),)).fetchall()
    return {"data":[dict(r) for r in rows]}

@app.get("/api/config")
def config():
    return {"x_connected":bool(os.getenv("X_BEARER_TOKEN")),
            "stocks_connected":bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET")),
            "real_orders_enabled":False,
            "message":"Este prototipo no ejecuta operaciones reales."}
