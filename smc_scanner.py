"""PURGATORY SMC v4 historical scanner. Underlying-price simulation only."""
import numpy as np
import pandas as pd

def smc_backtest(df, min_rate=70, min_trades=30, rr=1.5, swing=5,
                 volume_mult=1.3, body_min=.60, break_atr=.15,
                 min_gap_atr=.10, cooldown=15, max_wait=20,
                 confirm_wait=3, max_hold=30, stop_buffer=.10):
    required = {"Open","High","Low","Close","Volume"}
    if not required.issubset(df.columns):
        raise ValueError("SMC requires OHLCV data, including volume")
    if len(df) < 70:
        raise ValueError("Insufficient 5-minute OHLCV bars")
    d = df.copy().sort_index().dropna(subset=list(required))
    for c in required:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=list(required))
    if len(d) < 70:
        raise ValueError("Insufficient valid OHLCV bars")
    close=d.Close.to_numpy(float); high=d.High.to_numpy(float)
    low=d.Low.to_numpy(float); op=d.Open.to_numpy(float)
    vol=d.Volume.to_numpy(float); n=len(d)
    ema9=d.Close.ewm(span=9,adjust=False).mean().to_numpy()
    ema30=d.Close.ewm(span=30,adjust=False).mean().to_numpy()
    prev=np.r_[close[0],close[:-1]]
    tr=np.maximum(high-low,np.maximum(abs(high-prev),abs(low-prev)))
    atr=pd.Series(tr).ewm(alpha=1/14,adjust=False).mean().to_numpy()
    avgvol=pd.Series(vol).rolling(20).mean().to_numpy()
    sh=sl=np.nan; sh_id=sl_id=-1; broken_h=broken_l=-1
    direction=0; last_choch=-100000; last_dir=0
    pending=0; pending_at=-1; zone=0; zone_at=-1
    ztop=zbottom=np.nan; reject_at=-1; trigger=reject_stop=np.nan
    position=0; entry=stop=target=np.nan; entry_at=-1
    outcomes=[]; chochs=0; signals=0; latest="—"; latest_time=None
    # Entry/exit at confirmed close. Stops/targets start on next candle.
    for i in range(max(30,swing*2+2),n):
        if position and i>entry_at:
            stop_hit=(low[i]<=stop if position==1 else high[i]>=stop)
            tp_hit=(high[i]>=target if position==1 else low[i]<=target)
            session_end=d.index[i].date()!=d.index[i-1].date()
            exit_now=stop_hit or tp_hit or i-entry_at>=max_hold or session_end
            if exit_now:
                exit_px=stop if stop_hit else target if tp_hit else op[i] if session_end else close[i]
                risk=abs(entry-stop)
                r=position*(exit_px-entry)/risk
                outcomes.append({"r":float(r),"side":"CALL" if position==1 else "PUT",
                                 "entry_time":d.index[entry_at].isoformat(),
                                 "exit_time":d.index[i].isoformat()})
                position=0
        # Pivot confirmed only swing bars after its center.
        p=i-swing
        if high[p]>=max(high[p-swing:p+swing+1]):
            sh=high[p]; sh_id=p
        if low[p]<=min(low[p-swing:p+swing+1]):
            sl=low[p]; sl_id=p
        break_up=np.isfinite(sh) and close[i]>sh and close[i-1]<=sh and broken_h!=sh_id
        break_dn=np.isfinite(sl) and close[i]<sl and close[i-1]>=sl and broken_l!=sl_id
        candidate=0
        if break_up:
            candidate=1 if direction==-1 else 0
            direction=1; broken_h=sh_id
        elif break_dn:
            candidate=-1 if direction==1 else 0
            direction=-1; broken_l=sl_id
        body=abs(close[i]-op[i])/max(high[i]-low[i],1e-8)
        rv=vol[i]/avgvol[i] if np.isfinite(avgvol[i]) and avgvol[i]>0 else 0
        qualified=(candidate!=0 and i-last_choch>=cooldown and
                   candidate!=last_dir and rv>=volume_mult and body>=body_min and
                   ((candidate==1 and close[i]>=sh+atr[i]*break_atr and close[i]>op[i] and close[i]>ema9[i]) or
                    (candidate==-1 and close[i]<=sl-atr[i]*break_atr and close[i]<op[i] and close[i]<ema9[i])))
        if qualified:
            chochs+=1; last_choch=i; last_dir=candidate
            pending=candidate; pending_at=i; zone=0; reject_at=-1
        if pending and i>pending_at:
            gap_up=low[i]>high[i-2] and low[i]-high[i-2]>=atr[i]*min_gap_atr
            gap_dn=high[i]<low[i-2] and low[i-2]-high[i]>=atr[i]*min_gap_atr
            if (pending==1 and gap_up) or (pending==-1 and gap_dn):
                zone=pending; zone_at=i
                ztop=low[i] if zone==1 else low[i-2]
                zbottom=high[i-2] if zone==1 else high[i]
                reject_at=-1; pending=0
            elif i-pending_at>max_wait:
                pending=0
        if zone:
            if i-zone_at>max_wait or (zone==1 and close[i]<zbottom) or (zone==-1 and close[i]>ztop):
                zone=0; reject_at=-1
            elif reject_at>=0 and i-reject_at>confirm_wait:
                zone=0; reject_at=-1
            elif i>zone_at and reject_at<0 and low[i]<=ztop and high[i]>=zbottom:
                if zone==1 and close[i]>op[i] and close[i]>ztop:
                    reject_at=i; trigger=high[i]; reject_stop=min(low[i],zbottom)-atr[i]*stop_buffer
                elif zone==-1 and close[i]<op[i] and close[i]<zbottom:
                    reject_at=i; trigger=low[i]; reject_stop=max(high[i],ztop)+atr[i]*stop_buffer
            elif reject_at>=0 and i>reject_at and position==0:
                bull=zone==1 and close[i]>trigger and close[i]>ema9[i]>ema30[i]
                bear=zone==-1 and close[i]<trigger and close[i]<ema9[i]<ema30[i]
                if bull or bear:
                    newdir=1 if bull else -1
                    if newdir*(close[i]-reject_stop)>0 and abs(close[i]-reject_stop)>1e-6:
                        position=newdir; entry=close[i]; stop=reject_stop
                        target=entry+newdir*rr*abs(entry-stop); entry_at=i
                        signals+=1; latest="CALL" if bull else "PUT"
                        latest_time=d.index[i].isoformat()
                    zone=0; reject_at=-1
    rvals=np.array([x["r"] for x in outcomes])
    wins=int(np.sum(rvals>0)); losses=int(np.sum(rvals<=0)); count=len(outcomes)
    winrate=round(100*wins/count,1) if count else 0
    gross_win=float(rvals[rvals>0].sum()) if count else 0
    gross_loss=float(-rvals[rvals<0].sum()) if count else 0
    pf=round(gross_win/gross_loss,2) if gross_loss>0 else (999 if gross_win>0 else 0)
    equity=np.r_[0,np.cumsum(rvals)] if count else np.array([0.])
    dd=float(np.max(np.maximum.accumulate(equity)-equity))
    avg=float(rvals.mean()) if count else 0
    # Conservative ranking: minimum sample, positive expectancy, profit factor and drawdown.
    qualified=count>=min_trades and winrate>=min_rate and avg>0 and pf>1
    return {"win_rate":winrate,"trades":count,"wins":wins,"losses":losses,
            "profit_factor":pf,"total_r":round(float(rvals.sum()),2),
            "avg_r":round(avg,3),"max_drawdown_r":round(dd,2),
            "qualified":qualified,"choch_signals":chochs,"entries":signals,
            "last_signal":latest,"last_signal_time":latest_time,
            "open_trade":bool(position),"bars":n,
            "from":d.index[0].isoformat(),"to":d.index[-1].isoformat(),
            "note":"Stock-price backtest; no options pricing, slippage or fees. Entry at confirmed close."}
