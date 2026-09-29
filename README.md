# Pipeline de transações - Fintech

Pipeline em Python/Pandas que limpa dados brutos de transações, cruza com nível
de risco por cliente, detecta anomalias por Z-Score e gera um gráfico de
volume diário com média móvel.

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python criar_dados.py            # gera transacoes.csv e cotacoes.csv
python pipeline.py               # roda o pipeline
```

Os resultados vão para a pasta `saida/`.

## O que cada etapa faz

| Etapa | Onde | Decisão |
|---|---|---|
| Leitura | `carregar_e_limpar` | `encoding="latin1"`, mesmo formato em que o arquivo foi salvo |
| NaN em `valor` | `carregar_e_limpar` | `groupby("estado_cliente").transform("median")` + `fillna`, sem laço |
| `plataforma` | `carregar_e_limpar` | valor fixo `'Mobile'` |
| Fuso horário | `tratar_datas` | `to_datetime` + `dt.tz_localize("America/Sao_Paulo")` |
| Dia da semana / mês | `tratar_datas` | acessor `.dt` (`day_name()` traduzido e `month`) |
| Duplicadas | `tratar_datas` | `drop_duplicates(keep="first")` (15 removidas) |
| Filtro | `filtrar_setembro_alto_valor` | máscaras combinadas com `&` e `\|`, valor > 5000 |
| Risco | `montar_pivot` | `.map(RISCO_DICT)` |
| Pivot | `montar_pivot` | soma de `valor`, mês x risco, `margins=True` |
| Z-Score | `zscore_por_grupo` | `(x - média) / desvio` por estado via `groupby.transform` |
| Gráfico | `gerar_grafico` | API OO (`fig, ax`), `rolling(7).mean()`, `ax.set_ylim(bottom=0)` |

## Observações

- A imputação acontece antes da remoção de duplicadas, seguindo a ordem do
  enunciado. Como as duplicadas são do mesmo estado, recebem a mesma mediana e
  continuam sendo detectadas como duplicadas.
- O desvio padrão do Z-Score usa `ddof=1` (padrão do Pandas, amostral).
- Os valores dos dados são discretos (50, 150, 3000, 7500, 12000), então os Z
  altos concentram-se nas transações de R$ 12.000. Com Z > 2.5 sobram 46 casos.
- `cotacoes.csv` não é exigido no enunciado; usei como extra: os 2 NaN são
  interpolados e o `resumo_diario.csv` traz também o total diário em USD.
- O dicionário `RISCO_DICT` está no topo do `pipeline.py`; edite lá se a
  classificação dos clientes mudar.
- O enunciado gera dados a partir de 01/09/2026 com 1000 horas, então os
  dados vão até 12/10/2026 (por isso o pivot tem setembro e outubro).
