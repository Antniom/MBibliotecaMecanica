import os
count = 0
for root, _, files in os.walk('web/src/content/biblioteca'):
    for f in files:
        if f.endswith('.md'):
            try:
                with open(os.path.join(root, f), 'r', encoding='utf-8') as fh:
                    if 'storage_url: "https' in fh.read():
                        count += 1
            except Exception:
                pass
print('Files with storage_url locally:', count)
