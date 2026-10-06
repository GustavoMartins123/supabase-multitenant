"""Test-only internal controller: real Chromium sessions, no TLS bypass/socket.

Only mounted synthetic credentials and the test CA are visible in this container.
No host port is published. The privileged fixture controls fault injection.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess

from playwright.sync_api import sync_playwright

ORIGIN = 'https://studio.p1.test'


def main():
    database = Path.home() / '.pki/nssdb'
    database.mkdir(parents=True)
    subprocess.run(['certutil', '-N', '-d', 'sql:' + str(database), '--empty-password'], check=True)
    subprocess.run(['certutil', '-A', '-d', 'sql:' + str(database), '-n', 'p1-test-ca',
                    '-t', 'C,,', '-i', '/fixture/ca.pem'], check=True)
    credentials = json.loads(Path('/fixture/credentials.json').read_text(encoding='utf-8'))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        pages = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'ready')

            def do_POST(self):
                try:
                    command = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    actor = command['actor']
                    if actor not in pages:
                        context = browser.new_context()
                        page = context.new_page()
                        page.goto(ORIGIN + '/session-test')
                        if actor != 'anonymous':
                            status = page.evaluate('''async credentials => (await fetch('/auth/api/firstfactor', {
                                method:'POST',headers:{'Content-Type':'application/json'},
                                body:JSON.stringify({...credentials,keepMeLoggedIn:false,targetURL:location.origin+'/session-test'})})).status''',
                                credentials[actor])
                            if status != 200:
                                raise RuntimeError(f'Authelia login {actor}: {status}')
                            assert any(c['name'] == 'authelia_session' and c['secure'] and c['httpOnly']
                                       for c in context.cookies(ORIGIN))
                        pages[actor] = page
                    if command.get('step_up'):
                        command['body'] = {**command['body'], 'password': credentials[actor]['password']}
                    session_cookie_before = any(c['name'] == 'authelia_session'
                                                for c in pages[actor].context.cookies(ORIGIN))
                    result = pages[actor].evaluate('''async input => {
                        const headers={...input.headers};
                        if(input.body!==undefined) headers['Content-Type']='application/json';
                        const options={method:input.method,headers,redirect:'manual',cache:'no-store'};
                        if(input.body!==undefined) options.body=JSON.stringify(input.body);
                        if(input.benchmark) {
                            const {samples,concurrency}=input.benchmark;
                            if(!Number.isInteger(samples)||samples<1||samples>1000||
                               !Number.isInteger(concurrency)||concurrency<1||concurrency>16)
                                throw Error('Invalid bounded benchmark configuration');
                            let next=0;
                            const measurements=[];
                            const batchStart=performance.now();
                            await Promise.all(Array.from({length:concurrency},async()=>{
                                while(next++<samples) {
                                    const start=performance.now();
                                    const response=await fetch(input.path,{...options,signal:AbortSignal.timeout(30000)});
                                    await response.arrayBuffer();
                                    measurements.push({status:response.status,milliseconds:performance.now()-start});
                                }
                            }));
                            return {measurements,elapsed_ms:performance.now()-batchStart};
                        }
                        const start=performance.now();
                        const response=await fetch(input.path,{...options,signal:AbortSignal.timeout(30000)});
                        const body=await response.text();
                        return {status:response.status,body,milliseconds:performance.now()-start};
                    }''', command)
                    if command.get('benchmark'):
                        cookies = pages[actor].context.cookies(ORIGIN)
                        result['session_cookie_present'] = any(c['name'] == 'authelia_session' for c in cookies)
                        result['session_cookie_before'] = session_cookie_before
                    payload = json.dumps(result).encode()
                    self.send_response(200)
                except Exception as error:
                    payload = json.dumps({'driver_error': str(error)}).encode()
                    self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(payload)

        try:
            HTTPServer(('0.0.0.0', 8765), Handler).serve_forever()
        finally:
            browser.close()


if __name__ == '__main__':
    main()
