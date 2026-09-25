from django.conf import settings


def configuracoes_site(request):
    return {'permitir_cadastro': settings.PERMITIR_CADASTRO}
