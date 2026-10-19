"""PURGATORY No Wick PRO research engine. Stock-only, no brokerage orders.

Feed completed OHLCV bars with a timezone-aware New York index. All indicators
use past/current completed bars. Signal at bar close; enter next bar open.
Stops take precedence if stop and target touch in the same bar.
"""
from dataclasses import dataclass
import pandas as pd
import numpy as np

@dataclass(frozen=True)
class Config:
    rr: float = 2.0
    risk_pct: float = 1.0
    daily_loss_pct: float = 3.0
    max_trades_day: int = 3
    min_rvol: float = 1.2
    min_adx: float = 18.0
    wick_tolerance: float = 0.02  # fraction of candle range
    fee_per_share: float = 0.005
    slippage_bps: float = 2.0
    initial_cash: float = 500.0

def prepare(df, cfg=Config()):
    d = df.copy().sort_index()
    if not isinstance(d.index, pd.DatetimeIndex) or d.index.tz is None:
        raise ValueError("Bars need a timezone-aware DatetimeIndex")
    d = d.tz_convert("America/New_York")
    if not {"Open","High","Low","Close","Volume"}.issubset(d.columns):
        raise ValueError("OHLCV data required; volume cannot be omitted")
    d = d.dropna(subset=["Open","High","Low","Close","Volume"])
    d = d.between_time("09:30","15:59").copy()
    for n in (5,9,30):
        d[f"ema{n}"] = d.Close.ewm(span=n, adjust=False).mean()
    # Reset VWAP every session, avoiding overnight leakage.
    day = d.index.date
    typical = (d.High+d.Low+d.Close)/3
    pv = (typical*d.Volume).groupby(day).cumsum()
    vol = d.Volume.groupby(day).cumsum()
    d["vwap"] = pv / vol.replace(0,np.nan)
    d["rvol"] = d.Volume / d.Volume.shift(1).rolling(20,min_periods=20).mean()
    up = d.High.diff()
    down = -d.Low.diff()
    plus_dm = pd.Series(np.where((up>down)&(up>0),up,0.0),index=d.index)
    minus_dm = pd.Series(np.where((down>up)&(down>0),down,0.0),index=d.index)
    tr = pd.concat([d.High-d.Low,(d.High-d.Close.shift()).abs(),(d.Low-d.Close.shift()).abs()],axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    plus_di = 100*plus_dm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    minus_di = 100*minus_dm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0,np.nan)
    d["adx"] = dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    return d

def signals(d,cfg=Config()):
    out = []
    for i in range(31,len(d)-1):
        p,b = d.iloc[i-1],d.iloc[i]
        if d.index[i-1].date()!=d.index[i].date(): continue
        if not (pd.Timestamp("09:38").time() <= d.index[i].time() <= pd.Timestamp("11:30").time()): continue
        if pd.isna(b.adx) or pd.isna(b.rvol) or b.adx<cfg.min_adx or b.rvol<cfg.min_rvol: continue
        candle_range=max(p.High-p.Low,0.01)
        no_bottom=p.Close>p.Open and (p.Open-p.Low)/candle_range<=cfg.wick_tolerance
        no_top=p.Close<p.Open and (p.High-p.Open)/candle_range<=cfg.wick_tolerance
        bull=b.ema5>b.ema9>b.ema30 and b.Close>b.vwap and b.Close>b.Open
        bear=b.ema5<b.ema9<b.ema30 and b.Close<b.vwap and b.Close<b.Open
        side = 1 if no_bottom and bull and b.High>p.High and b.Close>p.High else (-1 if no_top and bear and b.Low<p.Low and b.Close<p.Low else 0)
        if side:
            out.append((i+1,side,float(p.Low if side==1 else p.High)))
    return out

def backtest(df,cfg=Config()):
    d=prepare(df,cfg)
    candidates={i:(side,stop) for i,side,stop in signals(d,cfg)}
    balance=cfg.initial_cash; peak=balance; max_dd=0.0; records=[]
    position=None; daily_pnl=0.0; daily_count=0; current_day=None
    for i in range(len(d)):
        bar=d.iloc[i]; day=d.index[i].date()
        if day!=current_day:
            # Close any overnight position at the first available open, conservatively.
            if position:
                position["exit_i"]=i; position["reason"]="session_boundary"
                position["exit_raw"]=float(bar.Open)
            current_day=day; daily_pnl=0.0; daily_count=0
        if position:
            p=position; side=p["side"]
            hit_stop=bar.Low<=p["stop"] if side==1 else bar.High>=p["stop"]
            hit_target=bar.High>=p["target"] if side==1 else bar.Low<=p["target"]
            last_bar=i==len(d)-1 or (i+1<len(d) and d.index[i+1].date()!=day)
            if "exit_raw" in p or hit_stop or hit_target or last_bar:
                raw=p.pop("exit_raw",float(p["stop"] if hit_stop else p["target"] if hit_target else bar.Close))
                reason=p.pop("reason","stop" if hit_stop else "target" if hit_target else "session_close")
                slip=raw*cfg.slippage_bps/10000
                exit_price=raw-side*slip
                pnl=(exit_price-p["entry"])*side*p["shares"]-2*cfg.fee_per_share*p["shares"]
                balance+=pnl; daily_pnl+=pnl
                records.append({"entry_time":str(d.index[p["entry_i"]]),"exit_time":str(d.index[i]),"side":"CALL" if side==1 else "PUT","entry":round(p["entry"],4),"exit":round(exit_price,4),"shares":p["shares"],"pnl":round(pnl,2),"reason":reason})
                position=None
                peak=max(peak,balance); max_dd=max(max_dd,100*(peak-balance)/peak)
            continue
        if i not in candidates or daily_count>=cfg.max_trades_day or daily_pnl<=-cfg.initial_cash*cfg.daily_loss_pct/100 or balance<=0: continue
        side,stop=candidates[i]
        raw=float(bar.Open)
        entry=raw+side*raw*cfg.slippage_bps/10000
        distance=(entry-stop)*side
        if distance<=0 or distance>float(bar.Close)*0.05: continue
        shares=int(min(balance/entry,(balance*cfg.risk_pct/100)/(distance+2*cfg.fee_per_share)))
        if shares<1: continue
        position={"entry_i":i,"side":side,"entry":entry,"stop":stop,"target":entry+side*cfg.rr*distance,"shares":shares}
        daily_count+=1
        # Same entry-bar stops/targets are not ignored: conservative stop-first.
        hit_stop=bar.Low<=stop if side==1 else bar.High>=stop
        hit_target=bar.High>=position["target"] if side==1 else bar.Low<=position["target"]
        if hit_stop or hit_target:
            raw_exit=stop if hit_stop else position["target"]
            exit_price=raw_exit-side*raw_exit*cfg.slippage_bps/10000
            pnl=(exit_price-entry)*side*shares-2*cfg.fee_per_share*shares
            balance+=pnl; daily_pnl+=pnl
            records.append({"entry_time":str(d.index[i]),"exit_time":str(d.index[i]),"side":"CALL" if side==1 else "PUT","entry":round(entry,4),"exit":round(exit_price,4),"shares":shares,"pnl":round(pnl,2),"reason":"stop" if hit_stop else "target"})
            position=None; peak=max(peak,balance); max_dd=max(max_dd,100*(peak-balance)/peak)
    wins=sum(x["pnl"]>0 for x in records)
    return {"trades":len(records),"wins":wins,"win_rate":round(100*wins/len(records),1) if records else 0,"ending_balance":round(balance,2),"net_profit":round(balance-cfg.initial_cash,2),"max_drawdown_pct":round(max_dd,2),"trade_log":records}

def walk_forward(df,cfg=Config(),train_fraction=0.7):
    """Chronological holdout, no tuning on holdout. Each segment starts with fresh cash."""
    if not 0.5<=train_fraction<=0.85: raise ValueError("train_fraction out of range")
    days=sorted(set(df.index.date))
    if len(days)<20: raise ValueError("At least 20 distinct sessions required for meaningful split")
    cut=int(len(days)*train_fraction)
    train=df[df.index.date<=days[cut-1]]
    test=df[df.index.date>=days[cut]]
    return {"train":backtest(train,cfg),"holdout":backtest(test,cfg),"train_sessions":cut,"holdout_sessions":len(days)-cut}
