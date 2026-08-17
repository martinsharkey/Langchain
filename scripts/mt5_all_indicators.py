"""All 37 standard MT5 built-in indicators, computed from OHLCV in Python (the MT5 Python
package does not expose iMA/iRSI/... handles, so we replicate the formulas). Returns a
dict of name -> pd.Series aligned to the input bars. Used for the BTCUSD entry-edge table.

Bars df must have columns: open, high, low, close, tick_volume (and 'volume' alias).
"""
import numpy as np
import pandas as pd

def _ema(s, n): return s.ewm(span=n, adjust=False).mean()
def _sma(s, n): return s.rolling(n).mean()

def all_indicators(df: pd.DataFrame) -> dict:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    vol = df["tick_volume"].astype(float) if "tick_volume" in df else df.get("volume", pd.Series(1.0, index=df.index))
    med = (h + l) / 2.0
    typ = (h + l + c) / 3.0
    out = {}

    # ── Trend / MAs ──
    out["MA"] = _sma(c, 14)
    out["DEMA"] = 2*_ema(c, 14) - _ema(_ema(c, 14), 14)
    e1 = _ema(c, 14); e2 = _ema(e1, 14); e3 = _ema(e2, 14)
    out["TEMA"] = 3*e1 - 3*e2 + e3
    # AMA (Kaufman)
    n = 10
    change = (c - c.shift(n)).abs()
    vola = (c - c.shift(1)).abs().rolling(n).sum()
    er = (change / vola).replace([np.inf, -np.inf], 0).fillna(0)
    fast, slow = 2/(2+1), 2/(30+1)
    sc = (er*(fast-slow)+slow)**2
    ama = c.copy().astype(float)
    cv = c.values; scv = sc.values; av = ama.values.copy()
    for i in range(1, len(cv)):
        av[i] = av[i-1] + scv[i]*(cv[i]-av[i-1]) if not np.isnan(scv[i]) else av[i-1]
    out["AMA"] = pd.Series(av, index=c.index)
    # FrAMA (fractal adaptive)
    N = 16; half = N//2
    hh1 = h.rolling(half).max(); ll1 = l.rolling(half).min()
    hh2 = h.rolling(half).max().shift(half); ll2 = l.rolling(half).min().shift(half)
    hhN = h.rolling(N).max(); llN = l.rolling(N).min()
    n1 = (hh1-ll1)/half; n2 = (hh2-ll2)/half; n3 = (hhN-llN)/N
    D = ((np.log(n1+n2) - np.log(n3)) / np.log(2)).replace([np.inf,-np.inf], np.nan)
    alpha = np.exp(-4.6*(D-1)).clip(0.01, 1)
    fr = c.copy().astype(float); av2 = fr.values.copy(); alv = alpha.values
    for i in range(1, len(cv)):
        a = alv[i] if not np.isnan(alv[i]) else 0.5
        av2[i] = a*cv[i] + (1-a)*av2[i-1]
    out["FRAMA"] = pd.Series(av2, index=c.index)
    # VIDyA (CMO-based)
    cmo_n = 9
    up = (c-c.shift(1)).clip(lower=0).rolling(cmo_n).sum()
    dn = (c.shift(1)-c).clip(lower=0).rolling(cmo_n).sum()
    cmo = ((up-dn)/(up+dn)).abs().replace([np.inf,-np.inf],0).fillna(0)
    f = 2/(12+1)
    vd = c.copy().astype(float); vv = vd.values.copy(); cmv = cmo.values
    for i in range(1, len(cv)):
        a = f*cmv[i]
        vv[i] = a*cv[i] + (1-a)*vv[i-1]
    out["VIDYA"] = pd.Series(vv, index=c.index)
    # Bollinger, Envelopes, StdDev
    m20 = _sma(c, 20); sd20 = c.rolling(20).std()
    out["BB_upper"] = m20 + 2*sd20; out["BB_lower"] = m20 - 2*sd20
    out["BB_pos"] = (c - out["BB_lower"]) / (out["BB_upper"] - out["BB_lower"])
    out["ENV_upper"] = _sma(c,14)*1.001; out["ENV_lower"] = _sma(c,14)*0.999
    out["STDDEV"] = sd20
    # Parabolic SAR
    out["SAR"] = _psar(h.values, l.values, c.index)
    # Ichimoku
    out["ICHI_tenkan"] = (h.rolling(9).max()+l.rolling(9).min())/2
    out["ICHI_kijun"]  = (h.rolling(26).max()+l.rolling(26).min())/2
    out["ICHI_spanA"]  = ((out["ICHI_tenkan"]+out["ICHI_kijun"])/2)
    out["ICHI_spanB"]  = (h.rolling(52).max()+l.rolling(52).min())/2
    # Alligator (smma 13/8/5 shifted) + Gator
    j = _smma(med,13); t = _smma(med,8); li = _smma(med,5)
    out["ALLIG_jaw"] = j.shift(8); out["ALLIG_teeth"] = t.shift(5); out["ALLIG_lips"] = li.shift(3)
    out["GATOR_upper"] = (out["ALLIG_jaw"]-out["ALLIG_teeth"]).abs()
    out["GATOR_lower"] = -(out["ALLIG_teeth"]-out["ALLIG_lips"]).abs()

    # ── Oscillators ──
    macd_line = _ema(c,12)-_ema(c,26); sig = _ema(macd_line,9)
    out["MACD"] = macd_line; out["MACD_signal"] = sig; out["MACD_hist"] = macd_line-sig
    out["OSMA"] = macd_line - sig
    out["RSI"] = _rsi(c, 14)
    out["ATR"] = _atr(h,l,c,14)
    out["CCI"] = _cci(typ, 20)
    out["MOMENTUM"] = c/c.shift(14)*100
    out["WPR"] = -100*(h.rolling(14).max()-c)/(h.rolling(14).max()-l.rolling(14).min())
    out["DEMARKER"] = _demarker(h,l,14)
    out["BULLS"] = h - _ema(c,13)
    out["BEARS"] = l - _ema(c,13)
    k = 100*(c-l.rolling(14).min())/(h.rolling(14).max()-l.rolling(14).min())
    out["STOCH_K"] = k; out["STOCH_D"] = k.rolling(3).mean()
    out["RVI"] = _rvi(o,h,l,c,10)
    tr = _ema(_ema(_ema(np.log(c),15),15),15)
    out["TRIX"] = tr.diff()*10000
    # Bill Williams momentum
    ao = _sma(med,5)-_sma(med,34)
    out["AO"] = ao
    out["AC"] = ao - _sma(ao,5)
    # ── Volumes ──
    out["VOLUME"] = vol
    out["OBV"] = (np.sign(c.diff().fillna(0))*vol).cumsum()
    clv = (((c-l)-(h-c))/(h-l)).replace([np.inf,-np.inf],0).fillna(0)
    out["AD"] = (clv*vol).cumsum()
    out["CHAIKIN"] = _ema(out["AD"],3)-_ema(out["AD"],10)
    out["MFI"] = _mfi(typ, vol, 14)
    out["BWMFI"] = (h-l)/vol.replace(0,np.nan)

    return out

def _smma(s, n):
    r = s.copy().astype(float); v = r.values.copy(); sv = s.values
    first = np.nanmean(sv[:n]) if len(sv) >= n else sv[0]
    for i in range(len(v)):
        if i < n: v[i] = first
        else: v[i] = (v[i-1]*(n-1)+sv[i])/n
    return pd.Series(v, index=s.index)

def _rsi(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1+up/dn.replace(0,np.nan))

def _atr(h,l,c,n):
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def _cci(typ, n):
    sma = typ.rolling(n).mean(); md = (typ-sma).abs().rolling(n).mean()
    return (typ-sma)/(0.015*md)

def _demarker(h,l,n):
    dem = (h-h.shift()).clip(lower=0); demin = (l.shift()-l).clip(lower=0)
    return dem.rolling(n).sum()/(dem.rolling(n).sum()+demin.rolling(n).sum())

def _rvi(o,h,l,c,n):
    num = ((c-o)+2*(c.shift(1)-o.shift(1))+2*(c.shift(2)-o.shift(2))+(c.shift(3)-o.shift(3)))/6
    den = ((h-l)+2*(h.shift(1)-l.shift(1))+2*(h.shift(2)-l.shift(2))+(h.shift(3)-l.shift(3)))/6
    return num.rolling(n).mean()/den.rolling(n).mean().replace(0,np.nan)

def _mfi(typ, vol, n):
    mf = typ*vol; pos = mf.where(typ>typ.shift(),0.0); neg = mf.where(typ<typ.shift(),0.0)
    return 100-100/(1+pos.rolling(n).sum()/neg.rolling(n).sum().replace(0,np.nan))

def _psar(h, l, idx, af0=0.02, afmax=0.2):
    n=len(h); sar=np.zeros(n); bull=True; af=af0; ep=h[0]; sar[0]=l[0]
    for i in range(1,n):
        sar[i]=sar[i-1]+af*(ep-sar[i-1])
        if bull:
            if l[i]<sar[i]: bull=False; sar[i]=ep; ep=l[i]; af=af0
            else:
                if h[i]>ep: ep=h[i]; af=min(af+af0,afmax)
        else:
            if h[i]>sar[i]: bull=True; sar[i]=ep; ep=h[i]; af=af0
            else:
                if l[i]<ep: ep=l[i]; af=min(af+af0,afmax)
    return pd.Series(sar, index=idx)
