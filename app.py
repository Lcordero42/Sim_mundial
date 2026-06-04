import json
import os
import hashlib
import streamlit as st
import pandas as pd
import re
from datetime import datetime
import pytz

# ============================================================================
# Configuración de Google Sheets
# ============================================================================
URL_BASE = "https://docs.google.com/spreadsheets/d/1x32OesDGzqU6QmHt_wrozLF4cIIUoaBuVCo2bypCeco/export?format=csv"
GIDS = {
    'Teams': 0,
    'Matches_GP': 929864427,
    'Matches_FP': 1793296069,
    'Stages': 542487095
}
DB_FILE = "porra_db.json"

# ============================================================================
# Zona Horaria
# ============================================================================
TZ_MADRID = pytz.timezone('Europe/Madrid')

st.set_page_config(page_title="Quiniela Mundial - Familiar", page_icon="🏆", layout="wide")

# ============================================================================
# Carga de datos cacheada
# ============================================================================
@st.cache_data(ttl=60)
def cargar_hoja_por_gid(url_base: str, gid: int):
    url = f"{url_base}&gid={gid}"
    try:
        return pd.read_csv(url)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_todas_las_hojas():
    return {name: cargar_hoja_por_gid(URL_BASE, gid) for name, gid in GIDS.items()}

# ============================================================================
# Persistencia local
# ============================================================================
def cargar_db() -> dict:
    if not os.path.exists(DB_FILE):
        return {'usuarios': {}, 'quinielas': {}}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {'usuarios': {}, 'quinielas': {}}
        data.setdefault('usuarios', {})
        data.setdefault('quinielas', {})
        return data
    except Exception:
        return {'usuarios': {}, 'quinielas': {}}


def guardar_db(db: dict):
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode('utf-8')).hexdigest()


def slugify(nombre: str) -> str:
    texto = nombre.strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto)
    return texto.strip("_")


def buscar_usuario_por_nombre(nombre: str) -> str | None:
    slug = slugify(nombre)
    if not slug:
        return None
    for uid, usuario in db['usuarios'].items():
        if uid == slug or slugify(usuario.get('name', '')) == slug:
            return uid
    return None


def crear_usuario(nombre: str, avatar: str, pin: str) -> str | None:
    user_id = slugify(nombre)
    if not user_id:
        return None
    original = user_id
    suffix = 1
    while user_id in db['usuarios']:
        user_id = f"{original}_{suffix}"
        suffix += 1
    db['usuarios'][user_id] = {
        'name': nombre.strip(),
        'avatar': avatar,
        'pin_hash': hash_pin(pin),
        'created_at': datetime.now(TZ_MADRID).isoformat()
    }
    db['quinielas'][user_id] = {'gp': {}, 'fp': {}}
    guardar_db(db)
    return user_id


def verificar_pin(user_id: str, pin: str) -> bool:
    usuario = db['usuarios'].get(user_id)
    if not usuario:
        return False
    return usuario.get('pin_hash') == hash_pin(pin)


def actualizar_perfil(user_id: str, nombre: str, avatar: str) -> bool:
    if user_id not in db['usuarios']:
        return False
    nuevo_slug = slugify(nombre)
    if nuevo_slug and nuevo_slug != user_id and nuevo_slug in db['usuarios']:
        return False
    db['usuarios'][user_id]['name'] = nombre.strip()
    db['usuarios'][user_id]['avatar'] = avatar
    guardar_db(db)
    return True


def asegurar_quiniela_usuario(user_id: str):
    if user_id not in db['quinielas']:
        db['quinielas'][user_id] = {'gp': {}, 'fp': {}}
        guardar_db(db)
    return db['quinielas'][user_id]


def obtener_quiniela_usuario(user_id: str) -> dict:
    return asegurar_quiniela_usuario(user_id)


def guardar_pronostico_gp(user_id: str, match_id: int, resultado: str):
    pronosticos = asegurar_quiniela_usuario(user_id)
    pronosticos['gp'][str(match_id)] = resultado
    guardar_db(db)


def guardar_pronostico_fp(user_id: str, match_id: int, campo: str, valor):
    pronosticos = asegurar_quiniela_usuario(user_id)
    partido = pronosticos['fp'].get(str(match_id), {'goles_local': 0, 'goles_visitante': 0, 'ganador_penaltis': None})
    partido[campo] = valor
    pronosticos['fp'][str(match_id)] = partido
    guardar_db(db)


def iniciar_sesion_usuario(nombre: str, pin: str) -> bool:
    user_id = buscar_usuario_por_nombre(nombre)
    if not user_id:
        return False
    if verificar_pin(user_id, pin):
        st.session_state['usuario_id'] = user_id
        return True
    return False

# ============================================================================
# Utilidades de datos
# ============================================================================

def parse_kickoff_at(valor):
    if pd.isna(valor):
        return None
    try:
        fecha = pd.to_datetime(valor, errors='coerce')
        if pd.isna(fecha):
            return None
        if fecha.tzinfo is None:
            return TZ_MADRID.localize(fecha)
        return fecha.astimezone(TZ_MADRID)
    except Exception:
        return None


def obtener_cierre_grupos(df_gp: pd.DataFrame):
    if df_gp.empty or 'kickoff_at' not in df_gp.columns:
        return None
    valid = [v for v in df_gp['kickoff_at'].tolist() if v is not None]
    return min(valid) if valid else None


def obtener_primera_fecha_por_stage(df_fp: pd.DataFrame) -> dict:
    primeras = {}
    if df_fp.empty or 'kickoff_at' not in df_fp.columns:
        return primeras
    for _, row in df_fp.iterrows():
        stage_id = row.get('id_stage')
        kickoff = row.get('kickoff_at')
        if pd.isna(stage_id) or kickoff is None:
            continue
        try:
            stage_id = int(stage_id)
        except Exception:
            continue
        if stage_id not in primeras or kickoff < primeras[stage_id]:
            primeras[stage_id] = kickoff
    return primeras


def normalizar_resultado(valor) -> str:
    if pd.isna(valor):
        return ''
    texto = str(valor).strip().upper()
    return texto if texto in ['1', '2', 'X'] else ''


def obtener_group_label(row) -> str:
    if 'group_letter' in row and pd.notna(row.get('group_letter')):
        return str(row.get('group_letter')).strip()
    label = str(row.get('match_label', '') or '')
    if 'Group' in label:
        partes = label.split()
        return partes[-1] if partes else ''
    return ''


def extraer_labels_match_label(match_label: str) -> tuple[str, str]:
    texto = str(match_label or '').strip()
    partes = [p.strip() for p in texto.split(' vs ')]
    if len(partes) == 2:
        return partes[0], partes[1]
    return texto, ''


def obtener_nombre_partido_fp(partido: dict, team_map: dict) -> str:
    label_local, label_visitante = extraer_labels_match_label(partido.get('match_label', ''))
    home_id = partido.get('home_id')
    away_id = partido.get('away_id')
    home = team_map.get(home_id, label_local) if home_id is not None else label_local
    away = team_map.get(away_id, label_visitante) if away_id is not None else label_visitante
    return f"⚽ {home} vs {away}"


def resolver_nombre_fp(partido: dict, team_map: dict, local: bool) -> str:
    label_local, label_visitante = extraer_labels_match_label(partido.get('match_label', ''))
    label = label_local if local else label_visitante
    team_id = partido.get('home_id') if local else partido.get('away_id')
    if team_id is not None:
        return team_map.get(team_id, label)
    return label or (partido.get('home') if local else partido.get('away', 'Equipo'))

# ============================================================================
# Session state
# ============================================================================
if 'usuario_id' not in st.session_state:
    st.session_state['usuario_id'] = None

# ============================================================================
# Lectura y preparación de datos
# ============================================================================

def cargar_y_preparar_datos():
    dfs = cargar_todas_las_hojas()
    df_teams = dfs.get('Teams', pd.DataFrame()).copy()
    df_gp = dfs.get('Matches_GP', pd.DataFrame()).copy()
    df_fp = dfs.get('Matches_FP', pd.DataFrame()).copy()
    df_stages = dfs.get('Stages', pd.DataFrame()).copy()

    if 'kickoff_at' in df_gp.columns:
        df_gp['kickoff_at'] = df_gp['kickoff_at'].apply(parse_kickoff_at)
    if 'kickoff_at' in df_fp.columns:
        df_fp['kickoff_at'] = df_fp['kickoff_at'].apply(parse_kickoff_at)

    if not df_fp.empty:
        for col in ['home_team_id', 'away_team_id', 'id_stage']:
            if col in df_fp.columns:
                df_fp[col] = pd.to_numeric(df_fp[col], errors='coerce')

    return df_teams, df_gp, df_fp, df_stages


def map_teams(df_teams: pd.DataFrame) -> dict:
    mapping = {}
    if df_teams.empty:
        return mapping
    for _, row in df_teams.iterrows():
        try:
            mapping[int(row['id_team'])] = row.get('team_name', '')
        except Exception:
            continue
    return mapping


def map_stages(df_stages: pd.DataFrame) -> dict:
    mapping = {}
    if df_stages.empty:
        return mapping
    for _, row in df_stages.iterrows():
        try:
            mapping[int(row['id_stage'])] = row.get('stage_name', '')
        except Exception:
            continue
    return mapping


def procesar_partidos_gp(df_gp: pd.DataFrame, team_map: dict) -> list:
    partidos = []
    if df_gp.empty:
        return partidos
    for _, row in df_gp.iterrows():
        try:
            match_id = int(row['id_match']) if pd.notna(row.get('id_match')) else None
        except Exception:
            match_id = None
        try:
            home_id = int(row['home_team_id']) if pd.notna(row.get('home_team_id')) else None
        except Exception:
            home_id = None
        try:
            away_id = int(row['away_team_id']) if pd.notna(row.get('away_team_id')) else None
        except Exception:
            away_id = None
        partidos.append({
            'id': match_id,
            'grupo': obtener_group_label(row),
            'home_id': home_id,
            'away_id': away_id,
            'home': team_map.get(home_id, str(home_id) if home_id is not None else ''),
            'away': team_map.get(away_id, str(away_id) if away_id is not None else ''),
            'resultado_real': normalizar_resultado(row.get('resultado_real') if 'resultado_real' in row else row.get('Result', ''))
        })
    return partidos


def procesar_partidos_fp(df_fp: pd.DataFrame, team_map: dict, stage_map: dict) -> list:
    partidos = []
    if df_fp.empty:
        return partidos
    for _, row in df_fp.iterrows():
        try:
            match_id = int(row['id_match']) if pd.notna(row.get('id_match')) else None
        except Exception:
            match_id = None
        try:
            home_id = int(row['home_team_id']) if pd.notna(row.get('home_team_id')) else None
        except Exception:
            home_id = None
        try:
            away_id = int(row['away_team_id']) if pd.notna(row.get('away_team_id')) else None
        except Exception:
            away_id = None
        try:
            stage_id = int(row['id_stage']) if pd.notna(row.get('id_stage')) else None
        except Exception:
            stage_id = None
        match_label = str(row.get('match_label', '') or '')
        label_local, label_visitante = extraer_labels_match_label(match_label)
        home_name = team_map.get(home_id) if home_id is not None else label_local or match_label
        away_name = team_map.get(away_id) if away_id is not None else label_visitante or match_label

        try:
            home_goals = int(row['home_team_goals']) if pd.notna(row.get('home_team_goals')) else None
        except Exception:
            home_goals = None
        try:
            away_goals = int(row['away_team_goals']) if pd.notna(row.get('away_team_goals')) else None
        except Exception:
            away_goals = None
        try:
            team_winner = int(row['team_winner']) if pd.notna(row.get('team_winner')) else None
        except Exception:
            team_winner = None

        partidos.append({
            'id': match_id,
            'stage_id': stage_id,
            'stage_name': stage_map.get(stage_id, '') if stage_id is not None else '',
            'home_id': home_id,
            'away_id': away_id,
            'home': home_name,
            'away': away_name,
            'match_label': match_label,
            'home_goals_real': home_goals,
            'away_goals_real': away_goals,
            'team_winner_real': team_winner,
            'resultado_real': normalizar_resultado(row.get('resultado_real') if 'resultado_real' in row else row.get('Result', ''))
        })
    return partidos


def tabla_posiciones_torneo(partidos_gp: list, df_teams: pd.DataFrame) -> dict:
    puntos = {}
    group_map = {}
    if not df_teams.empty:
        for _, row in df_teams.iterrows():
            try:
                team_id = int(row['id_team'])
                puntos[team_id] = 0
                group_map[team_id] = row.get('group_letter', '')
            except Exception:
                continue
    for partido in partidos_gp:
        if not partido.get('resultado_real'):
            continue
        home_id = partido.get('home_id')
        away_id = partido.get('away_id')
        resultado = partido['resultado_real']
        if resultado == '1' and home_id is not None:
            puntos[home_id] = puntos.get(home_id, 0) + 3
        elif resultado == '2' and away_id is not None:
            puntos[away_id] = puntos.get(away_id, 0) + 3
        elif resultado == 'X':
            if home_id is not None:
                puntos[home_id] = puntos.get(home_id, 0) + 1
            if away_id is not None:
                puntos[away_id] = puntos.get(away_id, 0) + 1
    grupos = {}
    for team_id, pts in puntos.items():
        grupo = group_map.get(team_id, '')
        grupos.setdefault(grupo, []).append({'Equipo': team_map.get(team_id, str(team_id)), 'Puntos': pts})
    for grupo in grupos:
        grupos[grupo] = sorted(grupos[grupo], key=lambda x: x['Puntos'], reverse=True)
    return grupos


def puntos_usuario_quiniela(usuario_id: str, partidos_gp: list, partidos_fp: list) -> int:
    puntos = 0
    pronosticos = obtener_quiniela_usuario(usuario_id)

    for partido in partidos_gp:
        match_id = partido.get('id')
        if match_id is None:
            continue
        real = partido.get('resultado_real')
        if not real:
            continue
        pred = pronosticos['gp'].get(str(match_id))
        if pred and str(pred).upper() == real:
            puntos += 1

    for partido in partidos_fp:
        match_id = partido.get('id')
        if match_id is None:
            continue
        home_goals_real = partido.get('home_goals_real')
        away_goals_real = partido.get('away_goals_real')
        team_winner_real = partido.get('team_winner_real')
        if home_goals_real is None or away_goals_real is None:
            continue
        pred_fp = pronosticos['fp'].get(str(match_id))
        if not isinstance(pred_fp, dict):
            continue
        home_goals_pred = pred_fp.get('goles_local')
        away_goals_pred = pred_fp.get('goles_visitante')
        if home_goals_pred is None or away_goals_pred is None:
            continue
        if home_goals_pred == home_goals_real and away_goals_pred == away_goals_real:
            if home_goals_real == away_goals_real:
                ganador_pred = pred_fp.get('ganador_penaltis')
                if ganador_pred is None:
                    continue
                if isinstance(ganador_pred, str) and team_winner_real is not None:
                    equipo_real = team_map.get(team_winner_real, '')
                    if ganador_pred == equipo_real:
                        puntos += 1
            else:
                puntos += 1
    return puntos


db = cargar_db()

df_teams, df_gp, df_fp, df_stages = cargar_y_preparar_datos()
team_map = map_teams(df_teams)
stage_map = map_stages(df_stages)
partidos_gp = procesar_partidos_gp(df_gp, team_map)
partidos_fp = procesar_partidos_fp(df_fp, team_map, stage_map)

# ============================================================================
# UI
# ============================================================================
st.title("🏆 Quiniela Familiar del Mundial")

st.markdown('---')

col1, col2, col3 = st.columns([3,1,3])
with col1:
    st.write(f"Partidos de fase de grupos: {len(partidos_gp)}")
with col2:
    st.write(f"Partidos de fase final: {len(partidos_fp)}")
with col3:
    st.write(f"Usuarios registrados: {len(db['usuarios'])}")

st.markdown('---')

tab1, tab2, tab3, tab4 = st.tabs(["👤 Registro", "⚽ Tus Pronósticos", "🏆 Clasificación del Mundial", "📊 Clasificación de la Quiniela"])

with tab1:
    st.header("👤 Registro")
    if st.session_state['usuario_id'] is None:
        with st.form('registro_form'):
            nombre = st.text_input('Nombre')
            existing_id = buscar_usuario_por_nombre(nombre) if nombre else None
            if existing_id:
                pin = st.text_input('PIN de 4 dígitos', type='password', max_chars=4)
                if st.form_submit_button('Iniciar sesión'):
                    if not pin.isdigit() or len(pin) != 4:
                        st.error('El PIN debe tener 4 dígitos.')
                    elif iniciar_sesion_usuario(nombre, pin):
                        st.success('🔒 Sesión iniciada correctamente.')
                        st.experimental_rerun()
                    else:
                        st.error('PIN incorrecto. Intenta de nuevo.')
            else:
                avatar = st.selectbox('Avatar', ["⚽", "🏆", "🥇", "👤", "🧔", "👩"])
                pin = st.text_input('Crea un PIN de 4 dígitos', type='password', max_chars=4)
                if st.form_submit_button('Crear cuenta'):
                    if not nombre or not nombre.strip():
                        st.error('Ingresa un nombre válido.')
                    elif not pin.isdigit() or len(pin) != 4:
                        st.error('El PIN debe tener 4 dígitos.')
                    else:
                        nuevo_id = crear_usuario(nombre, avatar, pin)
                        if nuevo_id:
                            st.session_state['usuario_id'] = nuevo_id
                            st.success('🔒 Cuenta creada y sesión iniciada.')
                            st.experimental_rerun()
                        else:
                            st.error('No se pudo crear la cuenta. Intenta otro nombre.')
    else:
        user_id = st.session_state['usuario_id']
        user = db['usuarios'].get(user_id, {})
        st.success(f"🔒 Sesión activa como {user.get('avatar', '')} {user.get('name', '')}")
        st.markdown('---')
        st.subheader('Editar perfil')
        with st.form('perfil_form'):
            nombre = st.text_input('Nombre', value=user.get('name', ''))
            avatar = st.selectbox(
                'Avatar',
                ["⚽", "🏆", "🥇", "👤", "🧔", "👩"],
                index=["⚽", "🏆", "🥇", "👤", "🧔", "👩"].index(user.get('avatar', '⚽')) if user.get('avatar') in ["⚽", "🏆", "🥇", "👤", "🧔", "👩"] else 0
            )
            if st.form_submit_button('Guardar cambios'):
                if actualizar_perfil(user_id, nombre, avatar):
                    st.success('Perfil actualizado.')
                    st.experimental_rerun()
                else:
                    st.error('No se pudo actualizar el perfil. Elige otro nombre.')

with tab2:
    st.header('⚽ Tus Pronósticos')
    if st.session_state['usuario_id'] is None:
        st.warning('Debes iniciar sesión en la pestaña Registro.')
    else:
        user_id = st.session_state['usuario_id']
        ahora = datetime.now(TZ_MADRID)
        cierre_grupos = obtener_cierre_grupos(df_gp)
        grupos_abiertos = cierre_grupos is None or ahora < cierre_grupos

        st.subheader('Fase de Grupos')
        if cierre_grupos is not None and not grupos_abiertos:
            st.error(f'🔒 Las apuestas de la Fase de Grupos se cerraron el {cierre_grupos.strftime("%d/%m/%Y %H:%M")}')
        if not partidos_gp:
            st.info('No hay partidos de fase de grupos disponibles.')
        else:
            grupos = {}
            for partido in partidos_gp:
                grupos.setdefault(partido.get('grupo', ''), []).append(partido)
            for grupo in sorted(grupos.keys()):
                with st.expander(f'Grupo {grupo or "Sin grupo"}', expanded=False):
                    for partido in grupos[grupo]:
                        mid = partido['id']
                        if mid is None:
                            continue
                        col_a, col_b, col_c = st.columns([3,1,3])
                        with col_a:
                            st.write(f"{partido['home']} vs {partido['away']}")
                        with col_b:
                            pron = obtener_quiniela_usuario(user_id)
                            current = pron['gp'].get(str(mid), 'Seleccionar')
                            opcion = st.selectbox(
                                f'gp_{mid}',
                                ['Seleccionar', '1', 'X', '2'],
                                index=['Seleccionar', '1', 'X', '2'].index(current) if current in ['Seleccionar', '1', 'X', '2'] else 0,
                                key=f'gp_{mid}',
                                disabled=not grupos_abiertos
                            )
                            if grupos_abiertos and opcion != 'Seleccionar' and mid is not None:
                                guardar_pronostico_gp(user_id, mid, opcion)
                        with col_c:
                            st.write(f"Resultado real: {partido['resultado_real'] or 'Pendiente'}")

        st.markdown('---')
        st.subheader('Fase Final - Marcador Exacto + Penaltis 🎯')
        if not partidos_fp:
            st.info('No hay partidos de fase final disponibles.')
        else:
            primeros_por_stage = obtener_primera_fecha_por_stage(df_fp)
            partidos_fp_ordenados = sorted(partidos_fp, key=lambda x: (x.get('stage_id', 999), x.get('id', 999)))
            etapas_por_stage = []
            for partido in partidos_fp_ordenados:
                stage_id = partido.get('stage_id', 999)
                stage_name = partido.get('stage_name', 'Sin etapa') or 'Sin etapa'
                etapas_por_stage.append((stage_id, stage_name, partido))

            ultima_stage = None
            for stage_id, stage_name, partido_stage in etapas_por_stage:
                if stage_id != ultima_stage:
                    if ultima_stage is not None:
                        st.markdown('---')
                    ultima_stage = stage_id
                    stage_first = primeros_por_stage.get(stage_id)
                    stage_abierta = stage_first is None or ahora < stage_first
                    with st.expander(stage_name, expanded=False):
                        if stage_first is not None and not stage_abierta:
                            st.error(f'🔒 La ronda {stage_name} se cerró el {stage_first.strftime("%d/%m/%Y %H:%M")}')
                        stage_partidos = [p for sid, sname, p in etapas_por_stage if sid == stage_id]
                        for idx, partido_stage in enumerate(stage_partidos):
                            mid = partido_stage['id']
                            if mid is None:
                                continue
                            nombre_partido = obtener_nombre_partido_fp(partido_stage, team_map)
                            st.write(f"**{nombre_partido}**")
                            pron = obtener_quiniela_usuario(user_id)
                            pred = pron['fp'].get(str(mid), {'goles_local': 0, 'goles_visitante': 0, 'ganador_penaltis': None})
                            col1, col2 = st.columns(2)
                            with col1:
                                goles_local = st.number_input(
                                    f'Goles Local',
                                    min_value=0,
                                    step=1,
                                    value=pred.get('goles_local', 0),
                                    key=f'fp_home_{mid}_{idx}',
                                    disabled=not stage_abierta
                                )
                                if stage_abierta:
                                    guardar_pronostico_fp(user_id, mid, 'goles_local', goles_local)
                            with col2:
                                goles_visitante = st.number_input(
                                    f'Goles Visitante',
                                    min_value=0,
                                    step=1,
                                    value=pred.get('goles_visitante', 0),
                                    key=f'fp_away_{mid}_{idx}',
                                    disabled=not stage_abierta
                                )
                                if stage_abierta:
                                    guardar_pronostico_fp(user_id, mid, 'goles_visitante', goles_visitante)
                            if goles_local == goles_visitante:
                                st.info(f'⚠️ Empate {goles_local}-{goles_visitante}. Selecciona ganador en penaltis:')
                                local_name = resolver_nombre_fp(partido_stage, team_map, local=True)
                                away_name = resolver_nombre_fp(partido_stage, team_map, local=False)
                                opciones_penaltis = [local_name, away_name]
                                seleccion_actual = pred.get('ganador_penaltis')
                                opcion_index = opciones_penaltis.index(seleccion_actual) if seleccion_actual in opciones_penaltis else 0
                                ganador = st.selectbox(
                                    'Ganador en penaltis 🎯',
                                    opciones_penaltis,
                                    index=opcion_index,
                                    key=f'fp_penaltis_{mid}_{idx}',
                                    disabled=not stage_abierta
                                )
                                if stage_abierta:
                                    guardar_pronostico_fp(user_id, mid, 'ganador_penaltis', ganador)
                            else:
                                if stage_abierta:
                                    guardar_pronostico_fp(user_id, mid, 'ganador_penaltis', None)
                            if partido_stage.get('home_goals_real') is not None and partido_stage.get('away_goals_real') is not None:
                                st.write(f"Resultado real: {partido_stage['home_goals_real']}-{partido_stage['away_goals_real']}")
                            else:
                                st.write('Resultado real: Pendiente')

with tab3:
    st.header('🏆 Clasificación del Mundial')
    if df_gp.empty or df_teams.empty:
        st.info('Faltan datos para calcular la clasificación del torneo.')
    else:
        clasificacion = tabla_posiciones_torneo(partidos_gp, df_teams)
        if not clasificacion:
            st.info('No hay resultados reales para calcular la clasificación.')
        else:
            for grupo, equipos in sorted(clasificacion.items()):
                st.subheader(f'Grupo {grupo or "Sin grupo"}')
                df = pd.DataFrame(equipos)
                st.table(df)

with tab4:
    st.header('📊 Clasificación de la Quiniela')
    jugadores = []
    for uid, usuario in db['usuarios'].items():
        jugadores.append({
            'Participante': f"{usuario.get('avatar','')} {usuario.get('name','')}",
            'Puntos Totales': puntos_usuario_quiniela(uid, partidos_gp, partidos_fp)
        })
    if not jugadores:
        st.info('No hay usuarios registrados aún.')
    else:
        df_jugadores = pd.DataFrame(jugadores).sort_values(by='Puntos Totales', ascending=False)
        st.dataframe(df_jugadores.reset_index(drop=True))

st.markdown('---')
st.caption('Datos cargados desde Google Sheets y persistidos en porra_db.json.')
