# lfc-sp500-data

Dataset histórico do S&P 500 auto-atualizado mensalmente. Usado pela [Calculadora de Retorno Histórico do S&P 500](https://www.literaciafinanceira.pt/calculadora-4---calculadora-do-retorno-historico-do-s-p-500) da Literacia Financeira.

## URL do dataset

```
https://cdn.jsdelivr.net/gh/GaMa96/lfc-sp500-data@main/data/sp500.js
```

Carregado via `<script src="...">` no Webflow. Define a global `window.__lfcSpData` com:

- `start`, `end`: range coberto (ex: `"1871-01"` a `"2026-04"`)
- `prices[]`: S&P 500 close mensal (Shiller P column)
- `cpis[]`: Consumer Price Index NSA mensal (FRED CPIAUCNS / Shiller para pré-1913)
- `nomTRP[]`: Total Return Index pré-calculado (convenção S&P standard `(P[t] + D[t-1]/12) / P[t-1]`)

Todos os arrays têm o mesmo `length` = nº de meses entre `start` e `end` inclusive.

## Fontes de dados

| Série | Fonte | Cobertura |
|---|---|---|
| Price (S&P 500) | [Robert Shiller XLS](http://www.econ.yale.edu/~shiller/data/ie_data.xls) (Yale) | 1871-01 → ~2 anos atrás |
| Price (extensão) | [datahub.io mirror](https://datahub.io/core/s-and-p-500) | meses recentes onde Shiller não actualizou |
| Dividend | Shiller XLS | 1871-01 → ~2 anos atrás (forward-filled para o resto) |
| CPI | [FRED CPIAUCNS](https://fred.stlouisfed.org/series/CPIAUCNS) (BLS oficial) | 1913+ |
| CPI (pré-1913) | Shiller XLS (reconstrução) | 1871-01 → 1912 |
| Total Return Index (>2023-09) | [Yahoo ^SP500TR](https://finance.yahoo.com/quote/%5ESP500TR) (S&P actual) | 1988+ (usado a partir de Out 2023) |

## Atualização

### Automática (cron mensal)
[GitHub Actions](https://github.com/GaMa96/lfc-sp500-data/actions) corre `_build_dataset.py` no dia 1 de cada mês às 06:00 UTC. Se houver dados novos, faz commit a `data/sp500.js` e o jsDelivr serve a versão atualizada (cache CDN propaga em ~12h).

### Manual
Para forçar uma atualização fora do ciclo mensal:
1. Vai a **Actions** → **Update S&P 500 dataset**
2. Clica **Run workflow** → **Run workflow**
3. Aguarda ~1-2 min até o workflow terminar

### Local (desenvolvimento)
```bash
pip install -r requirements.txt
python _build_dataset.py
```

O script gera `data/sp500.js` localmente. Útil para testar antes de fazer push.

## Methodology notes

### Total Return convention

O `nomTRP` usa a convenção S&P standard `(P[t] + D[t-1]/12) / P[t-1]` (dividend do mês anterior, dividido por 12 para mensual). Esta convenção dá **match exacto** ao cêntimo com [ofdollarsanddata.com/sp500-calculator/](https://ofdollarsanddata.com/sp500-calculator/) para qualquer período inteiramente dentro do range Shiller (até Set 2023).

### Yahoo ^SP500TR override

A partir de Out 2023 (último mês de Shiller "Real Total Return Price"), substituímos a extensão calculada pelo **S&P 500 Total Return Index oficial** publicado pela própria S&P Global (via Yahoo Finance). Isto:
- ✅ Reflete os dividendos reais cobrados em 2024-2025 (não forward-filled)
- ✅ Inclui compounding diário (vs aproximação mensal da fórmula)
- ⚠️ Diverge de ofdollarsanddata para datas recentes (eles parecem usar cache estático com dividend forward-filled)

Flag `USE_YAHOO_OVERRIDE` no topo de `_build_dataset.py` permite reverter (mudar para `False` se quiseres match ofdollarsanddata em vez de S&P actual).

### Filtragem de meses incompletos

O script filtra automaticamente qualquer mês ainda não concluído. Se hoje é 15 de Maio 2026, o último mês incluído é **Abril 2026** (Maio só entra quando 1 Junho passar). Isto evita valores mid-mês que não representam um close de mês real.

## Estrutura

```
lfc-sp500-data/
├── _build_dataset.py        # script principal
├── requirements.txt         # xlrd<2
├── README.md                # este ficheiro
├── .github/
│   └── workflows/
│       └── update.yml       # GH Actions cron mensal + manual trigger
└── data/
    └── sp500.js             # output (gerado pelo script, served via jsDelivr)
```

## Notas técnicas

- O script é **idempotente**: correr 2× no mesmo dia produz o mesmo output. O commit no GH Actions só acontece se o conteúdo mudou.
- O workflow precisa de `permissions: contents: write` (já configurado) para fazer push.
- jsDelivr cache TTL ~12h para repos públicos do GitHub. Para forçar refresh imediato: usar `https://purge.jsdelivr.net/gh/GaMa96/lfc-sp500-data@main/data/sp500.js`.

## Licença

Dataset agregado de fontes públicas (Shiller, FRED, Yahoo Finance, datahub.io). Use à vontade.
