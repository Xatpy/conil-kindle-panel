# Conil en el Kindle

Panel para un Kindle Paperwhite 4 (1072 × 1448): previsión de Conil de la Frontera,
viento, próximas horas, salida/puesta de sol y mareas del puerto de Conil.
No sustituye una carta náutica ni una observación del nivel real del mar.

## Versión alojada en GitHub Pages

La imagen se genera con GitHub Actions a los minutos 17 y 47 de cada hora y se
publica como `conil.png` en GitHub Pages. El Kindle sigue descargándola solamente
al entrar en reposo. La previsión puede tener unos 30 minutos de antigüedad,
además de retrasos de Actions y la caché de Pages; la hora de generación permanece
visible. Una consulta fallida impide publicar y mantiene el despliegue anterior.

Este modo funciona con el Mac apagado, siempre que el Kindle tenga Wi-Fi con
acceso a Internet. La URL de la imagen es pública y solo contiene información
meteorológica de Conil. Las copias de seguridad, cachés, ajustes personales e IP
local del dispositivo no se incluyen en el repositorio público.

GitHub puede retrasar ejecuciones programadas. También deshabilita las tareas
programadas de repositorios públicos después de 60 días sin actividad: si ocurre,
reactiva el workflow en Actions. Comprueba la fecha del panel cuando lo consultes.
No se añaden commits artificiales para eludir esa limitación.

## Primera prueba en el Mac

Python 3.11 o posterior:

```sh
cd conil-panel
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python panel.py render
.venv/bin/python panel.py serve --host 0.0.0.0 --port 8789
```

Abre `http://IP_DEL_MAC:8789/conil.png` desde el iPhone en la misma Wi-Fi.
El Mac debe permanecer encendido y accesible. El servidor consulta las fuentes
cada 15 minutos y entrega la imagen desde memoria; no descarga datos por cada petición
del Kindle. El cortafuegos puede solicitar acceso a la red local para Python.
Para exponer el servicio fuera de la red local, usa un alojamiento con HTTPS;
no abras el puerto del router. Este proyecto no contrata ni publica alojamiento.

En Linux instala la fuente DejaVu Sans. También puedes indicar las fuentes con
`CONIL_FONT` y `CONIL_FONT_BOLD` (rutas a fuentes TrueType/OpenType).

## Pantalla de reposo de KOReader

Esta primera versión **solo actualiza al entrar en reposo**, con Wi-Fi ya conectado.
No enciende Wi-Fi, no programa despertares y no cambia el salvapantallas del Kindle
normal. Sin red conserva la última imagen: su fecha permanece visible.
La descarga puede retrasar el reposo hasta unos cinco segundos; la resolución DNS
del sistema puede tardar más, por lo que para la prueba local conviene usar la IP.

1. Comprueba en el iPhone que la URL del panel responde.
2. Sal de KOReader y conecta el USB.
3. Desde el Mac, con la imagen ya generada:

   ```sh
   .venv/bin/python install.py --url http://IP_DEL_MAC:8789/conil.png --configure-sleep
   ```

4. Expulsa el Kindle, desconecta y abre de nuevo KOReader.
5. El instalador selecciona el panel como imagen de reposo y oculta el mensaje
   «Sleeping». Para revisar el ajuste: en `Settings → Screen → Sleep screen → Wallpaper`, selecciona
   `Show custom image or cover on sleep screen`.
6. En `Custom images → Choose image or document cover`, elige
   `/mnt/us/koreader/conil.png`. Desactiva el mensaje «Sleeping» si tapa el panel.
7. Con el Wi-Fi conectado, pon el Kindle en reposo y comprueba la imagen y su hora.

El instalador guarda los archivos anteriores y `settings.reader.lua` en `backups/`.
Solo cambia esos tres ajustes si se usa `--configure-sleep`. Sin esa opción copia
la imagen y el hook, y la selección se hace desde KOReader. El hook se ha escrito contra
las APIs de KOReader 2026.07.1 y se ha probado en un Paperwhite 4 con firmware
5.13.6. Otros dispositivos requieren adaptar la resolución y validar el reposo.

Para desinstalar, borra `koreader/patches/2-conil-sleepscreen.lua` y
`koreader/settings/conil-config.lua`, reinicia KOReader y elige otra pantalla de reposo.
Puedes borrar `koreader/conil.png`. Si recuperas una copia de ajustes, perderás
los cambios de configuración hechos desde esa copia: no es necesario restaurarla
para desinstalar este panel.

## Fuentes y precisión

- [Open-Meteo](https://open-meteo.com/en/docs): previsión para 36.2772, −6.0885.
  No se presenta como una medición de una estación. Un dato con más de dos horas
  se marca como antiguo. Se muestra la hora del dato por separado de la generación
  de la imagen. Datos bajo CC BY 4.0, atribuidos en el panel.
- [API del Instituto Hidrográfico de la Marina](https://ideihm.covam.es/portal/api-mareas/):
  puerto 46, Conil. Los eventos y la curva se extraen del bloque JSON público
  `datos-marea` de su vista gráfica. Es una interfaz que podría cambiar.
  Se valida `utc: true` y se convierte con `Europe/Madrid`, incluyendo horario de verano.
  Las alturas y la curva son predicciones astronómicas referidas al cero IHM.
  No se interpolan pleamares para inventar una curva.

Cada fuente conserva su última respuesta y fecha independientemente. Si no hay
mareas del día solicitado, no se muestra una curva de otro día. Las respuestas
se guardan localmente en `.cache/`; `output/conil.png` es una captura, no se actualiza
sola al verla como archivo. La URL del servidor sí genera una imagen con la hora actual.

## Verificación

```sh
.venv/bin/python -m unittest -v
.venv/bin/python panel.py render --offline
```

Se comprueban la conversión de horas en invierno/verano, eventos alrededor de
medianoche, validación de la respuesta IHM, ausencia de datos y conservación de
caché ante fallos de conexión. La imagen final debe inspeccionarse antes de instalar.

Para ejecutar también las pruebas del hook con Lua 5.1, instala
`requirements-dev.txt` y ejecuta de nuevo unittest. Esas pruebas simulan el dispositivo:
no sustituyen comprobar un ciclo real de reposo en el Kindle.
