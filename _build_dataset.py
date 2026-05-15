"""
Gera o dataset histórico S&P 500 para a Calculadora 4 (LFC).
Output: data/sp500.js (servido via jsDelivr CDN)

FONTES:
  - Shiller XLS (Yale): Price + Dividend desde 1871
  - FRED CPIAUCNS (BLS): CPI oficial, atualizado mensalmente desde 1913
  - Yahoo ^SP500TR: S&P 500 Total Return Index oficial, para meses pós-Sep 2023
  - Datahub mirror: prices recentes (fallback para meses pós-Shiller)

USO LOCAL:
    pip install -r requirements.txt
    python _build_dataset.py

AUTOMAÇÃO:
  GitHub Actions corre este script no dia 1 de cada mês (cron 06:00 UTC).
  Output commited para data/sp500.js; jsDelivr serve a partir dali com cache CDN.

URL do CDN:
  https://cdn.jsdelivr.net/gh/GaMa96/lfc-sp500-data@main/data/sp500.js
"""
import csv
import datetime
import json
import os
import sys
import urllib.request
import xlrd

SHILLER_XLS_URL = 'http://www.econ.yale.edu/~shiller/data/ie_data.xls'
DATAHUB_URL     = 'https://datahub.io/core/s-and-p-500/r/data.csv'
FRED_URL        = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS'
YAHOO_URL       = 'https://query1.finance.yahoo.com/v8/finance/chart/%5ESP500TR?interval=1mo&period1=1693526400&period2=9999999999'

START_YM        = '1871-01'
SHILLER_LAST_YM = '2023-09'  # último mês com Shiller "Real Total Return Price" completo

# ─────────────────────────────────────────────────────────────────────────
# FLAG DE METODOLOGIA — facilmente reversível
# ─────────────────────────────────────────────────────────────────────────
# True (atual): para meses pós-Set 2023, usa Yahoo ^SP500TR (S&P actual TR
#               Index, daily compounding com dividendos reais).
#               PRO: valores correspondem à realidade do S&P 500.
#               CON: ~9% diferença vs ofdollarsanddata.com (cache estático).
#
# False:        usa fórmula calculada (P[t] + D[t-1]/12) / P[t-1] com
#               forward-fill do último dividend Shiller (~$68.71/ano).
#               PRO: ~1-2% diff vs ofdollarsanddata.com.
#               CON: dividendos artificialmente congelados em 2023.
USE_YAHOO_OVERRIDE = True


def fetch(url, target_path):
    print(f'Downloading: {url}')
    urllib.request.urlretrieve(url, target_path)
    print(f'  -> saved to {target_path}')


def fraction_to_ym(frac):
    """Shiller usa formato decimal: 1871.01, 1871.02, ..., 1871.12."""
    year = int(frac)
    month = int(round((frac - year) * 100))
    if month < 1 or month > 12:
        return None
    return f'{year:04d}-{month:02d}'


def parse_shiller_xls(path):
    """Devolve dict {ym: {p, d, cpi}} do XLS oficial Shiller."""
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_name('Data')
    out = {}
    for r in range(8, sheet.nrows):
        vals = sheet.row_values(r)
        if vals[0] == '' or vals[1] == '':
            continue
        try:
            ym = fraction_to_ym(float(vals[0]))
            if ym is None or ym < START_YM:
                continue
            p   = float(vals[1])
            d   = float(vals[2]) if vals[2] not in ('', None) else 0
            cpi = float(vals[4]) if vals[4] not in ('', None) else 0
        except (ValueError, TypeError):
            continue
        out[ym] = {'p': p, 'd': d, 'cpi': cpi}
    return out


def parse_datahub(path):
    """Devolve dict {ym: p} do mirror datahub (para meses pós-Shiller)."""
    out = {}
    with open(path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            ym = r['Date'][:7]
            try:
                p = float(r['SP500'])
            except (ValueError, KeyError):
                continue
            if p > 0:
                out[ym] = p
    return out


def parse_fred(path):
    """Devolve dict {ym: cpi} do FRED CPIAUCNS."""
    out = {}
    with open(path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) < 2:
                continue
            date, val = row[0], row[1]
            if not val or val == '.':
                continue
            try:
                out[date[:7]] = float(val)
            except ValueError:
                continue
    return out


def fetch_yahoo_sp500tr():
    """Devolve dict {ym: close_eom} do Yahoo Finance ^SP500TR (S&P 500
    Total Return Index oficial, daily compounding)."""
    import datetime as _dt
    req = urllib.request.Request(YAHOO_URL, headers={'User-Agent': 'Mozilla/5.0'})
    print(f'Downloading: {YAHOO_URL[:80]}...')
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode('utf-8'))
    result = data['chart']['result'][0]
    timestamps = result['timestamp']
    closes = result['indicators']['quote'][0]['close']
    out = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        dt = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc)
        ym = f'{dt.year:04d}-{dt.month:02d}'
        out[ym] = float(close)
    print(f'  -> {len(out)} meses do Yahoo ({min(out)} a {max(out)})')
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    shiller_xls = os.path.join(here, 'ie_data.xls')
    datahub_csv = os.path.join(here, 'datahub-tmp.csv')
    fred_csv    = os.path.join(here, 'fred-cpi-tmp.csv')
    output_dir  = os.path.join(here, 'data')
    output      = os.path.join(output_dir, 'sp500.js')

    os.makedirs(output_dir, exist_ok=True)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # 1. Downloads
    fetch(SHILLER_XLS_URL, shiller_xls)
    fetch(DATAHUB_URL,     datahub_csv)
    fetch(FRED_URL,        fred_csv)

    # 2. Parse
    shiller = parse_shiller_xls(shiller_xls)
    datahub_p = parse_datahub(datahub_csv)
    fred_cpi = parse_fred(fred_csv)

    print(f'\nShiller XLS: {len(shiller)} meses ({min(shiller)} -> {max(shiller)})')
    print(f'Datahub prices: {len(datahub_p)} meses (ate {max(datahub_p)})')
    print(f'FRED CPI: {len(fred_cpi)} meses (ate {max(fred_cpi)})')

    # 3. Construir lista contínua de meses
    def ym_to_idx(ym):
        y = int(ym[:4]); m = int(ym[5:7])
        return y * 12 + (m - 1)
    def idx_to_ym(idx):
        return f'{idx // 12:04d}-{(idx % 12) + 1:02d}'

    start_idx = ym_to_idx(START_YM)
    end_idx = max(ym_to_idx(max(datahub_p)), ym_to_idx(max(shiller)))

    rows = []
    for idx in range(start_idx, end_idx + 1):
        ym = idx_to_ym(idx)
        if ym in shiller and shiller[ym]['p'] > 0:
            p = shiller[ym]['p']
        elif ym in datahub_p:
            p = datahub_p[ym]
        else:
            continue
        d = shiller[ym]['d'] if ym in shiller else 0
        if ym in fred_cpi:
            cpi = fred_cpi[ym]
        elif ym in shiller and shiller[ym]['cpi'] > 0:
            cpi = shiller[ym]['cpi']
        else:
            cpi = 0
        rows.append({'ym': ym, 'p': p, 'd': d, 'cpi': cpi})

    # 4. Forward-fill Dividend
    last_d = None
    for r in rows:
        if r['d'] > 0:
            last_d = r['d']
        elif last_d is not None:
            r['d'] = last_d

    # 5. Forward-fill CPI residual
    last_cpi = None
    for r in rows:
        if r['cpi'] > 0:
            last_cpi = r['cpi']
        elif last_cpi is not None:
            r['cpi'] = last_cpi

    # 6. Pré-computar nomTRP (S&P convention: D[t-1]/12)
    rows[0]['nomTRP'] = 100.0
    for i in range(1, len(rows)):
        prev = rows[i-1]
        cur  = rows[i]
        if prev['p'] <= 0 or cur['p'] <= 0:
            cur['nomTRP'] = prev.get('nomTRP', 100.0)
            continue
        d_prev = prev['d']
        cur['nomTRP'] = prev['nomTRP'] * (cur['p'] + d_prev / 12) / prev['p']

    # 7. (Opcional) Yahoo ^SP500TR override pós-Sep 2023
    if USE_YAHOO_OVERRIDE:
        try:
            yahoo = fetch_yahoo_sp500tr()
        except Exception as e:
            print(f'\nWARNING: fetch Yahoo ^SP500TR falhou: {e}')
            print('  -> mantendo extensao calculada com forward-fill de dividend.')
            yahoo = None

        if yahoo and SHILLER_LAST_YM in yahoo:
            anchor_idx = next((i for i, r in enumerate(rows) if r['ym'] == SHILLER_LAST_YM), None)
            if anchor_idx is None:
                print(f'\nWARNING: anchor month {SHILLER_LAST_YM} nao encontrado.')
            else:
                anchor_nomTRP = rows[anchor_idx]['nomTRP']
                anchor_yahoo  = yahoo[SHILLER_LAST_YM]
                replaced = 0
                for i in range(anchor_idx + 1, len(rows)):
                    ym = rows[i]['ym']
                    if ym in yahoo:
                        yahoo_ratio = yahoo[ym] / anchor_yahoo
                        rows[i]['nomTRP'] = anchor_nomTRP * yahoo_ratio
                        replaced += 1
                print(f'\nYahoo ^SP500TR override: {replaced} meses substituidos.')
    else:
        print('\nUSE_YAHOO_OVERRIDE=False -> mantendo extensao calculada.')

    # 8. Filtrar para apenas meses FULLY COMPLETOS
    today = datetime.date.today()
    current_ym = f'{today.year:04d}-{today.month:02d}'
    before_count = len(rows)
    rows = [r for r in rows if r['ym'] < current_ym]
    removed = before_count - len(rows)
    if removed > 0:
        print(f'\nFiltrados {removed} meses incompletos (>= {current_ym}).')

    start = rows[0]['ym']
    end   = rows[-1]['ym']

    print(f'\nRange final: {start} -> {end} (n={len(rows)})')
    print('Last 3 entries:')
    for r in rows[-3:]:
        print(f'  {r["ym"]}: P={r["p"]:.4f} CPI={r["cpi"]:.4f} '
              f'nomTRP={r["nomTRP"]:.4f}')

    payload = {
        'start': start,
        'end':   end,
        'prices':  [round(r['p'], 4)      for r in rows],
        'cpis':    [round(r['cpi'], 4)    for r in rows],
        'nomTRP':  [round(r['nomTRP'], 4) for r in rows],
    }
    json_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)

    # Output JS file (carregado via <script src="..."> a partir do CDN)
    js_body = (
        '/* S&P 500 dataset auto-gerado por _build_dataset.py.\n'
        '   Fontes: Shiller XLS (P, D) + FRED (CPI) + Yahoo ^SP500TR (TR pos-2023-09).\n'
        '   nomTRP = indice Total Return pre-calculado (convencao S&P standard).\n'
        '   Cobre {0} -> {1} (mensal, n={2}).\n'
        '   Atualizar: workflow .github/workflows/update.yml (1x mes). */\n'
        'window.__lfcSpData = {3};\n'
    ).format(start, end, len(rows), json_str)

    with open(output, 'w', encoding='utf-8') as f:
        f.write(js_body)

    size_kb = os.path.getsize(output) / 1024
    print(f'\nOutput: {output} ({size_kb:.1f} KB)')

    # Cleanup
    for tmp in (shiller_xls, datahub_csv, fred_csv):
        try:
            os.remove(tmp)
        except OSError:
            pass
    print('Cleaned up temp files.')


if __name__ == '__main__':
    main()
