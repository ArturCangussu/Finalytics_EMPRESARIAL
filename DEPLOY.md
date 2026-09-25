# Deploy

Precisa de Python 3.10 ou mais novo.

## Instalação

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuração do .env

- `DJANGO_SECRET_KEY`: gere uma com `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DJANGO_DEBUG`: `False` em produção
- `DJANGO_ALLOWED_HOSTS`: domínios do site, separados por vírgula
- `DJANGO_CSRF_TRUSTED_ORIGINS`: os mesmos domínios com `https://`
- `DJANGO_HTTPS`: `True` se o site roda em HTTPS
- `DJANGO_SECURE_SSL_REDIRECT`: `True` para o Django redirecionar http para https (deixe `False` se a hospedagem já faz isso)
- `DJANGO_PERMITIR_CADASTRO`: `False` para desativar o cadastro público na tela de login
- `DJANGO_UPLOAD_MAX_MB`: tamanho máximo de cada arquivo enviado
- `DJANGO_DB_PATH`: opcional, caminho do banco SQLite

Não suba o `.env` para o GitHub. Sem `DJANGO_SECRET_KEY` o projeto não inicia com `DEBUG=False`.

## Banco, estáticos e usuário

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

## Servidor

O WSGI é `analisador_web.wsgi:application`.

- cPanel (Setup Python App): crie um `passenger_wsgi.py` com `from analisador_web.wsgi import application`
- VPS: `gunicorn analisador_web.wsgi --bind 0.0.0.0:8000`, atrás do Nginx com HTTPS
- PythonAnywhere: no arquivo WSGI da aba Web, importe `from analisador_web.wsgi import application`

Os arquivos estáticos são servidos pelo WhiteNoise.

## Observações

- Cada usuário só vê os próprios dados. Se o sistema for de uso interno, desative o cadastro depois de criar os usuários. Dá pra criar novos pelo `/admin/`.
- Os dados ficam no `db.sqlite3`, então faça backup dele.
- Depois de atualizar o código, rode `migrate` e `collectstatic` e reinicie a aplicação.
- `python manage.py check --deploy` mostra se falta alguma configuração de segurança.
