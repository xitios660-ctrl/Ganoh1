"""Actual Android TV emulator/device test. No production, credentials or coordinates.
python3 tv/tests/android_tv_smoke.py /path/to/signed-demo.apk
FLAG_SECURE is preserved: assertions inspect accessibility XML, not screenshots.
"""
import pathlib
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

PACKAGE = 'com.ganoh.tv.demo'
COMPONENT = PACKAGE + '/com.ganoh.tv.MainActivity'


def adb(*args):
    result = subprocess.run(['adb', *args], check=True, capture_output=True, text=True, timeout=40)
    return result.stdout


def nodes():
    with tempfile.TemporaryDirectory() as folder:
        adb('shell', 'uiautomator', 'dump', '/sdcard/ganoh-tv.xml')
        path = pathlib.Path(folder) / 'ui.xml'
        adb('pull', '/sdcard/ganoh-tv.xml', str(path))
        return [node.attrib for node in ET.parse(path).iter('node')]


def wait_for(text):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        current = nodes()
        if any(text in n.get('text', '') for n in current):
            return current
        time.sleep(.5)
    raise AssertionError('TV did not show: ' + text)


def key(code):
    adb('shell', 'input', 'keyevent', str(code))


def focus(label, directions=(20,)):
    for i in range(16):
        current = nodes()
        if any(n.get('text') == label and n.get('focused') == 'true' for n in current):
            return
        key(directions[i % len(directions)])
    raise AssertionError('D-pad could not focus ' + label)


def main():
    apk = pathlib.Path(sys.argv[1]).resolve()
    assert apk.is_file()
    adb('install', '-r', str(apk))
    adb('shell', 'am', 'force-stop', PACKAGE)
    adb('shell', 'am', 'start', '-W', '-n', COMPONENT)
    wait_for('Abrir demonstração — dados fictícios')
    focus('Abrir demonstração — dados fictícios', (19,))
    key(23)
    wait_for('NÃO SÃO VENDAS REAIS')
    focus('Estoque de RUNNER')
    key(23)
    wait_for('Lanche de demonstração')
    key(4)
    wait_for('TOTAL DAS UNIDADES AUTORIZADAS')
    focus('Sair da demonstração', (19,))
    key(23)
    wait_for('Entrar na homologação')
    focus('Abrir demonstração — dados fictícios', (19,))
    key(23)
    wait_for('NÃO SÃO VENDAS REAIS')
    adb('shell', 'am', 'force-stop', PACKAGE)
    adb('install', '-r', str(apk))
    adb('shell', 'am', 'start', '-W', '-n', COMPONENT)
    final = wait_for('Abrir demonstração — dados fictícios')
    assert not any('TOTAL DAS UNIDADES' in n.get('text', '') for n in final)
    print('PASS Android TV: APK install, real D-pad demo/stock/back/logout, force stop and reinstall; no financial state restored')


if __name__ == '__main__':
    main()
