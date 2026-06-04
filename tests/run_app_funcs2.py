import runpy

app_path = r'c:\Users\LuisCorderoHUMANOX\OneDrive - HUMANOX\Escritorio\sim_mundial\app.py'
ns = runpy.run_path(app_path, run_name='__main__')

if 'obtener_partidos_grupos' in ns:
    partidos_gp = ns['obtener_partidos_grupos']()
    print('Partidos GP cargados:', len(partidos_gp))
    for p in partidos_gp[:5]:
        print(p)
else:
    print('Función obtener_partidos_grupos no encontrada')

if 'obtener_partidos_fp' in ns:
    partidos_fp = ns['obtener_partidos_fp']()
    print('\nPartidos FP cargados:', len(partidos_fp))
    for p in partidos_fp[:5]:
        print(p)
else:
    print('Función obtener_partidos_fp no encontrada')
