"""Bounded typed defaults access. No output is exposed in public diagnostics."""
import plistlib


def read(runner, domain, key):
    result = runner.run(['defaults','export',domain,'-'],timeout=5)
    if result.returncode:
        raise ValueError('Preference domain unavailable')
    try:
        values = plistlib.loads(result.stdout.encode())
    except Exception:
        raise ValueError('Invalid preferences') from None
    return {'exists': key in values, 'value':values.get(key)}


def write(runner, domain, key, value):
    if not value['exists']:
        argv = ['defaults','delete',domain,key]
    else:
        item = value['value']
        if isinstance(item,bool):
            args = ['-bool',str(item).lower()]
        elif isinstance(item,int):
            args = ['-int',str(item)]
        elif isinstance(item,str):
            args = ['-string',item]
        else:
            raise ValueError('Unsupported preference value')
        argv = ['defaults','write',domain,key,*args]
    result = runner.run(argv,timeout=5)
    if result.returncode:
        raise ValueError('Preference write failed')
