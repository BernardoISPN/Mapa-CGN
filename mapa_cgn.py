import streamlit as st
import pandas as pd
import geopandas as gpd
import geobr
import pydeck as pdk
import json
import numpy as np

st.set_page_config(
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Projetos que receberam votos da CT - Edital 45")

st.write("")
st.write("")
st.write("")

# ==============================
# CONFIGURAÇÕES
# ==============================
sheet_id = st.secrets["google"]["sheet_id"]
gid_pequenos = "0"
gid_consolidacao = "1670469352"

url_pequenos = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid_pequenos}"
url_consolidacao = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid_consolidacao}"

# ==============================
# CARREGAR PLANILHAS
# ==============================
@st.cache_data
def carregar_dados():
    df_peq = pd.read_csv(url_pequenos)
    df_cons = pd.read_csv(url_consolidacao)

    df_peq["tipo"] = "Pequeno"
    df_cons["tipo"] = "Consolidação"

    df = pd.concat([df_peq, df_cons], ignore_index=True)
    df["Município Principal"] = pd.to_numeric(
        df["Município Principal"],
        errors="coerce"
    )

    df = df.dropna(subset=["Município Principal"])
    df["Município Principal"] = df["Município Principal"].astype(int)
    df["ranking_str"] = df["Ranking por votos"].astype(str)
    
    df["ranking_num"] = (
        df["ranking_str"]
        .str.split(",")
        .str[0]
        .astype(int)
    )

    return df

df = carregar_dados()

# ==============================
# FILTROS (COM FORM)
# ==============================

# Criar label completa antes do form
df["label_projeto"] = (
    df["Ranking por votos"].astype(str)
    + " - "
    + df["Número projeto"].astype(str)
    + " - "
    + df["Nome da organização"].astype(str)
)

df = df.sort_values("Ranking por votos")

# ==============================
# FILTROS NA SIDEBAR (COM FORM)
# ==============================

# Criar label completa antes do form
df["label_projeto"] = (
    df["Ranking por votos"].astype(str)
    + " - "
    + df["Número projeto"].astype(str)
    + " - "
    + df["Nome da organização"].astype(str)
)

df = df.sort_values(["ranking_num", "tipo"])

with st.sidebar.form("filtros_form"):

    st.markdown("## Filtros")

    # ======================
    # CHECKBOX GERAL POR TIPO
    # ======================
    mostrar_pequenos = st.checkbox("Projetos Pequenos", True)
    mostrar_consolidacao = st.checkbox("Projetos Consolidação", True)

    st.markdown("---")

    projetos_selecionados = []

    # ======================
    # COLUNAS LADO A LADO
    # ======================

    col1, col2 = st.columns(2)

    # COLUNA PEQUENOS
    with col1:
        if mostrar_pequenos:
            st.markdown("### 🔵 Pequenos")

            df_peq = df[df["tipo"] == "Pequeno"]

            for _, row in df_peq.iterrows():
                checked = st.checkbox(
                    row["label_projeto"],
                    value=True,
                    key=f"peq_{row['Número projeto']}"
                )
                if checked:
                    projetos_selecionados.append(row["label_projeto"])

    # COLUNA CONSOLIDAÇÃO
    with col2:
        if mostrar_consolidacao:
            st.markdown("### 🔴 Consolidação")

            df_cons = df[df["tipo"] == "Consolidação"]

            for _, row in df_cons.iterrows():
                checked = st.checkbox(
                    row["label_projeto"],
                    value=True,
                    key=f"cons_{row['Número projeto']}"
                )
                if checked:
                    projetos_selecionados.append(row["label_projeto"])

    aplicar_filtros = st.form_submit_button("Aplicar filtros")

# Só filtra depois que clicar no botão
if aplicar_filtros:

    tipos = []
    if mostrar_pequenos:
        tipos.append("Pequeno")
    if mostrar_consolidacao:
        tipos.append("Consolidação")

    df = df[df["tipo"].isin(tipos)]
    df = df[df["label_projeto"].isin(projetos_selecionados)]

# ==============================
# GEO
# ==============================
@st.cache_data
def carregar_geo():
    municipios = geobr.read_municipality(year=2020, simplified=True)
    biomas = geobr.read_biomes(year=2019, simplified=True)
    estados = geobr.read_state(year=2020, simplified=True)

    estados_desejados = [
        "Mato Grosso","Mato Grosso Do Sul","Distrito Federal",
        "Goiás","Tocantins","Maranhão","Ceará","Piauí","Bahia",
        "Pernambuco","Rio Grande Do Norte","Paraíba","Alagoas",
        "Sergipe","Minas Gerais"
    ]

    estados = estados[estados["name_state"].isin(estados_desejados)]
    estados = estados.to_crs(epsg=4326)

    cerrado = biomas[biomas["name_biome"] == "Cerrado"].to_crs(epsg=4326)
    caatinga = biomas[biomas["name_biome"] == "Caatinga"].to_crs(epsg=4326)

    return municipios, estados, cerrado, caatinga

municipios, estados, cerrado, caatinga = carregar_geo()

# ==============================
# MERGE MUNICÍPIOS
# ==============================
df_geo = municipios.merge(
    df,
    left_on="code_muni",
    right_on="Município Principal",
    how="inner"
)

df_geo_proj = df_geo.to_crs(epsg=5880)
df_geo_proj["geometry"] = df_geo_proj.geometry.centroid
df_geo = df_geo_proj.to_crs(epsg=4326)

df_geo["lon"] = df_geo.geometry.x
df_geo["lat"] = df_geo.geometry.y
df_geo = df_geo.drop(columns="geometry")

# ==============================
# SPIDERFY
# ==============================
@st.cache_data
def criar_spiderfy(df, raio_km=10):
    df = df.copy()
    pontos = []
    linhas = []

    for muni, group in df.groupby("Município Principal"):
        centro_lat = group.iloc[0]["lat"]
        centro_lon = group.iloc[0]["lon"]
        n = len(group)

        raio = raio_km / 111
        angles = np.linspace(0, 2*np.pi, n, endpoint=False)

        for i, (_, row) in enumerate(group.iterrows()):
            if n == 1:
                lat = centro_lat
                lon = centro_lon
            else:
                lat = centro_lat + raio * np.sin(angles[i])
                lon = centro_lon + raio * np.cos(angles[i])

            linhas.append({
                "source": [centro_lon, centro_lat],
                "target": [lon, lat]
            })

            novo = row.copy()
            novo["lat_plot"] = lat
            novo["lon_plot"] = lon
            pontos.append(novo)

    return pd.DataFrame(pontos), pd.DataFrame(linhas)

df_pontos, df_linhas = criar_spiderfy(df_geo)

df_pontos["color"] = df_pontos["tipo"].map({
    "Pequeno": [52, 152, 219],
    "Consolidação": [231, 76, 60]
})

df_pontos["ranking_num"] = (
    df_pontos["ranking_str"]
    .str.split(",")
    .str[0]
    .astype(int)
)

df_pontos["radius"] = 30 - (df_pontos["ranking_num"] * 1.2)
df_pontos["radius"] = df_pontos["radius"].clip(lower=10)

# ==============================
# REMOVER GEOMETRIA
# ==============================
if "geometry" in df_pontos.columns:
    df_pontos = df_pontos.drop(columns="geometry")

if "geometry" in df_linhas.columns:
    df_linhas = df_linhas.drop(columns="geometry")

# ==============================
# CAMADAS 
# ==============================

cerrado_layer = pdk.Layer(
    "GeoJsonLayer",
    data=cerrado.__geo_interface__,
    opacity=0.01,  
    stroked=True,
    filled=True,
    get_fill_color=[46, 204, 113],
    get_line_color=[0, 0, 0],
)

caatinga_layer = pdk.Layer(
    "GeoJsonLayer",
    data=caatinga.__geo_interface__,
    opacity=0.01,  
    stroked=True,
    filled=True,
    get_fill_color=[241, 196, 15],
    get_line_color=[0, 0, 0],
)

estados_layer = pdk.Layer(
    "GeoJsonLayer",
    data=estados.__geo_interface__,
    stroked=True,
    filled=False,
    get_line_color=[0, 0, 0],
    get_line_width=0.5,
    line_width_min_pixels=0.5, 
)

linhas_layer = pdk.Layer(
    "LineLayer",
    data=df_linhas.to_dict("records"),  
    get_source_position="source",
    get_target_position="target",
    get_width=2,
    get_color=[120, 120, 120],
)

pontos_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df_pontos.to_dict("records"), 
    get_position='[lon_plot, lat_plot]',
    get_fill_color='color',
    pickable=True,
    radiusUnits="pixels",
    get_radius=1,           
    radiusMinPixels=15,       
    radiusMaxPixels=22,      
)

texto_layer = pdk.Layer(
    "TextLayer",
    data=df_pontos.to_dict("records"),  # IGUAL HTML
    get_position='[lon_plot, lat_plot]',
    get_text="ranking_str",
    get_size=12,
    get_color=[0, 0, 0],
)

# ==============================
# VIEW
# ==============================
view = pdk.ViewState(
    latitude=-14,
    longitude=-52,
    zoom=4,
)

# ==============================
# MAPA
# ==============================
deck = pdk.Deck(
    layers=[
        cerrado_layer,
        caatinga_layer,
        estados_layer,
        pontos_layer,
        texto_layer,
        linhas_layer,
    ],
    initial_view_state=view,
    map_style="light",
    tooltip={
        "html": """
        <b>Código do projeto:</b> {Número projeto}<br/>
        <b>Município:</b> {name_muni} - {abbrev_state}<br/>
        <b>Organização:</b> {Nome da organização}<br/>
        <b>Nome do projeto:</b> {Nome do projeto}<br/>
        <b>Número de famílias beneficiadas:</b> {Número de famílias beneficiadas}<br/>
        """,
        "style": {
            "backgroundColor": "white",
            "color": "black",
            "fontSize": "13px",
            "border": "1px solid #ccc",
            "borderRadius": "6px",
            "padding": "8px"
        }
    }
)

st.pydeck_chart(deck, width="stretch", height=950)