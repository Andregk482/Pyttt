"""
Pipeline de análise de transações - Fintech
Limpeza, transformação, consolidação, detecção de anomalias e gráfico.

Uso:
    python criar_dados.py   # gera transacoes.csv e cotacoes.csv
    python pipeline.py      # roda tudo e salva os resultados em ./saida
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # salva o gráfico em arquivo, sem precisar de janela
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ARQ_TRANSACOES = "transacoes.csv"
ARQ_COTACOES = "cotacoes.csv"
PASTA_SAIDA = Path("saida")
LIMITE_Z = 2.5
VALOR_MINIMO = 5000.0

# Nível de risco por cliente (usado no .map())
RISCO_DICT = {
    "C100": "Baixo",
    "C101": "Alto",
    "C102": "Medio",
    "C103": "Baixo",
    "C104": "Alto",
}

DIAS_PT = {
    "Monday": "Segunda", "Tuesday": "Terca", "Wednesday": "Quarta",
    "Thursday": "Quinta", "Friday": "Sexta", "Saturday": "Sabado",
    "Sunday": "Domingo",
}


# ---------------------------------------------------------------- 1. limpeza
def carregar_e_limpar(caminho: str) -> pd.DataFrame:
    # o arquivo foi salvo em latin1, então precisa ser lido assim
    df = pd.read_csv(caminho, encoding="latin1")
    print(f"[ingestão] {len(df)} linhas | NaN em valor: {df['valor'].isna().sum()}")

    # mediana por estado, calculada de forma vetorizada com transform
    mediana_estado = df.groupby("estado_cliente")["valor"].transform("median")
    df["valor"] = df["valor"].fillna(mediana_estado)

    df["plataforma"] = "Mobile"
    return df


# ------------------------------------------------------------- 2. datas/tempo
def tratar_datas(df: pd.DataFrame) -> pd.DataFrame:
    df["data_transacao"] = pd.to_datetime(df["data_transacao"])
    df["data_transacao"] = df["data_transacao"].dt.tz_localize("America/Sao_Paulo")

    df["dia_semana"] = df["data_transacao"].dt.day_name().map(DIAS_PT)
    df["mes"] = df["data_transacao"].dt.month

    antes = len(df)
    df = df.drop_duplicates(keep="first").reset_index(drop=True)
    print(f"[duplicadas] removidas: {antes - len(df)}")
    return df


# ------------------------------------------------------------ 3. filtro bitwise
def filtrar_setembro_alto_valor(df: pd.DataFrame) -> pd.DataFrame:
    e_setembro = df["mes"] == 9
    e_sp_rj = (df["estado_cliente"] == "SP") | (df["estado_cliente"] == "RJ")
    e_alto_valor = df["valor"] > VALOR_MINIMO

    return df[e_setembro & e_sp_rj & e_alto_valor]


# ----------------------------------------------------------- 4. risco + pivot
def montar_pivot(df: pd.DataFrame) -> pd.DataFrame:
    df["nivel_risco"] = df["id_cliente"].map(RISCO_DICT)

    return pd.pivot_table(
        df,
        values="valor",
        index="mes",
        columns="nivel_risco",
        aggfunc="sum",
        margins=True,
        margins_name="Total",
        fill_value=0,
    )


# -------------------------------------------------------------- 5. z-score
def zscore_por_grupo(df: pd.DataFrame, coluna: str, grupo: str) -> pd.Series:
    """Z = (x - media) / desvio, calculado dentro de cada grupo, sem for."""
    g = df.groupby(grupo)[coluna]
    return (df[coluna] - g.transform("mean")) / g.transform("std")


def detectar_anomalias(df: pd.DataFrame, limite: float = LIMITE_Z) -> pd.DataFrame:
    df["z_score"] = zscore_por_grupo(df, "valor", "estado_cliente")
    return df[df["z_score"] > limite].copy()


# ------------------------------------------------------------ 6. cotações (extra)
def carregar_cotacoes(caminho: str) -> pd.DataFrame:
    cot = pd.read_csv(caminho, encoding="utf-8", parse_dates=["data"])
    # dois dias vieram sem cotação; interpolo entre o dia anterior e o seguinte
    cot["cotacao_usd"] = cot["cotacao_usd"].interpolate()
    return cot


# ------------------------------------------------------------------ 7. gráfico
def gerar_grafico(df: pd.DataFrame, destino: Path) -> pd.DataFrame:
    datas = df["data_transacao"].dt.tz_localize(None).dt.normalize()
    diario = df.groupby(datas)["valor"].sum().rename("total_diario").to_frame()
    diario["media_movel_7d"] = diario["total_diario"].rolling(7).mean()

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(diario.index, diario["total_diario"], color="#9aa5b1",
            linewidth=1.3, marker="o", markersize=3, label="Total diário")
    ax.plot(diario.index, diario["media_movel_7d"], color="#d1495b",
            linewidth=2.4, label="Média móvel (7 dias)")

    ax.set_ylim(bottom=0)
    ax.set_title("Volume financeiro diário de transações")
    ax.set_xlabel("Data")
    ax.set_ylabel("Valor total (R$)")
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"R$ {v:,.0f}".replace(",", "."))
    )
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    return diario


# ------------------------------------------------------------------------ main
def main():
    PASTA_SAIDA.mkdir(exist_ok=True)

    df = carregar_e_limpar(ARQ_TRANSACOES)
    df = tratar_datas(df)

    filtradas = filtrar_setembro_alto_valor(df)
    print(f"[filtro] setembro, SP/RJ, valor > {VALOR_MINIMO:.0f}: {len(filtradas)} transações")

    pivot = montar_pivot(df)
    print("\n[pivot] soma do valor por mês x nível de risco")
    print(pivot.round(2))

    anomalias = detectar_anomalias(df)
    print(f"\n[z-score] anomalias com Z > {LIMITE_Z}: {len(anomalias)}")
    if anomalias.empty:
        print("          nenhuma transação passou do limite (ver README)")
    print("[z-score] maior Z por estado:")
    print(df.groupby("estado_cliente")["z_score"].max().round(3))

    diario = gerar_grafico(df, PASTA_SAIDA / "grafico_diario.png")

    cot = carregar_cotacoes(ARQ_COTACOES)
    diario = diario.reset_index().rename(columns={"data_transacao": "data"})
    diario = diario.merge(cot[["data", "cotacao_usd"]], on="data", how="left")
    diario["total_usd"] = diario["total_diario"] / diario["cotacao_usd"]

    # exporto tudo com data sem fuso para abrir bem no Excel
    limpas = df.copy()
    limpas["data_transacao"] = limpas["data_transacao"].astype(str)
    limpas.to_csv(PASTA_SAIDA / "transacoes_limpas.csv", index=False, encoding="utf-8")
    filtradas.assign(data_transacao=filtradas["data_transacao"].astype(str)) \
        .to_csv(PASTA_SAIDA / "filtro_setembro_sp_rj.csv", index=False, encoding="utf-8")
    anomalias.assign(data_transacao=anomalias["data_transacao"].astype(str)) \
        .to_csv(PASTA_SAIDA / "anomalias.csv", index=False, encoding="utf-8")
    pivot.to_csv(PASTA_SAIDA / "pivot_mes_risco.csv", encoding="utf-8")
    diario.to_csv(PASTA_SAIDA / "resumo_diario.csv", index=False, encoding="utf-8")

    print(f"\nPronto. Resultados em ./{PASTA_SAIDA}/")


if __name__ == "__main__":
    main()
