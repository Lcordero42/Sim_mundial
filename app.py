import json
import hashlib
import streamlit as st
import pandas as pd
import re
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

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
SPREADSHEET_ID = re.search(r"/d/([a-zA-Z0-9_-]+)", URL_BASE).group(1)
USUARIOS_SHEET_NAME = 'Usuarios_DB'
PRONOSTICOS_SHEET_NAME = 'Pronosticos_DB'
USUARIOS_COLUMNS = ['usuario_id', 'nombre', 'pin', 'avatar']
PRONOSTICOS_COLUMNS = ['usuario_id', 'match_id', 'tipo_fase', 'pronostico']

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
# Persistencia en Google Sheets
# ============================================================================

def get_service_account_info() -> dict:
    secret = st.secrets.get('gcp_service_account') or st.secrets.get('google_service_account')
    if not secret:
        raise RuntimeError('Faltan las credenciales de Google Sheets en st.secrets["gcp_service_account"] o st.secrets["google_service_account"].')
    if isinstance(secret, str):
        return json.loads(secret)
    return secret


def get_gspread_client():
    credentials = Credentials.from_service_account_info(
        get_service_account_info(),
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return gspread.authorize(credentials)


def get_spreadsheet():
    client = get_gspread_client()
    return client.open_by_key(SPREADSHEET_ID)


def ensure_worksheet(sheet, title: str, headers: list[str]):
    try:
        worksheet = sheet.worksheet(title)
    except WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        worksheet.append_row(headers)
        return worksheet
    current_headers = worksheet.row_values(1)
    if current_headers != headers:
        worksheet.update('A1', [headers])
    return worksheet


def worksheet_to_dataframe(worksheet, columns: list[str]) -> pd.DataFrame:
    rows = worksheet.get_all_values()
    if not rows or len(rows) < 2:
        return pd.DataFrame(columns=columns)
    header = rows[0]
    df = pd.DataFrame(rows[1:], columns=header)
    for column in columns:
        if column not in df.columns:
            df[column] = ''
    return df[columns].fillna('')


@st.cache_data(ttl=30)
def cargar_usuarios_sheet() -> pd.DataFrame:
    sheet = get_spreadsheet()
    worksheet = ensure_worksheet(sheet, USUARIOS_SHEET_NAME, USUARIOS_COLUMNS)
    df = worksheet_to_dataframe(worksheet, USUARIOS_COLUMNS)
    df['usuario_id'] = df['usuario_id'].astype(str)
    return df


@st.cache_data(ttl=30)
def cargar_pronosticos_sheet() -> pd.DataFrame:
    sheet = get_spreadsheet()
    worksheet = ensure_worksheet(sheet, PRONOSTICOS_SHEET_NAME, PRONOSTICOS_COLUMNS)
    df = worksheet_to_dataframe(worksheet, PRONOSTICOS_COLUMNS)
    df['usuario_id'] = df['usuario_id'].astype(str)
    df['match_id'] = df['match_id'].astype(str)
    df['tipo_fase'] = df['tipo_fase'].astype(str).str.lower()
    return df


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode('utf-8')).hexdigest()


def slugify(nombre: str) -> str:
    texto = nombre.strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto)
    return texto.strip("_")


def normalize_team_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or '').strip().lower())


TEAM_FLAG_MAP = {
    'argentina': '🇦🇷',
    'brazil': '🇧🇷',
    'mexico': '🇲🇽',
    'switzerland': '🇨🇭',
    'colombia': '🇨🇴',
    'uruguay': '🇺🇾',
    'france': '🇫🇷',
    'spain': '🇪🇸',
    'portugal': '🇵🇹',
    'germany': '🇩🇪',
    'england': '🇬🇧',
    'belgium': '🇧🇪',
    'netherlands': '🇳🇱',
    'croatia': '🇭🇷',
    'morocco': '🇲🇦',
    'canada': '🇨🇦',
    'senegal': '🇸🇳',
    'serbia': '🇷🇸',
    'poland': '🇵🇱',
    'japan': '🇯🇵',
    'southkorea': '🇰🇷',
    'korearepublic': '🇰🇷',
    'southafrica': '🇿🇦',
    'czechrepublic': '🇨🇿',
    'usa': '🇺🇸',
    'unitedstates': '🇺🇸',
    'australia': '🇦🇺',
    'tunisia': '🇹🇳',
    'costarica': '🇨🇷',
    'cameroon': '🇨🇲',
    'ghana': '🇬🇭',
    'sweden': '🇸🇪',
    'denmark': '🇩🇰',
    'wales': '🏴',
    'qatar': '🇶🇦'
}


def format_team_label(team_name: str) -> str:
    name = str(team_name or '').strip()
    emoji = TEAM_FLAG_MAP.get(normalize_team_key(name), '')
    return f"{emoji} {name}".strip() if name else ''


def buscar_usuario_por_nombre(nombre: str) -> str | None:
    slug = slugify(nombre)
    if not slug:
        return None
    usuarios = cargar_usuarios_sheet()
    for _, row in usuarios.iterrows():
        uid = str(row['usuario_id'])
        nombre_registro = str(row['nombre'] or '')
        if uid == slug or slugify(nombre_registro) == slug:
            return uid
    return None


def crear_usuario(nombre: str, avatar: str, pin: str) -> str | None:
    usuarios = cargar_usuarios_sheet()
    user_id = slugify(nombre)
    if not user_id:
        return None
    original = user_id
    suffix = 1
    while user_id in usuarios['usuario_id'].tolist():
        user_id = f"{original}_{suffix}"
        suffix += 1
    sheet = get_spreadsheet()
    worksheet = ensure_worksheet(sheet, USUARIOS_SHEET_NAME, USUARIOS_COLUMNS)
    worksheet.append_row([user_id, nombre.strip(), hash_pin(pin), avatar], value_input_option='USER_ENTERED')
    st.cache_data.clear()
    return user_id


def verificar_pin(user_id: str, pin: str) -> bool:
    usuarios = cargar_usuarios_sheet()
    match = usuarios[usuarios['usuario_id'] == user_id]
    if match.empty:
        return False
    return match.iloc[0]['pin'] == hash_pin(pin)


def actualizar_perfil(user_id: str, nombre: str, avatar: str) -> bool:
    usuarios = cargar_usuarios_sheet()
    match = usuarios[usuarios['usuario_id'] == user_id]
    if match.empty:
        return False
    worksheet = get_spreadsheet().worksheet(USUARIOS_SHEET_NAME)
    row_number = int(match.index[0]) + 2
    worksheet.update(f'B{row_number}', nombre.strip())
    worksheet.update(f'D{row_number}', avatar)
    st.cache_data.clear()
    return True


def obtener_quiniela_usuario(user_id: str, pronosticos_df: pd.DataFrame | None = None) -> dict:
    df = pronosticos_df if pronosticos_df is not None else cargar_pronosticos_sheet()
    usuario_df = df[df['usuario_id'] == user_id]
    result = {'gp': {}, 'fp': {}}
    for _, row in usuario_df.iterrows():
        match_id = str(row.get('match_id', '')).strip()
        tipo_fase = str(row.get('tipo_fase', '')).strip().lower()
        pronostico = row.get('pronostico', '')
        if tipo_fase == 'gp':
            result['gp'][match_id] = pronostico
        elif tipo_fase == 'fp':
            try:
                parsed = json.loads(pronostico)
                if not isinstance(parsed, dict):
                    parsed = {}
            except Exception:
                parsed = {}
            parsed.setdefault('goles_local', 0)
            parsed.setdefault('goles_visitante', 0)
            parsed.setdefault('ganador_penaltis', None)
            result['fp'][match_id] = parsed
    return result


def guardar_pronostico_row(user_id: str, match_id: str, tipo_fase: str, pronostico):
    sheet = get_spreadsheet()
    worksheet = ensure_worksheet(sheet, PRONOSTICOS_SHEET_NAME, PRONOSTICOS_COLUMNS)
    pronosticos = cargar_pronosticos_sheet()
    mask = (
        (pronosticos['usuario_id'] == user_id) &
        (pronosticos['match_id'] == str(match_id)) &
        (pronosticos['tipo_fase'] == tipo_fase)
    )
    payload = json.dumps(pronostico, ensure_ascii=False) if tipo_fase == 'fp' else str(pronostico)
    if mask.any():
        row_number = int(mask.idxmax()) + 2
        worksheet.update_acell(f'D{row_number}', payload)
    else:
        worksheet.append_row([user_id, str(match_id), tipo_fase, payload], value_input_option='USER_ENTERED')
    st.cache_data.clear()


def guardar_pronostico_gp(user_id: str, match_id: int, resultado: str):
    guardar_pronostico_row(user_id, str(match_id), 'gp', resultado)


def guardar_pronostico_fp(user_id: str, match_id: int, campo: str, valor):
    pronostico = obtener_quiniela_usuario(user_id)['fp'].get(str(match_id), {
        'goles_local': 0,
        'goles_visitante': 0,
        'ganador_penaltis': None
    })
    pronostico[campo] = valor
    if campo != 'ganador_penaltis' and pronostico.get('goles_local') != pronostico.get('goles_visitante'):
        pronostico['ganador_penaltis'] = None
    guardar_pronostico_row(user_id, str(match_id), 'fp', pronostico)


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
    home = format_team_label(team_map.get(home_id, label_local)) if home_id is not None else format_team_label(label_local)
    away = format_team_label(team_map.get(away_id, label_visitante)) if away_id is not None else format_team_label(label_visitante)
    return f"⚽ {home} vs {away}"


def resolver_nombre_fp(partido: dict, team_map: dict, local: bool) -> str:
    label_local, label_visitante = extraer_labels_match_label(partido.get('match_label', ''))
    label = label_local if local else label_visitante
    team_id = partido.get('home_id') if local else partido.get('away_id')
    if team_id is not None:
        return format_team_label(team_map.get(team_id, label))
    return format_team_label(label or (partido.get('home') if local else partido.get('away', 'Equipo')))

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


usuarios_df = cargar_usuarios_sheet()
pronosticos_df = cargar_pronosticos_sheet()

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
    st.write(f"Usuarios registrados: {len(usuarios_df)}")

st.markdown('---')

tab1, tab2, tab3, tab4 = st.tabs(["👤 Registro", "⚽ Tus Pronósticos", "🏆 Clasificación del Mundial", "📊 Clasificación de la Quiniela"])

with tab1:
    st.header("👤 Acceso")
    if st.session_state['usuario_id'] is None:
        with st.form('login_form'):
            nombre_login = st.text_input('Nombre de Usuario')
            pin_login = st.text_input('PIN de 4 dígitos', type='password', max_chars=4)
            if st.form_submit_button('Iniciar Sesión'):
                if not nombre_login or not nombre_login.strip():
                    st.error('Ingresa un nombre de usuario válido.')
                elif not pin_login.isdigit() or len(pin_login) != 4:
                    st.error('El PIN debe tener 4 dígitos.')
                elif iniciar_sesion_usuario(nombre_login, pin_login):
                    st.success('🔒 Sesión iniciada correctamente.')
                    st.rerun()
                else:
                    st.error('Usuario o PIN incorrecto. Intenta nuevamente.')

        with st.expander('⚠️ ¿No tienes cuenta? Regístrate aquí', expanded=False):
            with st.form('register_form'):
                nombre = st.text_input('Nombre')
                avatar = st.selectbox('Avatar', ["⚽", "🏆", "🥇", "👤", "🧔", "👩"])
                pin = st.text_input('Crea un PIN de 4 dígitos', type='password', max_chars=4)
                if st.form_submit_button('Crear Cuenta'):
                    if not nombre or not nombre.strip():
                        st.error('Ingresa un nombre válido.')
                    elif not pin.isdigit() or len(pin) != 4:
                        st.error('El PIN debe tener 4 dígitos.')
                    elif buscar_usuario_por_nombre(nombre):
                        st.error('Ya existe un usuario con ese nombre. Elige otro nombre.')
                    else:
                        nuevo_id = crear_usuario(nombre, avatar, pin)
                        if nuevo_id:
                            st.session_state['usuario_id'] = nuevo_id
                            st.success('🔒 Cuenta creada y sesión iniciada.')
                            st.rerun()
                        else:
                            st.error('No se pudo crear la cuenta. Intenta otro nombre.')
    else:
        user_id = st.session_state['usuario_id']
        usuario = usuarios_df[usuarios_df['usuario_id'] == user_id]
        user = usuario.iloc[0].to_dict() if not usuario.empty else {}
        st.success(f"🔒 Sesión activa como {user.get('avatar', '')} {user.get('nombre', '')}")
        st.markdown('---')
        if st.button('Cerrar Sesión'):
            st.session_state['usuario_id'] = None
            st.rerun()

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
            pron = obtener_quiniela_usuario(user_id, pronosticos_df)
            grupos = {}
            for partido in partidos_gp:
                grupos.setdefault(partido.get('grupo', ''), []).append(partido)
            for grupo in sorted(grupos.keys()):
                with st.expander(f'Grupo {grupo or "Sin grupo"}', expanded=False):
                    for partido in grupos[grupo]:
                        mid = partido['id']
                        if mid is None:
                            continue
                        home_label = format_team_label(partido['home'])
                        away_label = format_team_label(partido['away'])
                        col_a, col_b, col_c = st.columns([2, 1, 1])
                        with col_a:
                            st.markdown(f"**{home_label} vs {away_label}**")
                        with col_b:
                            current = pron['gp'].get(str(mid))
                            if current not in ['1', 'X', '2']:
                                default_index = 0
                            else:
                                default_index = ['1', 'X', '2'].index(current)
                            widget_key = f'gp_radio_{mid}'
                            opcion = st.radio(
                                'Tu apuesta',
                                ['1', 'X', '2'],
                                index=default_index,
                                key=widget_key,
                                horizontal=True,
                                label_visibility='collapsed',
                                disabled=not grupos_abiertos
                            )
                            if grupos_abiertos and mid is not None:
                                saved_key = f'{widget_key}_saved'
                                if current not in ['1', 'X', '2']:
                                    if saved_key not in st.session_state:
                                        st.session_state[saved_key] = opcion
                                    elif opcion != st.session_state[saved_key]:
                                        guardar_pronostico_gp(user_id, mid, opcion)
                                        st.session_state[saved_key] = opcion
                                elif opcion != current:
                                    guardar_pronostico_gp(user_id, mid, opcion)
                        with col_c:
                            st.write(f"Resultado real: {partido['resultado_real'] or 'Pendiente'}")

        st.markdown('---')
        st.subheader('Fase Final - Marcador Exacto + Penaltis 🎯')
        if not partidos_fp:
            st.info('No hay partidos de fase final disponibles.')
        else:
            pron = obtener_quiniela_usuario(user_id, pronosticos_df)
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
                            st.markdown(f"**{nombre_partido}**")
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
    for _, usuario in usuarios_df.iterrows():
        jugadores.append({
            'Participante': f"{usuario.get('avatar','')} {usuario.get('nombre','')}",
            'Puntos Totales': puntos_usuario_quiniela(usuario['usuario_id'], partidos_gp, partidos_fp)
        })
    if not jugadores:
        st.info('No hay usuarios registrados aún.')
    else:
        df_jugadores = pd.DataFrame(jugadores).sort_values(by='Puntos Totales', ascending=False)
        st.dataframe(df_jugadores.reset_index(drop=True))

st.markdown('---')
st.caption('Datos cargados desde Google Sheets y persistidos en Google Sheets.')
