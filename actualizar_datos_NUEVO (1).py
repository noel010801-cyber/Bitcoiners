"""
Version automatica: en vez de solo IMPRIMIR los datos nuevos, este script
edita el archivo index.html directamente, reemplazando los precios y betas
viejos por los nuevos. Pensado para correr solo, todos los dias, vía GitHub
Actions -- no necesita que nadie lo mire ni copie/pegue nada a mano.

Si se corre localmente (en tu computadora), hace exactamente lo mismo: busca
index.html en la misma carpeta y lo edita in-place.
"""

import subprocess, sys, re, os

def instalar_si_falta(paquete):
    try:
        __import__(paquete)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", paquete, "--quiet"])

for paquete in ["yfinance", "pandas", "statsmodels", "lxml"]:
    instalar_si_falta(paquete)

import yfinance as yf
import pandas as pd
import statsmodels.api as sm
from datetime import datetime

ARCHIVO_HTML = "index.html"

if not os.path.exists(ARCHIVO_HTML):
    print(f"ERROR: no se encontro {ARCHIVO_HTML} en esta carpeta.")
    sys.exit(1)

HOY = datetime.now().strftime("%d-%b-%Y").lower()

# ===================== PARTE 1: precios actuales =====================
TICKERS_PRECIO = {
    "mstr": "MSTR", "mara": "MARA", "xxi": "XXI", "djt": "DJT",
    "strc": "STRC", "strf": "STRF", "strk": "STRK", "strd": "STRD",
    "asst": "ASST", "sata": "SATA",
}

print("Buscando precios actuales...")
precios = {}
for key, ticker in TICKERS_PRECIO.items():
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d")
        precio = float(hist["Close"].iloc[-1])
        precios[key] = round(precio, 2)
        print(f"  {ticker:6} -> ${precios[key]}")
    except Exception as e:
        print(f"  {ticker:6} -> ERROR: {e}")

# ===================== PARTE 2: beta / R2 / retorno / drawdown =====================
TICKERS_BETA = {"mstr": "MSTR", "mara": "MARA", "xxi": "XXI", "djt": "DJT", "asst": "ASST", "strc": "STRC"}

print("\nCalculando beta y R2 (ventana de 6 meses)...")
btc = yf.download("BTC-USD", period="6mo", auto_adjust=True, progress=False)["Close"]

betas, r2s = {}, {}
for key, ticker in TICKERS_BETA.items():
    try:
        accion = yf.download(ticker, period="6mo", auto_adjust=True, progress=False)["Close"]
        df = pd.concat([accion, btc], axis=1)
        df.columns = ["accion", "btc"]
        df = df.dropna()
        returns = df.pct_change().dropna()
        X = sm.add_constant(returns["btc"])
        modelo = sm.OLS(returns["accion"], X).fit()
        betas[key] = round(float(modelo.params["btc"]), 4)
        r2s[key] = round(float(modelo.rsquared), 4)
        print(f"  {ticker:6} -> Beta={betas[key]} | R2={r2s[key]}")
    except Exception as e:
        print(f"  {ticker:6} -> ERROR: {e}")

# ===================== PARTE 3: variacion diaria (hoy vs ayer), los 10 =====================
print("\nCalculando variacion diaria (hoy vs cierre de ayer) para los 10 instrumentos...")
pct_diario = {}
for key, ticker in TICKERS_PRECIO.items():
    try:
        hist2d = yf.Ticker(ticker).history(period="5d")["Close"].dropna()
        if len(hist2d) >= 2:
            hoy_precio = float(hist2d.iloc[-1])
            ayer_precio = float(hist2d.iloc[-2])
            pct_diario[key] = round(hoy_precio/ayer_precio - 1, 4)
            print(f"  {ticker:6} -> {pct_diario[key]*100:.2f}%")
    except Exception as e:
        print(f"  {ticker:6} -> ERROR: {e}")


# ===================== PARTE 4: flujos diarios de los 5 ETFs (Farside) =====================
# Python no tiene el problema de CORS que tiene un navegador -- por eso esto que
# fallaba seguido del lado del navegador, deberia funcionar siempre desde aca.
print("\nBuscando flujos diarios de los ETFs (Farside)...")
flows_valores = {}
flows_fecha = None
try:
    tablas = pd.read_html("https://farside.co.uk/btc/", header=0)
    tabla = next((t for t in tablas if "IBIT" in t.columns and "FBTC" in t.columns), None)
    if tabla is not None:
        fila = tabla.iloc[0]  # Farside lista lo mas reciente primero
        flows_fecha = str(fila.iloc[0])
        for tk in ["IBIT","FBTC","GBTC","ARKB","BITB"]:
            if tk in tabla.columns:
                raw = str(fila[tk]).replace("(", "-").replace(")", "").replace(",", "")
                try:
                    flows_valores[tk.lower()] = float(raw)
                except ValueError:
                    pass
        print(f"  Fecha: {flows_fecha}")
        for k,v in flows_valores.items():
            print(f"  {k.upper()} -> {v}")
    else:
        print("  No se encontro la tabla de flujos en Farside.")
except Exception as e:
    print(f"  ERROR al traer flujos: {e}")


print(f"\nEditando {ARCHIVO_HTML}...")
with open(ARCHIVO_HTML, "r", encoding="utf-8") as f:
    html = f.read()

cambios = 0

# PRECIOS_RESPALDO
precios_js = ", ".join(f"{k}: {v}" for k,v in precios.items())
nuevo = f"const PRECIOS_RESPALDO = {{ {precios_js} }};"
html_nuevo, n = re.subn(r"const PRECIOS_RESPALDO = \{[^}]*\};", nuevo, html, count=1)
if n: html = html_nuevo; cambios += 1

# PRECIOS_RESPALDO_FECHA
fechas_js = ", ".join(f'{k}:"{HOY} (automatico)"' for k in precios)
nuevo = f"const PRECIOS_RESPALDO_FECHA = {{ {fechas_js} }};"
html_nuevo, n = re.subn(r"const PRECIOS_RESPALDO_FECHA = \{[^}]*\};", nuevo, html, count=1)
if n: html = html_nuevo; cambios += 1

# BETAS
betas_js = ", ".join(f"{k}: {v}" for k,v in betas.items())
nuevo = f"const BETAS = {{ {betas_js} }};"
html_nuevo, n = re.subn(r"const BETAS = \{[^}]*\};", nuevo, html, count=1)
if n: html = html_nuevo; cambios += 1

# R2_RESPALDO (dentro de renderBetaLive)
r2_js = ", ".join(f"{k}:{v}" for k,v in r2s.items())
nuevo = f"const R2_RESPALDO = {{{r2_js}}};"
html_nuevo, n = re.subn(r"const R2_RESPALDO = \{[^}]*\};", nuevo, html, count=1)
if n: html = html_nuevo; cambios += 1

# PRECIOS_PCT_RESPALDO (variacion diaria, tambien dentro de renderBetaLive)
pct_js = ", ".join(f"{k}:{v}" for k,v in pct_diario.items())
nuevo = f"const PRECIOS_PCT_RESPALDO = {{{pct_js}}};"
html_nuevo, n = re.subn(r"const PRECIOS_PCT_RESPALDO = \{[^}]*\};", nuevo, html, count=1)
if n: html = html_nuevo; cambios += 1

# FLOWS_RESPALDO (tiene llaves anidadas -- el patron de match es distinto a los anteriores)
if flows_valores and flows_fecha:
    valores_js = ", ".join(f"{k}:{v}" for k,v in flows_valores.items())
    nuevo = f'const FLOWS_RESPALDO = {{valores:{{{valores_js}}}, fecha:"{flows_fecha}"}};'
    html_nuevo, n = re.subn(r"const FLOWS_RESPALDO = \{(?:[^{}]|\{[^{}]*\})*\};", nuevo, html, count=1)
    if n: html = html_nuevo; cambios += 1

# Fecha global del nav (el "Pagina cargada" dinamico ya lo calcula JS solo, no hace falta tocarlo)

with open(ARCHIVO_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\nListo. Se actualizaron {cambios} de 6 bloques de datos en {ARCHIVO_HTML}.")
if cambios < 6:
    print("ATENCION: no se encontraron todos los bloques esperados -- revisar que el HTML no haya cambiado de estructura.")
