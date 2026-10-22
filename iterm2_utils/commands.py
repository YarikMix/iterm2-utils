"""Bounded, shell-free process execution; never log payloads."""
import subprocess


class Runner:
    def run(self, argv: list[str], *, timeout: float, stdin: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, input=stdin, capture_output=True, text=True,
                              timeout=timeout, check=False, env=env)

    def mcp_probe(self, argv: list[str], *, timeout: float, env: dict[str, str] | None = None) -> dict:
        """Bounded stdio MCP handshake; discard all content except tool names.

        No shell, stderr capture or session payload is retained. One deadline
        covers initialization, tool inventory, and the observation call.
        """
        import json
        import os
        import selectors
        import signal
        import time
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=env, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer = bytearray()
        received = 0

        def send(value):
            payload = (json.dumps({'jsonrpc':'2.0', **value})+'\n').encode()
            process.stdin.write(payload)
            process.stdin.flush()

        def response(identity):
            nonlocal received
            while True:
                while b'\n' in buffer:
                    line, _, remainder = buffer.partition(b'\n')
                    buffer[:] = remainder
                    value = json.loads(line)
                    if value.get('id') == identity:
                        if 'error' in value or 'result' not in value:
                            raise ValueError('MCP protocol failure')
                        return value['result']
                remaining = deadline-time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise ValueError('MCP probe deadline')
                chunk = os.read(process.stdout.fileno(), 8192)
                received += len(chunk)
                if not chunk or received > 1048576:
                    raise ValueError('MCP probe output limit or EOF')
                buffer.extend(chunk)
        try:
            send({'id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05',
                'capabilities':{},'clientInfo':{'name':'iterm2-utils-probe','version':'1'}}})
            initialized = response(1)
            if initialized.get('protocolVersion') != '2024-11-05' or not isinstance(initialized.get('capabilities'),dict):
                raise ValueError('Unsupported MCP initialization')
            send({'method':'notifications/initialized'})
            send({'id':2,'method':'tools/list','params':{}})
            inventory = response(2)
            tools = inventory.get('tools')
            if inventory.get('nextCursor') or not isinstance(tools,list):
                raise ValueError('Incomplete MCP tool inventory')
            names = [tool['name'] for tool in tools]
            from .config.mcp import TOOLS
            if len(names) != 13 or set(names) != TOOLS:
                return {'tools': names, 'sessions':False}
            send({'id':3,'method':'tools/call','params':{'name':'list_sessions','arguments':{}}})
            result = response(3)
            data=result.get('structuredContent')
            if data is None:
                texts=[item['text'] for item in result.get('content',[]) if item.get('type')=='text']
                if len(texts) != 1:raise ValueError('MCP session result unavailable')
                data=json.loads(texts[0])
            valid=(isinstance(data,dict) and isinstance(data.get('windows'),list) and
                   isinstance(data.get('buried_sessions'),list))
            if valid:
                for window in data['windows']:
                    if not isinstance(window,dict) or not isinstance(window.get('tabs'),list):
                        valid=False
                        break
                    for tab in window['tabs']:
                        if not isinstance(tab,dict) or not isinstance(tab.get('sessions'),list):
                            valid=False
                            break
            return {'tools':names,'sessions':valid and result.get('isError',False) is False}
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            return {'tools':[], 'sessions':False}
        finally:
            selector.close()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=1)
            process.stdin.close()
            process.stdout.close()
