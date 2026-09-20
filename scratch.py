import json
with open('data/custom_workflows/Advanced_V38.json', encoding='utf-8') as f:
    data = json.load(f)
print('Node 164:', json.dumps(data.get('164', {}), indent=2))

import os, struct, glob
def read_safetensors_metadata(path):
    try:
        with open(path, 'rb') as f:
            length_bytes = f.read(8)
            if len(length_bytes) != 8: return 'err'
            header_size = struct.unpack('<Q', length_bytes)[0]
            header_json = f.read(header_size).decode('utf-8')
            header = json.loads(header_json)
            return header.get('__metadata__', {})
    except Exception as e:
        return str(e)

print('--- LORAS ---')
files = glob.glob('F:/wk/**/models/loras/*.safetensors', recursive=True)
for f in files:
    m = read_safetensors_metadata(f)
    print(os.path.basename(f), m.get('ss_base_model_version', m.get('modelspec.architecture', '')) if isinstance(m, dict) else m)
