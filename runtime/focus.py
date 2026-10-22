"""Select the exact originating session; never activate after lookup failure."""
from pathlib import Path
import sys
try:
    from vendor.codex_status.status import terminal_id
except ImportError:
    from .vendor.codex_status.status import terminal_id

def focus(terminal_uuid: str,it2: Path,runner)->bool:
    if terminal_id(terminal_uuid)!=terminal_uuid or not it2.is_absolute():
        return False
    try:
        result=runner.run([str(it2),'session','focus',terminal_uuid],timeout=2)
        if result.returncode:
            return False
        return runner.run([str(it2),'app','activate'],timeout=2).returncode==0
    except Exception:
        return False

if __name__=='__main__':
    from hook import Runner
    sys.exit(0 if len(sys.argv)==3 and focus(sys.argv[1],Path(sys.argv[2]),Runner()) else 1)
