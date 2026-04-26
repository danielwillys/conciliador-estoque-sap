import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide", page_title="Conciliador de Estoque SAP")

st.title("📊 Comparativo de Estoque: MB52 vs ADPROD")
st.markdown("---")

# --- SIDEBAR: IMPORTAÇÃO ---
st.sidebar.header("1. Importar Relatórios")
file_mb52 = st.sidebar.file_uploader("Relatório MB52 (ERP)", type=['xlsx'])
file_adprod = st.sidebar.file_uploader("Relatório ADPROD (EWM)", type=['xlsx'])

if file_mb52 and file_adprod:
    df_mb52_raw = pd.read_excel(file_mb52)
    df_adprod_raw = pd.read_excel(file_adprod)

    # --- 2. FILTROS DE CATEGORIA ---
    st.sidebar.markdown("---")
    st.sidebar.header("2. Filtros de Categoria")
    
    cols_mb52_disponiveis = ["Utilização livre", "Controle qualidade", "Bloqueado"]
    cols_presentes_mb52 = [c for c in cols_mb52_disponiveis if c in df_mb52_raw.columns]
    selected_mb52 = st.sidebar.multiselect("Categorias MB52", options=cols_presentes_mb52, default=cols_presentes_mb52)
    
    tipos_adprod_reais = df_adprod_raw["Tipo de estoque"].unique().tolist()
    defaults_adprod = [t for t in ['F1', 'B5', 'Q3'] if t in tipos_adprod_reais]
    selected_adprod = st.sidebar.multiselect("Tipos ADPROD", options=tipos_adprod_reais, default=defaults_adprod if defaults_adprod else tipos_adprod_reais)

    # --- SOLUÇÃO PARA DESCRIÇÕES AUSENTES ---
    # Criamos um de-para de Produto -> Descrição e UMB usando a ADPROD como referência
    referencia_produtos = df_adprod_raw[['Produto', 'Descrição breve do produto', 'UM básica']].drop_duplicates('Produto')
    referencia_produtos['Produto'] = referencia_produtos['Produto'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # --- TRATAMENTO MB52 ---
    df_mb52_raw['Soma_ERP'] = df_mb52_raw[selected_mb52].sum(axis=1)
    df_mb52 = df_mb52_raw.groupby(["Material", "Lote"])['Soma_ERP'].sum().reset_index()
    df_mb52["Material"] = df_mb52["Material"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    df_mb52["Lote"] = df_mb52["Lote"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # --- TRATAMENTO ADPROD ---
    df_adprod_filtered = df_adprod_raw[df_adprod_raw["Tipo de estoque"].isin(selected_adprod)]
    df_adprod = df_adprod_filtered.groupby(["Produto", "Lote"])["Qtd.disponível UMB"].sum().reset_index()
    df_adprod["Produto"] = df_adprod["Produto"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    df_adprod["Lote"] = df_adprod["Lote"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # --- CONCILIAÇÃO (OUTER MERGE) ---
    df_merge = pd.merge(df_adprod, df_mb52, left_on=["Produto", "Lote"], right_on=["Material", "Lote"], how='outer').fillna(0)

    # Consolidação de chaves de produto
    df_merge["Produto_Final"] = df_merge["Produto"].where(df_merge["Produto"] != 0, df_merge["Material"])
    
    # REPREENCHIMENTO: Busca a descrição na referência criada no início
    df_merge = pd.merge(df_merge, referencia_produtos, left_on="Produto_Final", right_on="Produto", how="left", suffixes=('', '_ref'))

    # Conversão para INTEIRO e ajustes finais
    df_merge["Qtd ADPROD"] = df_merge["Qtd.disponível UMB"].astype(int)
    df_merge["Qtd MB52"] = df_merge["Soma_ERP"].astype(int)
    df_merge["Divergencia"] = (df_merge["Qtd ADPROD"] - df_merge["Qtd MB52"]).astype(int)
    df_merge["Status"] = df_merge["Divergencia"].apply(lambda x: 'Correto' if x == 0 else 'Divergente')

    df_display = df_merge[[
        "Produto_Final", "Descrição breve do produto", "Lote", 
        "UM básica", "Qtd ADPROD", "Qtd MB52", "Divergencia", "Status"
    ]].copy()
    df_display.columns = ['Produto', 'Descrição', 'Lote', 'UMB', 'Qtd ADPROD', 'Qtd MB52', 'Divergencia', 'Status']
    
    # Limpeza de zeros nas descrições de itens que não foram encontrados nem na referência
    df_display['Descrição'] = df_display['Descrição'].replace(0, "NÃO ENCONTRADO NA ADPROD")
    df_display['UMB'] = df_display['UMB'].replace(0, "-")

    # --- FUNÇÃO DE ESTILO ---
    def style_tables(df):
        styles = pd.DataFrame('text-align: center;', index=df.index, columns=df.columns)
        if 'Divergencia' in df.columns:
            for i in df.index:
                val = df.loc[i, 'Divergencia']
                if val < 0: styles.loc[i, 'Divergencia'] = 'color: #e74c3c; font-weight: bold; text-align: center;'
                elif val > 0: styles.loc[i, 'Divergencia'] = 'color: #3498db; font-weight: bold; text-align: center;'
        return styles

    # --- DASHBOARD VISUAL ---
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("Acuracidade de Estoque")
        fig = px.pie(df_display, names='Status', color='Status', color_discrete_map={'Correto':'#2ecc71', 'Divergente':'#e74c3c'}, hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Top 10 Divergências")
        top_10 = df_display[df_display['Divergencia'] != 0].copy()
        top_10['Abs_Div'] = top_10['Divergencia'].abs()
        top_10 = top_10.sort_values(by='Abs_Div', ascending=False).head(10)
        top_10 = top_10[['Produto', 'Lote', 'Divergencia']].reset_index(drop=True)
        top_10.index = top_10.index + 1
        st.dataframe(top_10.style.apply(style_tables, axis=None), use_container_width=True)

    # --- LISTA DETALHADA ---
    st.markdown("---")
    st.subheader("Lista Detalhada")
    busca = st.text_input("Filtrar por código ou lote")
    df_final_filtrado = df_display[df_display.apply(lambda row: busca.lower() in str(row).lower(), axis=1)] if busca else df_display
    st.dataframe(df_final_filtrado.style.apply(style_tables, axis=None), use_container_width=True, height=500)

else:
    st.info("💡 Por favor, carregue os arquivos MB52 e ADPROD para iniciar.")