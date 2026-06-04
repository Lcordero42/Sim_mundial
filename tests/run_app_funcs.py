import runpy

ns = runpy.run_path('..\\app.py', run_name='__main__')

# Las funciones quedan en el namespace si app.py las define a nivel global
if 'obtener_partidos_grupos' in ns:
    partidos_gp = ns['obtener_partidos_grupos']()
    print('Partidos GP cargados:', len(partidos_gp))
    print(partidos_gp[:3])
else:
    print('Función obtener_partidos_grupos no encontrada')

if 'obtener_partidos_fp' in ns:
    partidos_fp = ns['obtener_partidos_fp']()
    print('Partidos FP cargados:', len(partidos_fp))
    print(partidos_fp[:3])
else:
    print('Función obtener_partidos_fp no encontrada')
