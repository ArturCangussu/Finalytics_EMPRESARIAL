# Finanalytics

Sistema web em Django para conciliação de extrato bancário com os relatórios do sistema do condomínio.

Você envia o extrato do banco (Sicoob .html/.xlsx ou Caixa .xlsx) e um ou mais relatórios .csv, e o sistema cruza os lançamentos por data e valor, mostrando:

- lançamentos conciliados
- lançamentos que só aparecem no extrato
- lançamentos que só aparecem no relatório

Também tem uma tela para somar receitas, despesas e tarifas PIX de um extrato.

## Tecnologias

Python, Django, Pandas, BeautifulSoup, Bootstrap e SQLite.

## Rodando localmente

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

No `.env`, coloque `DJANGO_DEBUG=True`. Depois:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Para colocar em produção, veja o [DEPLOY.md](DEPLOY.md).
