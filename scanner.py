import pandas as pd
import yfinance as yf

DEFAULT_TICKERS = ['SPY','QQQ','IWM','AAPL','MSFT','NVDA','AMD','TSLA','META','AMZN','GOOGL','PLTR','SOFI','COIN','HOOD','BAC','F','INTC','MU','SMCI','UBER','NFLX','AVGO','JPM','XLF','XLK','TQQQ','SQQQ','MSTR','RIVN']

def get_bars(symbol, timeframe):
    interval, period = ('1m','7d') if timeframe in ('1m','4m') else ('5m','60d')
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False, threads=False, prepost=False)
    if df is None or df.empty:
        raise ValueError('No intraday bars available')
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[['Open','High','Low','Close','Volume']].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df = df.tz_convert('America/New_York').between_time('09:30','15:59')
    if timeframe == '4m':
        df = df.resample('4min', origin='start_day', offset='9h30min', label='left', closed='left').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna().between_time('09:30','15:59')
    return df

def backtest(df, rr=1.5, risk_pct=2.0, start_cash=500.0, min_rate=70, min_trades=30):
    if len(df) < 35:
        raise ValueError('Not enough bars')
    d = df.copy()
    for span in (5,9,30):
        d[f'e{span}'] = d['Close'].ewm(span=span, adjust=False).mean()
    pos=0; sl=tp=trade_risk=0.0; balance=float(start_cash); peak=balance; max_dd=0.0
    wins=losses=call_wins=put_wins=call_total=put_total=0
    last_signal='—'; last_signal_time=None
    rows=list(d.itertuples())
    for i in range(30,len(rows)):
        b=rows[i]; p=rows[i-1]
        if pos:
            stop_hit=(b.Low<=sl) if pos==1 else (b.High>=sl)
            target_hit=(b.High>=tp) if pos==1 else (b.Low<=tp)
            if stop_hit or target_hit:
                won=target_hit and not stop_hit
                if won:
                    wins+=1; balance+=trade_risk*rr
                    if pos==1: call_wins+=1
                    else: put_wins+=1
                else:
                    losses+=1; balance-=trade_risk
                balance=max(0.0,balance); peak=max(peak,balance)
                max_dd=max(max_dd,100*(peak-balance)/peak if peak else 0)
                pos=0
        if pos or balance<=0 or b.Index.date()!=p.Index.date():
            continue
        bull=b.e5>b.e9>b.e30 and p.e5>p.e9>p.e30
        bear=b.e5<b.e9<b.e30 and p.e5<p.e9<p.e30
        eps=0.000001
        no_bottom=p.Close>p.Open and abs(p.Open-p.Low)<eps
        no_top=p.Close<p.Open and abs(p.Open-p.High)<eps
        tick=0.01
        call=no_bottom and bull and b.High>p.High and b.Close>b.Open and b.Close>p.Low+tick
        put=no_top and bear and b.Low<p.Low and b.Close<b.Open and b.Close<p.High-tick
        if call and b.Close>p.Low:
            pos=1; sl=p.Low; tp=b.Close+(b.Close-sl)*rr; call_total+=1; last_signal='CALL'; last_signal_time=b.Index.isoformat()
        elif put and b.Close<p.High:
            pos=-1; sl=p.High; tp=b.Close-(sl-b.Close)*rr; put_total+=1; last_signal='PUT'; last_signal_time=b.Index.isoformat()
        if pos:
            trade_risk=balance*risk_pct/100
    total=wins+losses
    rate=100*wins/total if total else 0
    profit=balance-start_cash
    return {'win_rate':round(rate,1),'trades':total,'wins':wins,'losses':losses,
            'call_win_rate':round(100*call_wins/(call_total-int(pos==1)),1) if call_total-int(pos==1)>0 else 0,
            'put_win_rate':round(100*put_wins/(put_total-int(pos==-1)),1) if put_total-int(pos==-1)>0 else 0,
            'balance':round(balance,2),'profit':round(profit,2),'return_pct':round(100*profit/start_cash,1),
            'max_drawdown':round(max_dd,1),'qualified':total>=min_trades and rate>=min_rate and profit>0,
            'last_signal':last_signal,'last_signal_time':last_signal_time,'open_trade':bool(pos),
            'bars':len(df),'from':df.index[0].isoformat(),'to':df.index[-1].isoformat()}
