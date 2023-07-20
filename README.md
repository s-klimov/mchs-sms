## Создать виртуальное окружение
```bash
poetry install 
```

## Как запустить проект
```bash
export SMSC_LOGIN=devman
export SMSC_PSW=Ab6Kinhyxquot
export SMSC_VALID=1
poetry run python mchs_sms/smsc_api.py 
```