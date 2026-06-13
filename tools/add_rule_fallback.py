target = 'tasks/learning_profile/personal_syllabus.py'
with open(target, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with no_alignment_matches return
for i, line in enumerate(lines):
    if 'return {"synced_weeks": 0, "reason": "no_alignment_matches"}' in line:
        indent = '\t\t'
        block = [
            indent + '# -- rule fallback: keyword/substring match on full week content --\n',
            indent + 'for entry in period:\n',
            indent + '\tif not isinstance(entry, dict):\n',
            indent + '\t\tcontinue\n',
            indent + '\twi = str(entry.get("week_index") or "")\n',
            indent + '\tif not wi or wi in week_scores:\n',
            indent + '\t\tcontinue\n',
            indent + '\tfull_text = " ".join(str(entry.get(k) or "") for k in ("content", "enhanced_content"))\n',
            indent + '\tfor kp_key, kp_score in by_kp.items():\n',
            indent + '\t\tif kp_score <= 0:\n',
            indent + '\t\t\tcontinue\n',
            indent + '\t\t# direct substring match\n',
            indent + '\t\tif kp_key.lower() in full_text.lower():\n',
            indent + '\t\t\tweek_scores[wi] = max(week_scores.get(wi, 0.0), kp_score)\n',
            indent + '\t\t\tbreak\n',
            indent + '\t\t# token-level match (English acronyms: HDFS, ETL, etc.)\n',
            indent + '\t\timport re\n',
            indent + '\t\tfor token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]+", kp_key):\n',
            indent + '\t\t\tif token.lower() in full_text.lower():\n',
            indent + '\t\t\t\tweek_scores[wi] = max(week_scores.get(wi, 0.0), kp_score)\n',
            indent + '\t\t\t\tbreak\n',
            indent + 'if not week_scores:\n',
        ]
        lines[i:i] = block
        print(f'Inserted fallback before L{i+1}')
        break

with open(target, 'w', encoding='utf-8') as f:
    f.writelines(lines)

import py_compile
py_compile.compile(target, doraise=True)
print('OK')
