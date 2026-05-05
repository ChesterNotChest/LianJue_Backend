# run.py Cheatsheet

Quick commands to run the KnowLion pipeline.

## Single file
```bash
cd /root/knowlion
python3.11 run.py --input /root/knowlion/pdfs/基于RAG的维修手册智能问答系统研究与应用_郭超_象征性编辑.pdf
```
- Runs: convert_to_markdown → markdown_to_triple → triple_to_knowledge → knowledge_to_save → search summary.

## Batch folder
```bash
cd /root/knowlion
python3.11 run.py --input /root/knowlion/pdfs --workers 4
```
- Scans top-level files with ext: pdf/doc/docx/pptx/xlsx/png/jpg/jpeg/md.
- Processes in parallel with 4 threads; prints per-file stats and a summary of successes/failures.

## Customize graph name
```bash
python3.11 run.py --input /root/knowlion/pdfs --graph RAG_Test
```

## Options
- `--input`: file or folder (default `/root/knowlion/pdfs`).
- `--workers`: thread count for parallel processing (default 2). Reduce if backend is not thread-safe.
- `--graph`: target graph name (default `RAG_Test`).

## Outputs
- Per file: markdown length, triple count, knowledge count, and write confirmation.
- Final summary: success/failed files with basic counts.
