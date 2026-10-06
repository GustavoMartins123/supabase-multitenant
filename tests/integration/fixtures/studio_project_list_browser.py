import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def enable_accessibility(page):
    placeholder = page.locator('flt-semantics-placeholder')
    placeholder.wait_for(state='attached', timeout=30000)
    placeholder.evaluate('(element) => element.click()')


def run(config):
    origin = config['origin']
    assert urlsplit(origin).scheme == 'https'
    assert re.fullmatch(r'[a-z]{20}', config['public_ref'])
    output = Path(config['output_dir'])
    output.mkdir(parents=True, exist_ok=True)
    database = Path.home() / '.pki/nssdb'
    database.mkdir(parents=True, exist_ok=True)
    subprocess.run(['certutil', '-N', '-d', 'sql:' + str(database), '--empty-password'], check=True)
    subprocess.run(['certutil', '-A', '-d', 'sql:' + str(database), '-n', 'studio-test-ca',
                    '-t', 'C,,', '-i', config['ca_file']], check=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 1080}, locale='pt-BR')
            context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=origin)
            context.add_cookies([{'name': 'authelia_session', 'value': config['cookie'],
                                 'url': origin + '/', 'httpOnly': True, 'secure': True, 'sameSite': 'Lax'}])
            page = context.new_page()
            errors = []
            mutations = []
            page.on('pageerror', lambda error: errors.append(error))
            page.on('request', lambda request: mutations.append(request.url)
                    if request.method in {'POST', 'PATCH', 'DELETE'} and
                    urlsplit(request.url).path.startswith('/api/projects') else None)
            page.goto(origin, wait_until='domcontentloaded', timeout=60000)
            enable_accessibility(page)
            payload = page.evaluate("""async () => {
                const response = await fetch('/api/projects');
                return {status:response.status, projects:await response.json()};
            }""")
            assert payload['status'] == 200
            matches = [p for p in payload['projects'] if p['public_ref'] == config['public_ref']]
            assert len(matches) == 1
            project = matches[0]
            assert re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', project['project_uuid'])
            assert isinstance(project['display_name'], str) and project['display_name'].strip()
            card = page.get_by_role('group', name=re.compile('^' + re.escape(project['display_name']) + ' '))
            card.get_by_role('button', name='Show menu', exact=True).wait_for(state='visible', timeout=60000)
            snapshot = page.locator('body').aria_snapshot()
            assert 'Projeto sem identidade canonica' not in snapshot
            assert config['public_ref'] in snapshot
            page.screenshot(path=str(output / 'project-list.png'), full_page=True)
            print('PASS: authenticated project payload renders its canonical identity and public URL')

            card.get_by_role('button', name='Adicionar aos favoritos', exact=True).click()
            try:
                page.get_by_role('button', name='Remover dos favoritos').wait_for(state='visible')
            finally:
                (output / 'favorites-aria.txt').write_text(page.locator('body').aria_snapshot())
                page.screenshot(path=str(output / 'favorites.png'), full_page=True)
            saved = page.evaluate("localStorage.getItem('flutter.project_favorite_ids')")
            assert json.loads(saved) == [project['project_uuid']]
            page.reload(wait_until='domcontentloaded', timeout=60000)
            enable_accessibility(page)
            page.get_by_role('button', name='Remover dos favoritos').wait_for(state='visible', timeout=60000)
            assert page.evaluate("localStorage.getItem('flutter.project_favorite_ids')") == saved
            print('PASS: favorite stores the immutable project UUID and survives reload')

            card.get_by_role('button', name='Show menu', exact=True).click()
            page.get_by_role('menuitem', name='Configurações do Projeto', exact=True).click()
            regenerate = page.get_by_role('button', name='Gerar nova URL', exact=True)
            regenerate.wait_for(state='visible', timeout=30000)
            rename = page.get_by_role('button', name='Renomear projeto', exact=True)
            assert rename.is_disabled()
            page.get_by_role('button', name='Copiar URL').click()
            project_url = page.evaluate('navigator.clipboard.readText()')
            assert project_url.endswith('/' + config['public_ref'])
            name_field = page.get_by_role('textbox', name='Nome do projeto', exact=True)
            name_field.fill('Nome editado sem alterar a URL')
            assert rename.is_enabled()
            page.get_by_role('button', name='Copiar URL').click()
            assert page.evaluate('navigator.clipboard.readText()') == project_url
            page.screenshot(path=str(output / 'project-settings.png'), full_page=True)
            regenerate.click()
            try:
                page.get_by_role('alertdialog').wait_for(state='visible')
            finally:
                (output / 'regeneration-aria.txt').write_text(page.locator('body').aria_snapshot())
                page.screenshot(path=str(output / 'regeneration.png'), full_page=True)
            page.get_by_role('button', name='Fechar', exact=True).wait_for(state='visible')
            snapshot = page.locator('body').aria_snapshot()
            assert 'Gerar nova URL do projeto' in snapshot
            page.get_by_role('button', name='Fechar', exact=True).click()
            assert not mutations, 'UI inspection must not mutate any project'
            assert not errors, 'Browser emitted an uncaught application error'
            print('PASS: rename and URL regeneration are independent controls; no project mutation submitted')
        finally:
            browser.close()


if __name__ == '__main__':
    run(json.load(sys.stdin))
