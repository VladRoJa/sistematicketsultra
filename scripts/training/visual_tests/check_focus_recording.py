#!/usr/bin/env python3
"""QA visual aislado: comprueba clics perceptibles sin Suite ni credenciales."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from playwright.sync_api import sync_playwright

from scripts.training.recording_focus import install_focus_context, install_focus_page

OUT = Path("artifacts/capacitacion/click-focus-qa")
HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<style>
body{margin:0;background:#edf2f7;color:#172e4d;font:22px Arial,sans-serif}
header{height:80px;background:#12294d;color:#fff;padding:26px 42px;box-sizing:border-box}
aside{position:absolute;top:80px;bottom:0;width:280px;background:white;padding:25px;box-sizing:border-box}
main{margin-left:320px;padding:28px 48px}
button{font:19px Arial;cursor:pointer;padding:15px 20px;border:1px solid #a8b2c8;
border-radius:10px;background:white;color:#1c334e}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}
.panel{background:white;border-radius:12px;padding:24px;box-shadow:0 3px 14px #c7d0dc}
#result{background:#ddf4e6;padding:24px;margin-top:30px;border-radius:10px}
#modal{display:none;background:white;border:2px solid #aab4c2;border-radius:16px;
position:absolute;top:240px;left:600px;width:500px;padding:24px;box-shadow:0 12px 38px #8793a4}
</style></head><body>
<header><b>CAP-V1 | Pantalla de muestra (sin conexión a Suite Ultra)</b></header>
<aside><h3>Menú</h3><p>Tickets</p><p>Inventarios</p><p>Movimientos</p><p>Reportes</p></aside>
<main><h2>Tickets de demostración</h2><p>Ejemplo sintético para validar la visibilidad de clics.</p>
<section class="grid"><div class="panel"><h3>Ticket de prueba</h3><button id="open">Ver historial</button></div>
<div class="panel"><h3>Recepción</h3><button id="receipt">Ver avance</button></div>
<div class="panel"><h3>Estado</h3><button id="state">Consultar estado</button></div></section>
<div id="result">Todavía no hay una opción seleccionada.</div></main>
<div id="modal"><h3>Historial de demostración</h3><p>La capa de clic no bloquea los botones.</p>
<button id="close">Cerrar</button></div>
<script>
window.clickCount=0;
const result=document.getElementById('result');
for(const id of ['open','receipt','state','close']){
 document.getElementById(id).addEventListener('click',()=>{
   window.clickCount++;
   if(id==='open')document.getElementById('modal').style.display='block';
   if(id==='close')document.getElementById('modal').style.display='none';
   result.textContent='Acción registrada: '+id+' (clic '+window.clickCount+')';
 });
}
</script></body></html>"""


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg y FFprobe obligatorios.")
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(OUT),
            record_video_size={"width": 1600, "height": 900},
            reduced_motion="no-preference",
        )
        install_focus_context(context)
        page = context.new_page()
        video = page.video
        page.goto("data:text/html;charset=utf-8," + __import__("urllib.parse", fromlist=["quote"]).quote(HTML))
        install_focus_page(page)
        assert page.evaluate("window.__capV1FocusRecorder.ready()")
        page.wait_for_timeout(450)
        for action in ("open", "close", "receipt", "state"):
            page.locator("#" + action).click()
            page.wait_for_timeout(800)
            assert page.evaluate("getComputedStyle(document.querySelector('.cap-v1-spotlight')).opacity") == "1"
            assert page.evaluate("!!document.querySelector('.cap-v1-pulse.cap-v1-animate')")
            if action == "close":
                # Se ha ocultado el modal: no debe quedar un marco amarillo
                # sobre el lugar donde ya desapareció el botón.
                assert not page.evaluate("!!document.querySelector('.cap-v1-target.cap-v1-visible')")
            else:
                assert page.evaluate("!!document.querySelector('.cap-v1-target.cap-v1-visible')")
            # Ningún overlay puede interceptar clics ni capturar foco.
            assert page.evaluate("getComputedStyle(document.querySelector('#cap-v1-recording-overlay')).pointerEvents") == "none"
            assert page.evaluate("window.__capV1FocusRecorder.events().length") > 0
        page.wait_for_timeout(1800)
        clicks = page.evaluate("window.clickCount")
        events = page.evaluate("window.__capV1FocusRecorder.events()")
        assert clicks == 4 and len(events) == clicks, (clicks, events)
        assert all(0 <= e["x"] <= 1600 and 0 <= e["y"] <= 900 for e in events)
        context.close()
        video.save_as(str(OUT / "synthetic.webm"))
        browser.close()
    mp4 = OUT / "clicks-y-foco-sintetico.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(OUT / "synthetic.webm"), "-c:v", "libx264", "-pix_fmt",
        "yuv420p", "-crf", "22", "-movflags", "+faststart", str(mp4),
    ], check=True)
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp4),
    ], check=True, capture_output=True, text=True)
    duration = float(probe.stdout.strip())
    assert duration >= 4.5 and mp4.stat().st_size > 25000
    summary = {
        "schema": "cap-v1-visual-focus-qa-v1",
        "dataset": "SYNTHETIC_ONLY",
        "suite_requests": 0,
        "clicks": clicks,
        "overlay_blocks_pointer": False,
        "video_seconds": round(duration, 3),
    }
    (OUT / "qa.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("CAP-V1 VISUAL FOCUS QA PASS: " + json.dumps(summary))


if __name__ == "__main__":
    main()
