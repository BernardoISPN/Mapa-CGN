import pandas as pd
import geopandas as gpd
import geobr
import pydeck as pdk
import json
import numpy as np
import re

# ==============================
# CONFIGURAÇÕES
# ==============================
sheet_id = "1HbF2q60MHSBnktYOm3B_rrJ0SD45NSECY_zbpHUeDYA"
gid_pequenos = "0"
gid_consolidacao = "1670469352"

url_pequenos = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid_pequenos}"
url_consolidacao = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid_consolidacao}"

# ==============================
# CARREGAR PLANILHAS
# ==============================
df_pequenos = pd.read_csv(url_pequenos)
df_consolidacao = pd.read_csv(url_consolidacao)

df_pequenos["tipo"] = "Pequeno"
df_consolidacao["tipo"] = "Consolidação"

df = pd.concat([df_pequenos, df_consolidacao], ignore_index=True)

print("Projetos pequenos:", len(df_pequenos))
print("Projetos consolidação:", len(df_consolidacao))

df["Município Principal"] = df["Município Principal"].astype(int)
df["ranking_str"] = df["Ranking por votos"].astype(str)

# ==============================
# CARREGAR GEO
# ==============================
print("Brasil carregado")

biomas = geobr.read_biomes(year=2019)
print("Biomas carregados")

municipios = geobr.read_municipality(year=2020, simplified=True)
print("Muni carregados")

cerrado = biomas[biomas["name_biome"] == "Cerrado"]
caatinga = biomas[biomas["name_biome"] == "Caatinga"]

print("Geometria carregadas")

# ==============================
# FUNÇÃO ORDENAR RANKING
# ==============================
def chave_ranking(valor):
    valor = str(valor).strip()

    # separa por vírgula
    partes = valor.split(",")

    try:
        principal = int(partes[0])
    except:
        principal = 9999

    if len(partes) > 1:
        try:
            secundario = int(partes[1])
        except:
            secundario = 0
    else:
        secundario = 0

    return (principal, secundario)

# ==============================
# MERGE COM MUNICIPIOS
# ==============================
df_geo = municipios.merge(
    df,
    left_on="code_muni",
    right_on="Município Principal",
    how="inner"
)

# Centróide correto
df_geo_proj = df_geo.to_crs(epsg=5880)
df_geo_proj["geometry"] = df_geo_proj.geometry.centroid
df_geo = df_geo_proj.to_crs(epsg=4326)

df_geo["lon"] = df_geo.geometry.x
df_geo["lat"] = df_geo.geometry.y

# ==============================
# FUNÇÃO SPIDERFY
# ==============================
def criar_spiderfy(df, raio_km=40):
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

if "geometry" in df_pontos.columns:
    df_pontos = df_pontos.drop(columns="geometry")

if "geometry" in df_linhas.columns:
    df_linhas = df_linhas.drop(columns="geometry")

df_pontos["ranking_sort"] = df_pontos["ranking_str"].apply(chave_ranking)

df_pontos["color"] = df_pontos["tipo"].map({
    "Pequeno": [52, 152, 219],
    "Consolidação": [231, 76, 60]
})

# ==============================
# CONVERTER BIOMAS
# ==============================
cerrado = cerrado.to_crs(epsg=4326)
caatinga = caatinga.to_crs(epsg=4326)

# ==============================
# CAMADAS
# ==============================
cerrado_layer = pdk.Layer(
    "GeoJsonLayer",
    data=json.loads(cerrado.to_json()),
    opacity=0.01,
    stroked=True,
    filled=True,
    get_fill_color=[46, 204, 113],
    get_line_color=[0, 0, 0],
)

caatinga_layer = pdk.Layer(
    "GeoJsonLayer",
    data=json.loads(caatinga.to_json()),
    opacity=0.01,
    stroked=True,
    filled=True,
    get_fill_color=[241, 196, 15],
    get_line_color=[0, 0, 0],
)

pontos_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df_pontos.to_dict("records"),
    get_position='[lon_plot, lat_plot]',
    get_fill_color='color',
    pickable=True,
    radiusUnits="pixels",
    get_radius=1,
    radiusMinPixels=10,
    radiusMaxPixels=22,
)

texto_layer = pdk.Layer(
    "TextLayer",
    data=df_pontos.to_dict("records"),
    get_position='[lon_plot, lat_plot]',
    get_text="ranking_str",
    get_size=12,
    get_color=[0, 0, 0],
)

linhas_layer = pdk.Layer(
    "LineLayer",
    data=df_linhas.to_dict("records"),
    get_source_position="source",
    get_target_position="target",
    get_width=2,
    get_color=[120, 120, 120],
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
        pontos_layer,
        texto_layer,
        linhas_layer
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

deck.to_html("mapa_temp.html")

with open("mapa_temp.html", "r", encoding="utf-8") as f:
    mapa_html = f.read()

mapa_html = mapa_html.replace("100vw", "100%").replace("100vh", "100%")

# ==============================
# LEGENDA
# ==============================
legenda_html = "<h2>Projetos que receberam votos da CT do Edital 45 - Fundo Ecos</h2>"

legenda_html += "<h3 style='margin-top:20px;'>Projetos Pequenos</h3>"
df_peq = df_pontos[df_pontos["tipo"] == "Pequeno"].sort_values("ranking_sort")

for _, row in df_peq.iterrows():
    cor = "rgb({},{},{})".format(*row["color"])
    legenda_html += f"""
    <div style="margin-bottom:6px;">
        <span style="
            display:inline-block;
            width:12px;
            height:13px;
            border-radius:50%;
            background:{cor};
            margin-right:6px;
        "></span>
        <b>{row['ranking_str']}</b> — {row['Número projeto']} — {row['Nome da organização']}
    </div>
    """

legenda_html += "<h3 style='margin-top:25px;'>Projetos de Consolidação</h3>"
df_cons = df_pontos[df_pontos["tipo"] == "Consolidação"].sort_values("ranking_sort")

for _, row in df_cons.iterrows():
    cor = "rgb({},{},{})".format(*row["color"])
    legenda_html += f"""
    <div style="margin-bottom:6px;">
        <span style="
            display:inline-block;
            width:12px;
            height:12px;
            border-radius:50%;
            background:{cor};
            margin-right:6px;
        "></span>
        <b>{row['ranking_str']}</b> — {row['Nome da organização']}
    </div>
    """

html_final = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>CGN Edital 45</title>
<style>
body {{ margin:0; font-family:Arial; }}
.container {{ display:flex; height:100vh; width:100vw; }}
.mapa {{ flex:4; width:70%; height:100vh; }}
.mapa iframe {{ width:100%; height:100%; border:none; }}
.legenda {{
    flex:1;
    padding:15px;
    overflow-y:auto;
    border-left:1px solid #ccc;
    background:#fafafa;
}}
</style>
</head>
<body>
<div class="container">
    <div class="mapa">
        {mapa_html}
    </div>
    <div class="legenda">
        {legenda_html}
    </div>
</div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_final)

print("Arquivo 'index.html' criado com sucesso.")