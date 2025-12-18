from fastapi.testclient import TestClient
import ezdxf
import math
import tempfile

from app.main import app

client = TestClient(app)

side = 3.21
height = math.sqrt(side ** 2 - (side / 2) ** 2)

doc = ezdxf.new("R2010")
doc.header["$INSUNITS"] = ezdxf.units.IN
msp = doc.modelspace()

msp.add_line((0, 0), (side, 0))
msp.add_line((side, 0), (side / 2, height))
msp.add_line((side / 2, height), (0, 0))

tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.dxf')
tmp.close()
with open(tmp.name, 'w') as fh:
    doc.write(fh)

with open(tmp.name, 'rb') as f:
    files = {"file": ("triangle.dxf", f, "application/dxf")}
    r = client.post('/api/dxf/render/metrics', files=files)
    print('status', r.status_code)
    print(r.json())
