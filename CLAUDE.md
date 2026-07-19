# LianJue Backend - Development Guide

## Environment

| Item | Value |
|------|-------|
| Terminal | WSL Ubuntu (not Git Bash, not PowerShell) |
| Python | `/home/chest/miniconda3/envs/lianjue/bin/python` (Python 3.11) |
| Activate | `source /home/chest/miniconda3/etc/profile.d/conda.sh && conda activate lianjue` |
| Work dir | `/mnt/e/AI/Learning-Platform/Lianjue_Backend` |

## Running Tests

```bash
# Non-MySQL tests (no DB required)
python -m pytest tests/test_new_endpoints.py -v -k "not mysql"

# Full test suite (requires MySQL)
python -m pytest tests/test_new_endpoints.py -v
```

## From Windows (wsl.exe)

```powershell
wsl.exe bash -c "source /home/chest/miniconda3/etc/profile.d/conda.sh && conda activate lianjue && cd /mnt/e/AI/Learning-Platform/Lianjue_Backend && python -m pytest tests/test_new_endpoints.py -v -k 'not mysql'"
```
