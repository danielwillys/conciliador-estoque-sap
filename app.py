import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

st.set_page_config(layout="wide", page_title="Conciliador de Estoque SAP")

# --- CSS ---
st.markdown("""
<style>
.main { background-color: #f5f7fa; }
.kpi-card {
    background: white;
    padding: 18px;
    border-radius: 12px;
    box-shadow: 0px 2px 8px rgba(0,0,0,0.08);
    text-align: center;
}

/* Centralizar TODOS os títulos */
h1, h2, h3 {
    text-align: center !important;
    width: 100%;
}

/* Centralizar cabeçalho dataframe */
[data-testid="column-header-content"] {
    justify-content: center !important;
    text-align: center !important;
}

/* Centralizar células */
[data-testid="stDataFrame"] td {
    text-align: center !important;
}

/* Centralizar cabeçalhos */
[data-testid="stDataFrame"] th {
    text-align: center !important;
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Comparativo de Estoque: MB52 vs ADPROD")

# --- SIDEBAR ---
st.sidebar.header("1. Importar Relatórios")
file_mb52 = st.sidebar.file_uploader("Relatório MB52 (ERP)", type=['xlsx'])
file_adprod = st.sidebar.file_uploader("Relatório ADPROD (EWM)", type=['xlsx'])

if file_mb52 and file_adprod:
    df_mb52_raw = pd.read_excel(file_mb52)
    df_adprod_raw = pd.read_excel(file_adprod)

    # --- LIMPAR COLUNAS ---
    df_mb52_raw.columns = df_mb52_raw.columns.str.strip()
    df_adprod_raw.columns = df_adprod_raw.columns.str.strip()

    def limpar_codigo(col):
        return col.astype(str).str.replace(r'\.0+$', '', regex=True).str.strip()

    for col in ["Material", "Lote"]:
        if col in df_mb52_raw.columns:
            df_mb52_raw[col] = limpar_codigo(df_mb52_raw[col])

    for col in ["Produto", "Lote"]:
        if col in df_adprod_raw.columns:
            df_adprod_raw[col] = limpar_codigo(df_adprod_raw[col])

    # --- VALIDAÇÃO ---
    required_mb52 = ["Material", "Lote"]
    required_adprod = ["Produto", "Lote", "Qtd.disponível UMB"]

    def validar(df, cols):
        return all(c in df.columns for c in cols)

    if validar(df_mb52_raw, required_adprod) and validar(df_adprod_raw, required_mb52):
        st.warning("⚠️ Arquivos invertidos.")
        st.stop()

    if not validar(df_mb52_raw, required_mb52):
        st.error("❌ Arquivo MB52 inválido")
        st.stop()

    if not validar(df_adprod_raw, required_adprod):
        st.error("❌ Arquivo ADPROD inválido")
        st.stop()

    # --- FILTROS ---
    st.sidebar.markdown("---")
    st.sidebar.header("2. Filtros")

    cols_mb52 = [c for c in ["Utilização livre", "Controle qualidade", "Bloqueado"] if c in df_mb52_raw.columns]
    selected_mb52 = st.sidebar.multiselect("Categorias MB52", cols_mb52, default=cols_mb52)

    tipos = df_adprod_raw["Tipo de estoque"].unique().tolist()
    selected_adprod = st.sidebar.multiselect("Categorias ADPROD", tipos, default=tipos)

    # --- REFERÊNCIA ---
    referencia = df_adprod_raw[['Produto', 'Descrição breve do produto', 'UM básica']].drop_duplicates()

    # --- PROCESSAMENTO ---
    df_mb52_raw['Soma_ERP'] = df_mb52_raw[selected_mb52].sum(axis=1)
    df_mb52 = df_mb52_raw.groupby(["Material", "Lote"])['Soma_ERP'].sum().reset_index()

    df_adprod_f = df_adprod_raw[df_adprod_raw["Tipo de estoque"].isin(selected_adprod)]
    df_adprod = df_adprod_f.groupby(["Produto", "Lote"])["Qtd.disponível UMB"].sum().reset_index()

    # --- MERGE ---
    df_merge = pd.merge(df_adprod, df_mb52, left_on=["Produto", "Lote"], right_on=["Material", "Lote"], how='outer').fillna(0)
    df_merge["Produto_F"] = df_merge["Produto"].where(df_merge["Produto"] != 0, df_merge["Material"])
    df_merge = pd.merge(df_merge, referencia, left_on="Produto_F", right_on="Produto", how="left")

    # --- CÁLCULOS ---
    df_merge["Qtd ADPROD"] = df_merge["Qtd.disponível UMB"].round().astype(int)
    df_merge["Qtd MB52"] = df_merge["Soma_ERP"].round().astype(int)
    df_merge["Divergencia"] = df_merge["Qtd ADPROD"] - df_merge["Qtd MB52"]
    df_merge["Status"] = df_merge["Divergencia"].apply(lambda x: 'Correto' if x == 0 else 'Divergente')

    df_display = df_merge[[
        "Produto_F", "Descrição breve do produto", "Lote", "UM básica",
        "Qtd ADPROD", "Qtd MB52", "Divergencia", "Status"
    ]].copy()

    df_display.columns = ['Produto', 'Descrição', 'Lote', 'UMB', 'Qtd ADPROD', 'Qtd MB52', 'Divergencia', 'Status']

    # --- ESTILO ---
    def style_div(df):
        styles = pd.DataFrame('', index=df.index, columns=df.columns)
        for i in df.index:
            base_style = 'text-align: center;'
            if df.loc[i, 'Divergencia'] != 0:
                base_style += ' background-color: #fdecea;'
            
            styles.loc[i, :] = base_style

            if df.loc[i, 'Divergencia'] < 0:
                styles.loc[i, 'Divergencia'] = base_style + ' color: #e74c3c; font-weight: bold;'
            elif df.loc[i, 'Divergencia'] > 0:
                styles.loc[i, 'Divergencia'] = base_style + ' color: #3498db; font-weight: bold;'
        return styles

    # --- KPI ---
    total = len(df_display)
    corretos = (df_display['Status'] == 'Correto').sum()
    divergentes = (df_display['Status'] == 'Divergente').sum()
    acuracidade = (corretos / total * 100) if total > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='kpi-card'><h3>{total}</h3><p>Total</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi-card'><h3>{corretos}</h3><p>Corretos</p></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi-card'><h3>{divergentes}</h3><p>Divergentes</p></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi-card'><h3>{acuracidade:.1f}%</h3><p>Acuracidade</p></div>", unsafe_allow_html=True)

    st.markdown("<h2 style='text-align:center;'>📊 Visão Geral</h2>", unsafe_allow_html=True)

    fig = px.pie(df_display, names='Status', hole=0.6, color='Status', color_discrete_map={'Correto':'#2ecc71','Divergente':'#e74c3c'})

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<h3 style='text-align:center;'>Acuracidade do Estoque</h3>", unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("<h3 style='text-align:center;'>Top 10 Divergências</h3>", unsafe_allow_html=True)

        top_10 = df_display[df_display['Divergencia'] != 0].copy()
        top_10['Abs'] = top_10['Divergencia'].abs()
        top_10 = top_10.sort_values('Abs', ascending=False).head(10).reset_index(drop=True)
        top_10.index = top_10.index + 1

        num_linhas = len(top_10)
        altura_linha = 34 
        altura_header = 40
        altura_total = (num_linhas * altura_linha) + altura_header + 5

        df_top10_view = top_10[['Produto','Lote','Divergencia']]

        st.dataframe(
            df_top10_view.style.apply(style_div, axis=None),
            height=altura_total,
            use_container_width=True,
            column_config={col: st.column_config.Column(alignment="center") for col in df_top10_view.columns}
        )

    # --- ANÁLISE DETALHADA ---
    st.markdown("<h2 style='text-align:center;'>🔎 Análise Detalhada</h2>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    busca_prod = c1.text_input("Filtrar Produto/Descrição")
    busca_lote = c2.text_input("Filtrar Lote")
    filtro_status = c3.multiselect("Filtrar Status", df_display['Status'].unique(), default=df_display['Status'].unique())

    df_filtrado = df_display.copy()
    if busca_prod:
        df_filtrado = df_filtrado[df_filtrado['Produto'].str.contains(busca_prod, case=False) | df_filtrado['Descrição'].str.contains(busca_prod, case=False)]
    if busca_lote:
        df_filtrado = df_filtrado[df_filtrado['Lote'].str.contains(busca_lote, case=False)]
    df_filtrado = df_filtrado[df_filtrado['Status'].isin(filtro_status)]

    st.dataframe(
        df_filtrado.style.apply(style_div, axis=None),
        column_config={col: st.column_config.Column(alignment="center") for col in df_filtrado.columns},
        height=500,
        use_container_width=True
    )

    def to_excel(df):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()

    st.download_button("📥 Baixar Excel", data=to_excel(df_filtrado), file_name="conciliacao.xlsx")

else:
    st.info("💡 Envie os arquivos MB52 e ADPROD.")